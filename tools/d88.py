"""Generic, payload-only D88 parsing and write safety for the Valis II builder.

The API intentionally separates inspection from modification:

    image = D88Image.read_verified(path, expected_size=..., expected_sha256=...)
    sector = image.resolve_chr(0x05, 0x00, 0x01)
    image.write_payload(
        sector.data_offset, old_bytes, new_bytes, component="...",
        row_id="...", evidence_ref="document.md#section/table-row", review_status="confirmed",
    )
    image.save(output_path)

Track pointers and sector IDs come from the D88 itself. A write must name an
explicit file offset inside one sector payload and the exact prior bytes.
This module does not infer offsets from text or runtime addresses.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable


class D88Error(ValueError):
    """Base class for malformed images and rejected D88 operations."""


class D88FormatError(D88Error):
    """The input is truncated, inconsistent, or outside supported D88 layouts."""


class SourceIdentityError(D88Error):
    """The input file does not match its declared size and SHA-256 contract."""


class PayloadWriteError(D88Error):
    """A payload write is invalid or its expected source bytes do not match."""


class WriteConflictError(PayloadWriteError):
    """Two reviewed writes claim the same physical payload byte."""


HEADER_160_TRACKS = 0x2A0
HEADER_164_TRACKS = 0x2B0
TRACK_POINTER_OFFSET = 0x20
TRACKS_160 = 160
TRACKS_164 = 164
SECTOR_HEADER_SIZE = 0x10


@dataclass(frozen=True)
class Sector:
    """One sector as stored in the image; offsets point to file bytes."""

    track_indices: tuple[int, ...]
    track_offset: int
    header_offset: int
    data_offset: int
    data_length: int
    c: int
    h: int
    r: int
    n: int
    sectors_per_track: int
    density: int
    deleted: int
    status: int
    recorded_data_length: int

    @property
    def data_end(self) -> int:
        return self.data_offset + self.data_length

    @property
    def chrn(self) -> tuple[int, int, int, int]:
        return self.c, self.h, self.r, self.n

    @property
    def chr(self) -> tuple[int, int, int]:
        return self.c, self.h, self.r

    def contains(self, offset: int, length: int = 1) -> bool:
        return (length > 0 and self.data_offset <= offset
                and offset + length <= self.data_end)


@dataclass(frozen=True)
class PayloadWrite:
    """A manually reviewed write at an explicit D88 file offset."""

    disk_offset: int
    expected_old: bytes
    replacement: bytes
    component: str
    row_id: str
    evidence_ref: str
    review_status: str


@dataclass(frozen=True)
class AppliedWrite:
    component: str
    row_id: str
    disk_offset: int
    length: int
    changed_bytes: int
    chrn: tuple[int, int, int, int]
    evidence_ref: str


class D88Image:
    """Parsed single-disk D88 image with guarded, sector-safe writes.

    `read()` and `parse()` are inspection-only. Mutation and `save()` require
    `read_verified()` so the image's bytes were first checked against both an
    exact source size and SHA-256 supplied by the caller.

    This parser accepts the common 160-pointer (0x2A0-byte) and 164-pointer
    (0x2B0-byte) headers. A concatenated multi-disk file is rejected; callers
    should provide the individual source disk whose identity they pinned.
    Sector payload lengths are derived from N (`128 << N`); the redundant
    length field at sector-header offset 0x0E is retained for inspection but
    is not trusted to locate the next sector.
    """

    def __init__(
        self,
        original: bytes,
        *,
        source_path: Path | None,
        source_verified: bool,
        header_size: int,
        track_pointer_count: int,
        sectors: list[Sector],
        pointers: tuple[int, ...],
        disk_size_field: int,
    ) -> None:
        self._original = original
        self._data = bytearray(original)
        self._source_path = source_path
        self._source_verified = source_verified
        self.header_size = header_size
        self.track_pointer_count = track_pointer_count
        self.sectors = tuple(sectors)
        self.track_pointers = pointers
        self.disk_size_field = disk_size_field
        self._sector_starts = tuple(sector.data_offset for sector in sectors)
        self._applied_writes: list[AppliedWrite] = []
        self._owners: dict[int, AppliedWrite] = {}

    @classmethod
    def read(cls, path: str | Path) -> "D88Image":
        source = Path(path)
        return cls._parse(source.read_bytes(), source_path=source, source_verified=False)

    @classmethod
    def read_verified(
        cls,
        path: str | Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> "D88Image":
        """Read and parse only after exact size and SHA-256 checks pass."""

        source = Path(path)
        data = source.read_bytes()
        verify_source_identity(data, expected_size=expected_size,
                               expected_sha256=expected_sha256, label=str(source))
        return cls._parse(data, source_path=source, source_verified=True)

    @classmethod
    def parse(cls, data: bytes | bytearray | memoryview) -> "D88Image":
        """Parse bytes for inspection; returned images are not writable."""

        return cls._parse(bytes(data), source_path=None, source_verified=False)

    @classmethod
    def _parse(
        cls, data: bytes, *, source_path: Path | None, source_verified: bool
    ) -> "D88Image":
        if len(data) < HEADER_160_TRACKS:
            raise D88FormatError(
                f"D88 is shorter than a 160-track header (0x2A0): 0x{len(data):X} bytes"
            )

        disk_size_field = int.from_bytes(data[0x1C:0x20], "little")
        if disk_size_field and disk_size_field != len(data):
            raise D88FormatError(
                "D88 disk-size field does not match file size; concatenated or malformed "
                f"image (header=0x{disk_size_field:X}, file=0x{len(data):X})"
            )

        first_table = [
            int.from_bytes(data[TRACK_POINTER_OFFSET + 4 * index:
                                TRACK_POINTER_OFFSET + 4 * index + 4], "little")
            for index in range(TRACKS_160)
        ]
        live_first = [pointer for pointer in first_table if pointer and pointer < len(data)]
        if any(pointer > len(data) for pointer in first_table):
            raise D88FormatError("D88 track pointer is outside the file")

        # Older images end the pointer table at 0x2A0; current images use all
        # 164 entries through 0x2B0. The first formatted track marks that edge.
        if live_first and min(live_first) == HEADER_160_TRACKS:
            header_size, track_count = HEADER_160_TRACKS, TRACKS_160
        elif live_first and min(live_first) < HEADER_164_TRACKS:
            raise D88FormatError(
                "first D88 track starts inside the track-pointer table: "
                f"0x{min(live_first):X}"
            )
        elif len(data) >= HEADER_164_TRACKS:
            header_size, track_count = HEADER_164_TRACKS, TRACKS_164
        else:
            header_size, track_count = HEADER_160_TRACKS, TRACKS_160

        if len(data) < header_size:
            raise D88FormatError(f"D88 is shorter than its 0x{header_size:X}-byte header")
        pointers = tuple(
            int.from_bytes(data[TRACK_POINTER_OFFSET + 4 * index:
                                TRACK_POINTER_OFFSET + 4 * index + 4], "little")
            for index in range(track_count)
        )
        for index, pointer in enumerate(pointers):
            # Some writers place the end-of-image offset in unused entries.
            if pointer and pointer != len(data) and pointer < header_size:
                raise D88FormatError(
                    f"track pointer {index} points into the D88 header: 0x{pointer:X}"
                )
            if pointer > len(data):
                raise D88FormatError(
                    f"track pointer {index} is outside the file: 0x{pointer:X}"
                )

        aliases: dict[int, list[int]] = {}
        for index, pointer in enumerate(pointers):
            if pointer and pointer < len(data):
                aliases.setdefault(pointer, []).append(index)
        track_starts = sorted(aliases)

        sectors: list[Sector] = []
        for start_index, track_start in enumerate(track_starts):
            track_end = (track_starts[start_index + 1]
                         if start_index + 1 < len(track_starts) else len(data))
            if track_end <= track_start:
                raise D88FormatError(f"empty or reversed track range at 0x{track_start:X}")
            offset = track_start
            while offset < track_end:
                if offset + SECTOR_HEADER_SIZE > track_end:
                    raise D88FormatError(
                        f"truncated sector header at 0x{offset:X} in track ending 0x{track_end:X}"
                    )
                header = data[offset:offset + SECTOR_HEADER_SIZE]
                n = header[3]
                payload_length = 128 << n
                payload_start = offset + SECTOR_HEADER_SIZE
                payload_end = payload_start + payload_length
                if payload_end > track_end:
                    raise D88FormatError(
                        f"sector payload crosses track boundary at 0x{offset:X}: "
                        f"0x{payload_end:X} > 0x{track_end:X} (N={n})"
                    )
                sectors.append(Sector(
                    track_indices=tuple(aliases[track_start]),
                    track_offset=track_start,
                    header_offset=offset,
                    data_offset=payload_start,
                    data_length=payload_length,
                    c=header[0],
                    h=header[1],
                    r=header[2],
                    n=n,
                    sectors_per_track=int.from_bytes(header[4:6], "little"),
                    density=header[6],
                    deleted=header[7],
                    status=header[8],
                    recorded_data_length=int.from_bytes(header[14:16], "little"),
                ))
                offset = payload_end
            if offset != track_end:
                raise D88FormatError(f"track at 0x{track_start:X} does not end at its boundary")

        return cls(
            data,
            source_path=source_path,
            source_verified=source_verified,
            header_size=header_size,
            track_pointer_count=track_count,
            sectors=sectors,
            pointers=pointers,
            disk_size_field=disk_size_field,
        )

    @property
    def source_verified(self) -> bool:
        return self._source_verified

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self._original).hexdigest()

    @property
    def source_size(self) -> int:
        return len(self._original)

    @property
    def data(self) -> bytes:
        """Return an immutable snapshot; callers cannot bypass write guards."""

        return bytes(self._data)

    @property
    def writes(self) -> tuple[AppliedWrite, ...]:
        return tuple(self._applied_writes)

    def resolve_chr(self, c: int, h: int, r: int, *, n: int | None = None) -> Sector:
        """Resolve an exact sector ID to its D88 file payload location.

        CHR alone is accepted only when it identifies one physical sector;
        pass N when the image contains duplicate CHR IDs with different sizes.
        """

        values = (c, h, r) if n is None else (c, h, r, n)
        if any(not isinstance(value, int) or not 0 <= value <= 0xFF for value in values):
            raise ValueError("C/H/R/N values must be bytes")
        matches = [sector for sector in self.sectors
                   if sector.c == c and sector.h == h and sector.r == r
                   and (n is None or sector.n == n)]
        if len(matches) != 1:
            label = "/".join(f"{value:02X}" for value in values)
            raise D88FormatError(f"sector ID {label} matched {len(matches)} physical sectors")
        return matches[0]

    def sector_at_payload(self, offset: int, length: int = 1) -> Sector:
        """Return the unique sector containing an entire payload byte range."""

        if not isinstance(offset, int) or not isinstance(length, int) or length <= 0:
            raise ValueError("payload offset must be an integer and length must be positive")
        index = bisect_right(self._sector_starts, offset) - 1
        if index < 0 or not self.sectors[index].contains(offset, length):
            raise PayloadWriteError(
                f"file range 0x{offset:X}+0x{length:X} is not wholly inside one sector payload"
            )
        return self.sectors[index]

    def write_payload(
        self,
        disk_offset: int,
        expected_old: bytes,
        replacement: bytes,
        *,
        component: str,
        row_id: str,
        evidence_ref: str,
        review_status: str,
    ) -> AppliedWrite:
        """Apply one explicit, source-guarded payload write."""

        return self.apply_payload_writes((PayloadWrite(
            disk_offset=disk_offset,
            expected_old=expected_old,
            replacement=replacement,
            component=component,
            row_id=row_id,
            evidence_ref=evidence_ref,
            review_status=review_status,
        ),))[0]

    def apply_payload_writes(self, writes: Iterable[PayloadWrite]) -> tuple[AppliedWrite, ...]:
        """Validate a whole write batch before changing any byte.

        Duplicate destinations are rejected even when both rows request the
        same new value. The exception names the offset and both row owners.
        """

        if not self._source_verified:
            raise SourceIdentityError(
                "writes require D88Image.read_verified() with exact expected size and SHA-256"
            )
        rows = tuple(writes)
        if not rows:
            return ()

        planned_owners: dict[int, tuple[PayloadWrite, int]] = {}
        prepared: list[tuple[PayloadWrite, Sector, int]] = []
        for write in rows:
            if not isinstance(write.disk_offset, int) or write.disk_offset < 0:
                raise PayloadWriteError(f"invalid disk offset in {write.component}:{write.row_id}")
            if not write.component:
                raise PayloadWriteError("every payload write needs a component name")
            if not write.row_id or not write.evidence_ref.strip():
                raise PayloadWriteError(
                    f"every payload write needs row_id and evidence_ref: {write.component}"
                )
            if write.review_status != "confirmed":
                raise PayloadWriteError(
                    f"payload write lacks a confirmed source contract: {write.component}:{write.row_id} "
                    f"(status={write.review_status!r})"
                )
            if not isinstance(write.expected_old, bytes) or not isinstance(write.replacement, bytes):
                raise PayloadWriteError("expected_old and replacement must be bytes")
            if not write.expected_old or len(write.expected_old) != len(write.replacement):
                raise PayloadWriteError(
                    f"old/new byte lengths must match and be nonempty in {write.component}:{write.row_id}"
                )
            sector = self.sector_at_payload(write.disk_offset, len(write.replacement))
            actual = self._original[write.disk_offset:write.disk_offset + len(write.expected_old)]
            if actual != write.expected_old:
                mismatch = next(index for index, pair in enumerate(zip(actual, write.expected_old))
                                if pair[0] != pair[1])
                offset = write.disk_offset + mismatch
                raise PayloadWriteError(
                    f"expected-old mismatch at 0x{offset:X} in {write.component}:{write.row_id}: "
                    f"table={write.expected_old[mismatch]:02X}, source={actual[mismatch]:02X}"
                )
            changed = sum(old != new for old, new in zip(write.expected_old, write.replacement))
            prepared.append((write, sector, changed))
            for index, value in enumerate(write.replacement):
                offset = write.disk_offset + index
                prior = self._owners.get(offset)
                pending = planned_owners.get(offset)
                owner = prior or (pending[0] if pending else None)
                if owner is not None:
                    old_new = (self._data[offset] if prior else pending[1])
                    kind = "conflict" if old_new != value else "overlap"
                    raise WriteConflictError(
                        f"{kind} at 0x{offset:X}: {owner.component}:{owner.row_id} and "
                        f"{write.component}:{write.row_id} both claim this payload byte "
                        f"(first=0x{old_new:02X}, second=0x{value:02X})"
                    )
                planned_owners[offset] = (write, value)

        committed: list[AppliedWrite] = []
        for write, sector, changed in prepared:
            report = AppliedWrite(
                component=write.component,
                row_id=write.row_id,
                disk_offset=write.disk_offset,
                length=len(write.replacement),
                changed_bytes=changed,
                chrn=sector.chrn,
                evidence_ref=write.evidence_ref,
            )
            committed.append(report)

        # All bounds, source guards, and overlaps passed; mutation is now atomic
        # with respect to validation failures.
        for write, _, _ in prepared:
            start = write.disk_offset
            self._data[start:start + len(write.replacement)] = write.replacement
        for report in committed:
            self._applied_writes.append(report)
            for offset in range(report.disk_offset, report.disk_offset + report.length):
                self._owners[offset] = report
        return tuple(committed)

    def to_bytes(self) -> bytes:
        return bytes(self._data)

    def sha256(self) -> str:
        return hashlib.sha256(self._data).hexdigest()

    def save(self, path: str | Path) -> None:
        """Validate structure and untouched-byte preservation, then save a copy."""

        if not self._source_verified:
            raise SourceIdentityError("save requires an image loaded through read_verified()")
        output = Path(path)
        if self._source_path is not None and output.resolve() == self._source_path.resolve():
            raise PayloadWriteError("refusing to overwrite the source D88 image")
        written_offsets = set(self._owners)
        for offset, (old, new) in enumerate(zip(self._original, self._data)):
            if offset not in written_offsets and old != new:
                raise PayloadWriteError(f"unregistered byte changed outside a reviewed write at 0x{offset:X}")
        # Reparse before creating output so an invalid image never reaches disk.
        self._parse(bytes(self._data), source_path=None, source_verified=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(self._data)


def verify_source_identity(
    data: bytes | bytearray | memoryview,
    *,
    expected_size: int,
    expected_sha256: str,
    label: str = "D88 input",
) -> None:
    """Fail closed unless both the byte length and SHA-256 match exactly."""

    raw = bytes(data)
    if not isinstance(expected_size, int) or expected_size <= 0:
        raise ValueError("expected_size must be a positive integer")
    if not isinstance(expected_sha256, str):
        raise ValueError("expected_sha256 must be a string")
    expected_hash = expected_sha256.lower()
    if len(expected_hash) != 64 or any(character not in "0123456789abcdef" for character in expected_hash):
        raise ValueError("expected_sha256 must contain exactly 64 hexadecimal characters")
    actual_hash = hashlib.sha256(raw).hexdigest()
    if len(raw) != expected_size or actual_hash != expected_hash:
        raise SourceIdentityError(
            f"{label} does not match source contract: expected size=0x{expected_size:X}, "
            f"SHA-256={expected_hash}; actual size=0x{len(raw):X}, SHA-256={actual_hash}"
        )
