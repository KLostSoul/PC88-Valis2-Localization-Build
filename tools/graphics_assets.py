"""Encode the checked-in Disk A title and Disk B battle CG PNG sources."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "source" / "graphics"


@dataclass(frozen=True)
class EncodedResource:
    disk: str
    name: str
    data: bytes
    spans: tuple[tuple[int, int], ...]
    input_files: tuple[Path, ...]
    layout: str


def _read_plane(path: Path, size: tuple[int, int]) -> bytes:
    try:
        with Image.open(path) as source:
            if source.size != size:
                raise ValueError(
                    f"{path}: expected {size[0]}x{size[1]}, got {source.width}x{source.height}"
                )
            rgba = source.convert("RGBA")
            pixels = bytearray()
            for red, green, blue, alpha in rgba.getdata():
                if alpha != 255 or (red, green, blue) not in ((0, 0, 0), (255, 255, 255)):
                    raise ValueError(f"{path}: plane pixels must be opaque black or white")
                pixels.append(1 if red == 255 else 0)
            return bytes(pixels)
    except OSError as exc:
        raise ValueError(f"Cannot read graphics source {path}: {exc}") from exc


def _pack_rows(pixels: bytes, width: int, height: int) -> bytes:
    if len(pixels) != width * height or width % 8:
        raise ValueError("Invalid 1bpp plane dimensions")
    out = bytearray()
    stride = width // 8
    for y in range(height):
        row = y * width
        for xbyte in range(stride):
            value = 0
            for bit in range(8):
                if pixels[row + xbyte * 8 + bit]:
                    value |= 0x80 >> bit
            out.append(value)
    return bytes(out)


def _pack_columns(pixels: bytes, width: int, height: int) -> bytes:
    row_bytes = _pack_rows(pixels, width, height)
    stride = width // 8
    return bytes(row_bytes[y * stride + xbyte] for xbyte in range(stride) for y in range(height))


class _LsbBitWriter:
    def __init__(self) -> None:
        self.bits: list[int] = []

    def put(self, *bits: int) -> None:
        self.bits.extend(1 if bit else 0 for bit in bits)

    def to_bytes(self) -> bytes:
        out = bytearray()
        for base in range(0, len(self.bits), 8):
            value = 0
            for shift, bit in enumerate(self.bits[base:base + 8]):
                value |= bit << shift
            out.append(value)
        return bytes(out)


class _LsbBitReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0

    def get(self) -> int:
        byte_index, bit_index = divmod(self.position, 8)
        if byte_index >= len(self.data):
            raise ValueError("Title CG control stream ended before the image")
        self.position += 1
        return (self.data[byte_index] >> bit_index) & 1


def _decode_title_resource(resource: bytes, width_bytes: int, height: int) -> bytes:
    if len(resource) < 8 or resource[0] != width_bytes or resource[1] != height:
        raise ValueError("Encoded title CG has an invalid resource header")
    if resource[4] & 0x07 != 0x07:
        raise ValueError("Encoded title CG does not enable all three planes")
    main_end = 8 + int.from_bytes(resource[5:7], "little")
    if main_end > len(resource):
        raise ValueError("Encoded title CG main stream exceeds the resource")
    bits = _LsbBitReader(resource[main_end:])
    ring = bytearray(256)
    ring_pos = 0
    main_pos = 8
    flat = bytearray()

    for _unit in range(width_bytes * 3):
        output = bytearray()
        while len(output) < height:
            first = bits.get()
            if first == 0:
                if main_pos >= main_end:
                    raise ValueError("Encoded title CG literal stream is truncated")
                value = resource[main_pos]
                main_pos += 1
                output.append(value)
                ring[ring_pos] = value
                ring_pos = (ring_pos + 1) & 0xFF
                continue

            second = bits.get()
            if second == 0:
                if main_pos >= main_end:
                    raise ValueError("Encoded title CG run descriptor is missing")
                code = resource[main_pos]
                main_pos += 1
                if code < 0xF0:
                    if code == 0 or main_pos >= main_end:
                        raise ValueError("Encoded title CG same-value run is invalid")
                    value = resource[main_pos]
                    main_pos += 1
                    output.extend((value,) * code)
                else:
                    length = code & 0x0F or 16
                    if main_pos >= main_end:
                        raise ValueError("Encoded title CG dictionary index is missing")
                    index = resource[main_pos]
                    main_pos += 1
                    if index + length > 256:
                        raise ValueError("Encoded title CG dictionary reference crosses its ring")
                    output.extend(ring[index:index + length])
            else:
                third = bits.get()
                if third == 0:
                    if main_pos + 3 > main_end:
                        raise ValueError("Encoded title CG alternating run is truncated")
                    length, first_value, second_value = resource[main_pos:main_pos + 3]
                    main_pos += 3
                    if length == 0:
                        raise ValueError("Encoded title CG alternating run has zero length")
                    output.extend(first_value if i % 2 == 0 else second_value for i in range(length))
                elif bits.get() == 0:
                    output.append(0)
                    ring[ring_pos] = 0
                    ring_pos = (ring_pos + 1) & 0xFF
                else:
                    if main_pos >= main_end:
                        raise ValueError("Encoded title CG fill length is missing")
                    length = resource[main_pos]
                    main_pos += 1
                    if length == 0:
                        raise ValueError("Encoded title CG fill run has zero length")
                    output.extend((resource[7],) * length)

            if len(output) > height:
                raise ValueError("Encoded title CG token crosses a plane-column boundary")
        flat.extend(output)

    if main_pos != main_end:
        raise ValueError("Encoded title CG main stream has unconsumed bytes")
    consumed_control = (bits.position + 7) // 8
    if consumed_control != len(resource) - main_end:
        raise ValueError("Encoded title CG control stream has unconsumed bytes")
    return bytes(flat)


def _title_dictionary_match(ring: bytearray, raw: bytes, pos: int, remaining: int) -> tuple[int, int]:
    best_length = 0
    best_index = 0
    max_length = min(16, remaining)
    for index in range(256):
        limit = min(max_length, 256 - index)
        if limit <= best_length:
            continue
        length = 0
        while length < limit and ring[index + length] == raw[pos + length]:
            length += 1
        if length > best_length:
            best_length, best_index = length, index
            if length == max_length:
                break
    return best_length, best_index


def _run_length(raw: bytes, pos: int, remaining: int, value: int, cap: int) -> int:
    length = 0
    while length < min(remaining, cap) and raw[pos + length] == value:
        length += 1
    return length


def _alternating_length(raw: bytes, pos: int, remaining: int) -> int:
    if remaining < 2:
        return remaining
    first, second = raw[pos], raw[pos + 1]
    length = 2
    while length < min(remaining, 0xFF):
        if raw[pos + length] != (first if length % 2 == 0 else second):
            break
        length += 1
    return length


def _compress_title_planes(
    planes: Sequence[bytes], header_source: bytes, width_bytes: int, height: int
) -> bytes:
    expected_plane_size = width_bytes * height
    if len(planes) != 3 or any(len(plane) != expected_plane_size for plane in planes):
        raise ValueError("Title CG requires three planes with the declared dimensions")
    if len(header_source) < 8:
        raise ValueError("Title CG source header is missing")

    # The game stores each X byte column as three plane runs, with Y bytes inside each run.
    column_planes = [_pack_columns_from_packed(plane, width_bytes, height) for plane in planes]
    flat = bytearray()
    for xbyte in range(width_bytes):
        for plane in column_planes:
            flat.extend(plane[xbyte * height:(xbyte + 1) * height])

    header = bytearray(header_source[:8])
    header[0] = width_bytes
    header[1] = height
    fill = header[7]
    main = bytearray()
    control = _LsbBitWriter()
    ring = bytearray(256)
    ring_pos = 0
    pos = 0

    for _unit in range(width_bytes * 3):
        unit_end = pos + height
        while pos < unit_end:
            remaining = unit_end - pos
            value = flat[pos]
            candidates: list[tuple[int, int, str, int, object | None]] = []

            if value == fill:
                length = _run_length(flat, pos, remaining, value, 0xFF)
                if length >= 2:
                    candidates.append((length * 9 - 12, 5, "fill", length, None))
            length = _run_length(flat, pos, remaining, value, 0xEF)
            if length >= 2:
                candidates.append((length * 9 - 18, 4, "same", length, value))
            length = _alternating_length(flat, pos, remaining)
            if length >= 3:
                candidates.append((length * 9 - 27, 3, "alternating", length, (flat[pos], flat[pos + 1])))
            length, index = _title_dictionary_match(ring, flat, pos, remaining)
            if length >= 2:
                candidates.append((length * 9 - 18, 6, "dictionary", length, index))
            if value == 0:
                candidates.append((5, 7, "zero", 1, None))

            best = max(candidates, default=(0, 0, "literal", 1, None))
            if best[0] <= 0:
                best = (0, 0, "literal", 1, None)
            _saving, _priority, kind, length, extra = best

            if kind == "literal":
                control.put(0)
                main.append(value)
                ring[ring_pos] = value
                ring_pos = (ring_pos + 1) & 0xFF
                pos += 1
            elif kind == "zero":
                control.put(1, 1, 1, 0)
                ring[ring_pos] = 0
                ring_pos = (ring_pos + 1) & 0xFF
                pos += 1
            elif kind == "fill":
                control.put(1, 1, 1, 1)
                main.append(length)
                pos += length
            elif kind == "same":
                control.put(1, 0)
                main.extend((length, int(extra)))
                pos += length
            elif kind == "alternating":
                first, second = extra  # type: ignore[misc]
                control.put(1, 1, 0)
                main.extend((length, first, second))
                pos += length
            elif kind == "dictionary":
                index = int(extra)
                control.put(1, 0)
                main.extend((0xF0 if length == 16 else (0xF0 | length), index))
                pos += length
            else:
                raise AssertionError(f"Unknown title compression token {kind}")
        if pos != unit_end:
            raise AssertionError("Title compressor crossed a plane-column boundary")

    header[5:7] = len(main).to_bytes(2, "little")
    result = bytes(header + main + control.to_bytes())
    if _decode_title_resource(result, width_bytes, height) != bytes(flat):
        raise ValueError("Title CG encoder round trip does not match its PNG planes")
    return result


def _pack_columns_from_packed(row_packed: bytes, width_bytes: int, height: int) -> bytes:
    return bytes(row_packed[y * width_bytes + xbyte]
                 for xbyte in range(width_bytes) for y in range(height))


def _encode_ii(planes: Sequence[bytes], width_bytes: int, height: int) -> bytes:
    if len(planes) != 3:
        raise ValueError("II image requires exactly three planes")
    packed = [_pack_rows(plane, width_bytes * 8, height) for plane in planes]
    out = bytearray()
    for index in range(width_bytes * height):
        out.extend((packed[0][index], packed[1][index], packed[2][index]))
    return bytes(out)


class _MsbBitWriter:
    def __init__(self) -> None:
        self.bits: list[int] = []

    def put(self, bit: int) -> None:
        self.bits.append(1 if bit else 0)

    def to_bytes(self) -> bytes:
        out = bytearray()
        for base in range(0, len(self.bits), 8):
            value = 0
            for index, bit in enumerate(self.bits[base:base + 8]):
                value |= bit << (7 - index)
            out.append(value)
        return bytes(out)


class _MsbBitReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0

    def get(self) -> int:
        byte_index, bit_index = divmod(self.position, 8)
        if byte_index >= len(self.data):
            raise ValueError("Battle CG control stream ended before the image")
        self.position += 1
        return (self.data[byte_index] >> (7 - bit_index)) & 1


def _compress_battle(planes: Sequence[bytes], header_source: bytes, max_size: int) -> bytes:
    width_bytes, height = 80, 200
    plane_size = width_bytes * height
    if len(planes) != 3 or any(len(plane) != plane_size for plane in planes):
        raise ValueError("Battle CG requires three 640x200 planes")
    if len(header_source) < 12:
        raise ValueError("Battle CG source header is missing")

    history = bytearray(256)
    for index in range(128):
        history[index * 2] = index + 1
        history[index * 2 + 1] = 0
    history_pos = 0
    main = bytearray()
    control = _MsbBitWriter()

    for xbyte in range(width_bytes):
        for plane in planes:
            unit = bytes(plane[y * width_bytes + xbyte] for y in range(height))
            unit_main_start = len(main)
            pos = 0
            while pos < height:
                value = unit[pos]
                run = 1
                while pos + run < height and unit[pos + run] == value:
                    run += 1
                length = min(run, 0x80)
                remaining = height - pos
                if length == 1:
                    control.put(1)
                    main.append(value)
                    pos += 1
                    continue

                reference = None
                for index in range(0x80):
                    if history[index + 1] != value:
                        continue
                    history_length = history[index] + 1
                    if history_length == length or (length == remaining and history_length >= length):
                        reference = index
                        break
                control.put(0)
                if reference is not None:
                    main.append(0x80 | reference)
                else:
                    main.extend((length - 1, value))
                pos += length

            for byte in main[unit_main_start:]:
                history[history_pos] = byte
                history_pos = (history_pos + 1) & 0xFF

    control_bytes = control.to_bytes()
    control_offset = 12 + len(main)
    total_size = control_offset + len(control_bytes)
    if total_size > max_size:
        raise ValueError(f"Battle CG encoded resource exceeds 0x{max_size:X}-byte allocation")

    header = bytearray(header_source[:12])
    header[2:4] = control_offset.to_bytes(2, "little")
    header[6:8] = total_size.to_bytes(2, "little")
    header[8] = width_bytes
    header[9] = height
    header[10] = (header[10] & 0xF8) | 0x07
    result = bytes(header + main + control_bytes)
    if _decode_battle_resource(result, width_bytes, height) != tuple(bytes(plane) for plane in planes):
        raise ValueError("Battle CG encoder round trip does not match its PNG planes")
    return result


def _decode_battle_resource(resource: bytes, width_bytes: int, height: int) -> tuple[bytes, bytes, bytes]:
    if len(resource) < 12 or resource[8] != width_bytes or resource[9] != height:
        raise ValueError("Encoded battle CG has an invalid resource header")
    main_end = int.from_bytes(resource[2:4], "little")
    total_size = int.from_bytes(resource[6:8], "little")
    if not 12 <= main_end <= total_size <= len(resource):
        raise ValueError("Encoded battle CG main/control offsets are invalid")
    main = resource[12:main_end]
    bits = _MsbBitReader(resource[main_end:total_size])
    history = bytearray(256)
    for index in range(128):
        history[index * 2] = index + 1
        history[index * 2 + 1] = 0
    history_pos = 0
    main_pos = 0
    planes = [bytearray(width_bytes * height) for _ in range(3)]

    for xbyte in range(width_bytes):
        for plane_index in range(3):
            unit_main_start = main_pos
            y = 0
            while y < height:
                if bits.get():
                    if main_pos >= len(main):
                        raise ValueError("Encoded battle CG literal is truncated")
                    value = main[main_pos]
                    main_pos += 1
                    planes[plane_index][y * width_bytes + xbyte] = value
                    y += 1
                    continue
                if main_pos >= len(main):
                    raise ValueError("Encoded battle CG run descriptor is missing")
                descriptor = main[main_pos]
                main_pos += 1
                if descriptor < 0x80:
                    length = descriptor + 1
                    if main_pos >= len(main):
                        raise ValueError("Encoded battle CG direct-run value is missing")
                    value = main[main_pos]
                    main_pos += 1
                else:
                    index = descriptor & 0x7F
                    length = history[index] + 1
                    value = history[index + 1]
                count = min(length, height - y)
                for _ in range(count):
                    planes[plane_index][y * width_bytes + xbyte] = value
                    y += 1
            for value in main[unit_main_start:main_pos]:
                history[history_pos] = value
                history_pos = (history_pos + 1) & 0xFF

    if main_pos != len(main) or (bits.position + 7) // 8 != len(resource[main_end:total_size]):
        raise ValueError("Encoded battle CG streams have unconsumed bytes")
    return tuple(bytes(plane) for plane in planes)  # type: ignore[return-value]


def _ram_spans(
    ram_start: int, length: int, fields: Sequence[dict]
) -> tuple[tuple[int, int], ...]:
    """Map one RAM resource through the explicitly listed Disk A data fields."""
    ram_end = ram_start + length
    result: list[tuple[int, int]] = []
    covered = 0
    for field in fields:
        field_ram = int(field["ram_start"], 16)
        raw_start = int(field["raw_start"], 16)
        field_size = int(field["bytes"])
        begin = max(ram_start, field_ram)
        end = min(ram_end, field_ram + field_size)
        if begin < end:
            size = end - begin
            result.append((raw_start + begin - field_ram, size))
            covered += size
    if covered != length:
        raise ValueError(f"Disk A RAM range 0x{ram_start:04X}+0x{length:X} is not fully mapped")
    return tuple(result)


def _files(paths: Sequence[str]) -> tuple[Path, ...]:
    files = tuple((ROOT / path).resolve() for path in paths)
    if not files or any(ASSET_DIR.resolve() not in path.parents for path in files):
        raise ValueError("Graphics inputs must be files under source/graphics")
    return files


def _plane_files(mapping: dict) -> tuple[Path, Path, Path]:
    order = ("5C", "5D", "5E")
    if set(mapping) != set(order):
        raise ValueError("Three-plane PNG inputs must identify 5C, 5D, and 5E explicitly")
    files = tuple(_files((mapping[plane],))[0] for plane in order)
    return files  # type: ignore[return-value]


def _dimensions(config: dict) -> tuple[int, int]:
    try:
        width, height = config["dimensions"].split("x", 1)
        return int(width), int(height)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid graphics dimensions: {config.get('dimensions')!r}") from exc


def _check_declared_hash(data: bytes, config: dict, label: str) -> None:
    expected = config.get("encoded_target_sha256")
    if expected and hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"{label}: PNG encoder output differs from the declared resource hash")


def build_disk_a_resources(disk_data: bytes, table: dict) -> tuple[EncodedResource, ...]:
    layout = table["resource_layout"]
    inputs = table["asset_inputs"]
    fields = layout["disk_a_data_fields"]

    mugen_config = layout["mugen_title"]
    mugen_files = _plane_files(inputs["mugen_title_planes"])
    mugen_width, mugen_height = _dimensions(mugen_config)
    mugen_planes = tuple(
        _pack_rows(_read_plane(path, (mugen_width, mugen_height)), mugen_width, mugen_height)
        for path in mugen_files
    )
    mugen_start = int(mugen_config["ram_start"], 16)
    mugen_spans = _ram_spans(mugen_start, 8, fields)
    mugen_raw = mugen_spans[0][0]
    mugen = _compress_title_planes(
        mugen_planes, disk_data[mugen_raw:mugen_raw + 8], mugen_width // 8, mugen_height
    )
    if len(mugen) > int(mugen_config["maximum_size"], 16):
        raise ValueError("Disk A 夢幻戰士 title exceeds its declared RAM allocation")
    _check_declared_hash(mugen, mugen_config, "Disk A Mugen title")

    scroll_config = layout["mugen_scroll"]
    scroll_file = _files((inputs["mugen_scroll"],))[0]
    scroll_width, scroll_height = _dimensions(scroll_config)
    scroll = _pack_rows(_read_plane(scroll_file, (scroll_width, scroll_height)), scroll_width, scroll_height)
    _check_declared_hash(scroll, scroll_config, "Disk A Mugen scroll")

    ii_config = layout["roman_ii"]
    ii_files = _plane_files(inputs["roman_ii_planes"])
    ii_width, ii_height = _dimensions(ii_config)
    ii_planes = tuple(_read_plane(path, (ii_width, ii_height)) for path in ii_files)
    ii = _encode_ii(ii_planes, ii_width // 8, ii_height)
    _check_declared_hash(ii, ii_config, "Disk A Roman II")

    valis_config = layout["valis_title"]
    valis_files = _plane_files(inputs["valis_title_planes"])
    valis_width, valis_height = _dimensions(valis_config)
    valis_planes = tuple(
        _pack_rows(_read_plane(path, (valis_width, valis_height)), valis_width, valis_height)
        for path in valis_files
    )
    valis_start = int(valis_config["ram_start"], 16)
    valis_spans = _ram_spans(valis_start, 8, fields)
    valis_raw = valis_spans[0][0]
    valis = _compress_title_planes(
        valis_planes, disk_data[valis_raw:valis_raw + 8], valis_width // 8, valis_height
    )
    if len(valis) > int(valis_config["maximum_size"], 16):
        raise ValueError("Disk A ヴァリス title exceeds its declared RAM allocation")

    specs = (
        ("mugen-title", mugen, _ram_spans(mugen_start, len(mugen), fields), mugen_files, "compressed 352x17 3-plane"),
        ("mugen-scroll", scroll, _ram_spans(int(scroll_config["ram_start"], 16), len(scroll), fields), (scroll_file,), "row-major 352x16 1bpp"),
        ("roman-ii", ii, _ram_spans(int(ii_config["ram_start"], 16), len(ii), fields), ii_files, "row-major 152x79 3-plane interleave"),
        ("valis-title", valis, _ram_spans(valis_start, len(valis), fields), valis_files, "compressed 376x91 3-plane"),
    )
    return tuple(EncodedResource("A", name, data, spans, files, layout)
                 for name, data, spans, files, layout in specs)


def build_disk_b_battle_resource(disk_data: bytes, table: dict) -> EncodedResource:
    layout = table["resource_layout"]
    files = _plane_files(table["asset_inputs"]["battle_planes"])
    planes = tuple(_pack_rows(_read_plane(path, (640, 200)), 640, 200) for path in files)
    spans = tuple(
        (int(item["raw_start"], 16), int(item["bytes"]))
        for item in layout["raw_data_spans"]
    )
    raw_start = spans[0][0]
    target = _compress_battle(planes, disk_data[raw_start:raw_start + 12], int(layout["reserved_capacity_bytes"], 16))
    declared_size = int(layout["target_resource_bytes"], 16)
    if len(target) != declared_size:
        raise ValueError(f"Disk B battle CG encoded size changed: 0x{len(target):X} != declared 0x{declared_size:X}")
    declared_header = bytes.fromhex(layout["target_header_hex"])
    if target[:12] != declared_header:
        raise ValueError("Disk B battle CG generated header differs from the reviewed resource layout")
    _check_declared_hash(target, layout, "Disk B battle CG")
    return EncodedResource("B", "battle-cg", target, spans, files, "compressed 640x200 3-plane")


def write_spans(resource: EncodedResource, source_data: bytes, component: str, evidence_ref: str):
    """Create guarded writes, splitting only at listed D88 data-field boundaries."""
    from .d88 import PayloadWrite

    writes = []
    position = 0
    for index, (raw_start, span_size) in enumerate(resource.spans, 1):
        if position >= len(resource.data):
            break
        length = min(span_size, len(resource.data) - position)
        end = raw_start + length
        if raw_start < 0 or end > len(source_data):
            raise ValueError(f"{resource.name}: D88 raw span is outside the source image")
        old = source_data[raw_start:end]
        new = resource.data[position:position + length]
        if old != new:
            writes.append(PayloadWrite(
                disk_offset=raw_start,
                expected_old=old,
                replacement=new,
                component=component,
                row_id=f"{resource.disk.lower()}-{resource.name}-png-span-{index:02d}",
                evidence_ref=evidence_ref,
                review_status="confirmed",
            ))
        position += length
    if position != len(resource.data):
        raise ValueError(f"{resource.name}: encoded resource exceeds its listed D88 spans")
    return writes


def resource_report(resources: Iterable[EncodedResource], digest) -> list[dict]:
    result = []
    for resource in resources:
        result.append({
            "disk": resource.disk,
            "resource": resource.name,
            "layout": resource.layout,
            "encoded_size_bytes": len(resource.data),
            "encoded_sha256": digest(resource.data),
            "inputs": [
                {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())}
                for path in resource.input_files
            ],
        })
    return result
