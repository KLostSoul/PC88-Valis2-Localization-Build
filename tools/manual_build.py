"""Rebuild Valis II media from reviewed patch tables and included CG PNG inputs.

It verifies each original input against its recorded Japanese source identity,
re-encodes the checked-in Disk A/B graphics planes, applies explicit patch
tables through the sector-safe D88 writer, and emits IPS files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .d88 import D88Image, PayloadWrite
from .graphics_assets import (
    build_disk_a_resources,
    build_disk_b_battle_resource,
    resource_report,
    write_spans,
)
from .ips import apply_ips, encode_ips


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source" / "manual-build"
BASELINE_PATH = SOURCE_DIR / "source-baseline.json"
SCOPE_PATH = SOURCE_DIR / "build-scope.json"
KANJI_MAP_PATH = ROOT / "source" / "kanji" / "glyph-assignment-reference.csv"
IMPORT_DIR = ROOT / "import"
DEFAULT_OUTPUT = ROOT / "output"


class BuildError(RuntimeError):
    """A source contract or guarded build operation failed."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"Cannot read JSON source {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"JSON root must be an object: {path}")
    return value


def hex_bytes(value: Any, *, table: Path, row_id: str, field: str) -> bytes:
    if not isinstance(value, str) or not value.strip():
        raise BuildError(f"{table}:{row_id}: missing {field}")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise BuildError(f"{table}:{row_id}: invalid {field} hex") from exc


def load_baseline() -> dict[str, Any]:
    value = read_json(BASELINE_PATH)
    if value.get("schema") != "valis2.manual_build_source_baseline.v1":
        raise BuildError(f"Unsupported source baseline schema: {BASELINE_PATH}")
    disks = value.get("disks")
    if not isinstance(disks, dict) or set(disks) != set("ABCDEFG"):
        raise BuildError("Source baseline must declare disks A through G")
    kanji = value.get("kanji1")
    if not isinstance(kanji, dict) or not isinstance(kanji.get("sha256"), str):
        raise BuildError("Source baseline must declare the generated Korean KANJI1 ROM identity")
    return value


def load_patch_tables() -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    result: dict[str, list[tuple[Path, dict[str, Any]]]] = {disk: [] for disk in "ABCDEFG"}
    scope = read_json(SCOPE_PATH)
    if scope.get("schema") != "valis2.manual_build_scope.v1" or scope.get("require_all_components") is not True:
        raise BuildError(f"Unsupported or incomplete build scope: {SCOPE_PATH}")
    expected: dict[str, str] = {}
    for item in scope.get("components", []):
        if not isinstance(item, dict) or item.get("id") in expected:
            raise BuildError(f"Invalid or duplicate component in build scope: {item!r}")
        component_id, disk = item.get("id"), item.get("disk")
        if not isinstance(component_id, str) or disk not in result:
            raise BuildError(f"Invalid component id or disk in build scope: {item!r}")
        expected[component_id] = disk
    candidates: dict[str, str] = {}
    for item in scope.get("candidate_components", []):
        if not isinstance(item, dict):
            raise BuildError(f"Invalid candidate component in build scope: {item!r}")
        component_id, disk = item.get("id"), item.get("disk")
        if not isinstance(component_id, str) or disk not in result or component_id in expected or component_id in candidates:
            raise BuildError(f"Invalid or duplicate candidate component in build scope: {item!r}")
        if item.get("status") != "candidate":
            raise BuildError(f"Candidate component must have status='candidate': {item!r}")
        candidates[component_id] = disk
    found: set[str] = set()
    for path in sorted(SOURCE_DIR.glob("*.json")):
        if path.name in {BASELINE_PATH.name, SCOPE_PATH.name}:
            continue
        value = read_json(path)
        if value.get("schema") != "valis2.manual_patch_set.v1":
            continue
        disk = value.get("disk")
        if disk not in result:
            raise BuildError(f"{path}: disk must be one of A..G")
        component_id = value.get("component_id")
        if component_id in candidates:
            if value.get("complete") is True:
                raise BuildError(
                    f"{path}: candidate {component_id} is complete but has not been promoted into build scope"
                )
            continue
        if component_id not in expected:
            raise BuildError(f"{path}: unknown component_id {component_id!r}")
        if expected[component_id] != disk:
            raise BuildError(f"{path}: component {component_id} belongs to disk {expected[component_id]}")
        if component_id in found:
            raise BuildError(f"Duplicate component table for {component_id}")
        rows = value.get("rows")
        is_graphics_source = value.get("build_mode") == "png-graphics"
        if not isinstance(rows, list) or (not rows and not is_graphics_source):
            raise BuildError(f"{path}: patch table has no rows")
        if is_graphics_source and not isinstance(value.get("asset_inputs"), dict):
            raise BuildError(f"{path}: PNG graphics build mode requires asset_inputs")
        if value.get("complete") is not True:
            raise BuildError(f"{path}: component is not explicitly marked complete")
        source_docs = value.get("source_docs")
        if not isinstance(source_docs, list) or not source_docs or any(
            not (
                (isinstance(item, str) and item.strip())
                or (isinstance(item, dict) and any(
                    isinstance(item.get(key), str) and item[key].strip()
                    for key in ("path", "file")
                ))
            )
            for item in source_docs
        ):
            raise BuildError(f"{path}: source_docs must list at least one evidence source")
        result[disk].append((path, value))
        found.add(component_id)
    missing_components = sorted(set(expected) - found)
    if missing_components:
        raise BuildError("Missing complete source table(s): " + ", ".join(missing_components))
    missing = [disk for disk, tables in result.items() if not tables]
    if missing:
        raise BuildError("No complete manual patch table for disk(s): " + ", ".join(missing))
    return result


def validate_table_baseline(
    table_path: Path, table: dict[str, Any], disk: str, baseline: dict[str, Any]
) -> None:
    declared = table.get("baseline")
    if not isinstance(declared, dict):
        raise BuildError(f"{table_path}: missing baseline identity")
    declared_size = declared.get("size_bytes", declared.get("bytes"))
    if declared_size != baseline.get("size_bytes"):
        raise BuildError(f"{table_path}: {disk} baseline size differs from source-baseline.json")
    if declared.get("sha256") != baseline.get("sha256"):
        raise BuildError(f"{table_path}: {disk} baseline sha256 differs from source-baseline.json")


def table_writes(table_path: Path, table: dict[str, Any]) -> list[PayloadWrite]:
    component = table.get("component")
    if not isinstance(component, str) or not component.strip():
        raise BuildError(f"{table_path}: component name is required")
    rows = table["rows"]
    writes: list[PayloadWrite] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise BuildError(f"{table_path}: row {index} is not an object")
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id.strip() or row_id in seen_ids:
            raise BuildError(f"{table_path}: row {index} has an empty or duplicate id")
        seen_ids.add(row_id)
        if row.get("status") != "confirmed":
            raise BuildError(f"{table_path}:{row_id}: status is not confirmed")
        evidence_ref = row.get("evidence_ref")
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise BuildError(f"{table_path}:{row_id}: missing evidence_ref")
        try:
            offset = int(str(row.get("offset", "")), 0)
        except ValueError as exc:
            raise BuildError(f"{table_path}:{row_id}: invalid raw offset") from exc
        old = hex_bytes(row.get("old_hex"), table=table_path, row_id=row_id, field="old_hex")
        new = hex_bytes(row.get("new_hex"), table=table_path, row_id=row_id, field="new_hex")
        writes.append(PayloadWrite(
            disk_offset=offset,
            expected_old=old,
            replacement=new,
            component=component,
            row_id=row_id,
            evidence_ref=evidence_ref,
            review_status="confirmed",
        ))
    return writes


def generate_kanji_rom(
    original_rom: bytes,
    source_identity: dict[str, Any],
    target_identity: dict[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    if len(original_rom) != 0x20000:
        raise BuildError(f"Original KANJI1.ROM must be 131072 bytes, got {len(original_rom)}")
    original_hash = sha256(original_rom)
    if (
        len(original_rom) != int(source_identity["size_bytes"])
        or original_hash != source_identity["sha256"]
    ):
        raise BuildError("Original KANJI1.ROM does not match the recorded source identity")
    if not KANJI_MAP_PATH.is_file():
        raise BuildError(f"Missing 558-character glyph reference: {KANJI_MAP_PATH}")
    target_rom = bytearray(original_rom)
    checked = 0
    tokens: set[str] = set()
    offsets: set[int] = set()
    with KANJI_MAP_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        needed = {"char", "token_hex", "rom_file_offset_hex", "glyph_bytes_hex"}
        if not needed.issubset(set(reader.fieldnames or [])):
            raise BuildError("Glyph reference is missing required literal fields")
        for row in reader:
            try:
                offset = int(row["rom_file_offset_hex"], 16)
                glyph = bytes.fromhex(row["glyph_bytes_hex"])
                token = bytes.fromhex(row["token_hex"]).hex()
            except (TypeError, ValueError) as exc:
                raise BuildError(f"Invalid glyph reference row for {row.get('char')!r}") from exc
            if len(glyph) != 32 or offset < 0 or offset + 32 > len(target_rom):
                raise BuildError(f"Invalid 16x16 glyph record for {row.get('char')!r}")
            if token in tokens or offset in offsets:
                raise BuildError(f"Duplicate glyph token or ROM offset for {row.get('char')!r}")
            target_rom[offset:offset + 32] = glyph
            tokens.add(token)
            offsets.add(offset)
            checked += 1
    if checked != 558:
        raise BuildError(f"Expected 558 explicit glyph records, found {checked}")
    generated = bytes(target_rom)
    generated_hash = sha256(generated)
    if (
        len(generated) != int(target_identity["size_bytes"])
        or generated_hash != target_identity["sha256"]
    ):
        raise BuildError(
            "Generated Korean KANJI1.ROM does not match the recorded target identity; "
            "check the original ROM and glyph-assignment-reference.csv"
        )
    return generated, {
        "source_size_bytes": len(original_rom),
        "source_sha256": original_hash,
        "generated_file": target_identity["file"],
        "generated_size_bytes": len(generated),
        "generated_sha256": generated_hash,
        "glyph_rows_checked": checked,
        "glyph_tokens_checked": len(tokens),
        "glyph_rom_offsets_checked": len(offsets),
    }


def ensure_output_not_inside_inputs(
    output: Path, original_dir: Path, kanji_original_rom: Path
) -> None:
    resolved = output.resolve()
    for source in (original_dir.resolve(), kanji_original_rom.resolve()):
        if resolved == source or source in resolved.parents:
            raise BuildError(f"Output directory must not be inside an input path: {source}")


def discover_inputs(
    original_dir: Path, disk_baselines: dict[str, Any],
    kanji_identity: dict[str, Any], explicit_kanji: Path | None,
) -> tuple[dict[str, Path], Path]:
    if not original_dir.is_dir():
        raise BuildError(f"Original input directory is missing: {original_dir}")
    identities = {disk: (int(item["size_bytes"]), str(item["sha256"]))
                  for disk, item in disk_baselines.items()}
    kanji_key = (int(kanji_identity["size_bytes"]), str(kanji_identity["sha256"]))
    matches: dict[str, list[Path]] = {disk: [] for disk in identities}
    kanji_matches: list[Path] = []
    sizes = {size for size, _digest in identities.values()} | {kanji_key[0]}
    for path in original_dir.iterdir():
        if not path.is_file() or path.stat().st_size not in sizes:
            continue
        identity = (path.stat().st_size, sha256(path.read_bytes()))
        for disk, expected in identities.items():
            if identity == expected:
                matches[disk].append(path)
        if identity == kanji_key:
            kanji_matches.append(path)
    missing = [disk for disk, paths in matches.items() if not paths]
    duplicates = [disk for disk, paths in matches.items() if len(paths) > 1]
    if missing or duplicates:
        raise BuildError(f"Cannot identify unique original D88 files in {original_dir}: "
                         f"missing={missing}, duplicates={duplicates}")
    if explicit_kanji is not None:
        kanji_path = explicit_kanji.expanduser().resolve()
        if not kanji_path.is_file() or (kanji_path.stat().st_size, sha256(kanji_path.read_bytes())) != kanji_key:
            raise BuildError(f"Specified original KANJI1 ROM does not match its recorded identity: {kanji_path}")
    elif len(kanji_matches) == 1:
        kanji_path = kanji_matches[0]
    else:
        raise BuildError(f"Cannot identify one original KANJI1 ROM in {original_dir}: found {len(kanji_matches)} matches")
    return {disk: paths[0] for disk, paths in matches.items()}, kanji_path


def ensure_output_is_owned_build(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_dir():
        raise BuildError(f"Output path exists but is not a directory: {path}")
    files = {item.relative_to(path).as_posix() for item in path.rglob("*") if item.is_file()}
    if not files or files == {".gitkeep"}:
        return
    log_path = path / "build-log.json"
    if "build-log.json" not in files:
        raise BuildError(f"Refusing to overwrite an unrecognized output directory: {path}")
    try:
        log = json.loads(log_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"Refusing to overwrite an unreadable output manifest: {log_path}") from exc
    if log.get("schema") != "valis2.manual_reproduction_build.v2":
        raise BuildError(f"Refusing to overwrite outputs from another build: {path}")


def build(
    *, original_dir: Path, kanji_original_rom: Path | None, output_dir: Path
) -> dict[str, Any]:
    original_dir = original_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    ensure_output_is_owned_build(output_dir)
    source_baseline = load_baseline()
    baseline = source_baseline["disks"]
    tables_by_disk = load_patch_tables()
    kanji_original_identity = source_baseline.get("kanji1_source")
    if not isinstance(kanji_original_identity, dict):
        raise BuildError("Source baseline must identify the Japanese KANJI1 source ROM")
    disk_paths, kanji_original_rom = discover_inputs(
        original_dir, baseline, kanji_original_identity, kanji_original_rom
    )
    ensure_output_not_inside_inputs(output_dir, original_dir, kanji_original_rom)
    kanji_original_data = kanji_original_rom.read_bytes()
    if (
        len(kanji_original_data) != int(kanji_original_identity["size_bytes"])
        or sha256(kanji_original_data) != kanji_original_identity["sha256"]
    ):
        raise BuildError("Original KANJI1.ROM does not match the recorded source identity")
    kanji_target_data, kanji_report = generate_kanji_rom(
        kanji_original_data,
        kanji_original_identity,
        source_baseline["kanji1"],
    )
    kanji_ips_data = encode_ips(kanji_original_data, kanji_target_data)
    if apply_ips(kanji_original_data, kanji_ips_data) != kanji_target_data:
        raise BuildError("Generated KANJI1 IPS does not reproduce the generated Korean KANJI1.ROM")

    output_dir.mkdir(parents=True, exist_ok=True)
    disk_reports: dict[str, Any] = {}
    graphics_reports: list[dict[str, Any]] = []
    prepared: dict[str, tuple[D88Image, Path, Path, bytes]] = {}
    for disk in "ABCDEFG":
        identity = baseline[disk]
        source_path = disk_paths[disk]
        image = D88Image.read_verified(
            source_path,
            expected_size=int(identity["size_bytes"]),
            expected_sha256=str(identity["sha256"]),
        )
        source_data = source_path.read_bytes()
        writes: list[PayloadWrite] = []
        table_reports = []
        disk_graphics = []
        for table_path, table in tables_by_disk[disk]:
            validate_table_baseline(table_path, table, disk, identity)
            if table.get("build_mode") != "png-graphics":
                writes.extend(table_writes(table_path, table))
            table_reports.append({
                "path": str(table_path.relative_to(ROOT)),
                "sha256": sha256(table_path.read_bytes()),
                "component": table["component"],
                "rows": len(table["rows"]),
                "build_mode": table.get("build_mode", "raw-patch-table"),
            })

        if disk == "A":
            title_table = next(
                table for _path, table in tables_by_disk[disk]
                if table.get("component_id") == "a_title_cg"
            )
            assets = build_disk_a_resources(source_data, title_table)
            for asset in assets:
                evidence = "; ".join(path.relative_to(ROOT).as_posix() for path in asset.input_files)
                writes.extend(write_spans(
                    asset,
                    source_data,
                    component=title_table["component"],
                    evidence_ref=f"{evidence}; docs/integrated-source-analysis.md#37",
                ))
            disk_graphics.extend(resource_report(assets, sha256))

        if disk == "B":
            battle_table = next(
                table for _path, table in tables_by_disk[disk]
                if table.get("component_id") == "b_battle_cg"
            )
            asset = build_disk_b_battle_resource(source_data, battle_table)
            evidence = "; ".join(path.relative_to(ROOT).as_posix() for path in asset.input_files)
            writes.extend(write_spans(
                asset,
                source_data,
                component=battle_table["component"],
                evidence_ref=f"{evidence}; docs/integrated-source-analysis.md#37",
            ))
            disk_graphics.extend(resource_report((asset,), sha256))

        graphics_reports.extend(disk_graphics)
        applied = image.apply_payload_writes(writes)
        output_path = output_dir / "d88" / f"Valis2_KOR_Disk_{disk}.d88"
        ips_path = output_dir / "ips" / f"Valis2_KOR_Disk_{disk}.ips"
        output_data = image.to_bytes()
        # Parse the complete image before any build outputs are replaced.
        parsed_output = D88Image.parse(output_data)
        ips_data = encode_ips(source_data, output_data)
        if apply_ips(source_data, ips_data) != output_data:
            raise BuildError(f"Disk {disk}: generated IPS does not reproduce the table-built D88")
        prepared[disk] = (image, output_path, ips_path, ips_data)
        disk_reports[disk] = {
            "input": {
                "file": source_path.name,
                "size_bytes": identity["size_bytes"],
                "sha256": sha256(source_path.read_bytes()),
            },
            "tables": table_reports,
            "graphics_resources": disk_graphics,
            "writes": len(applied),
            "changed_bytes": sum(item.changed_bytes for item in applied),
            "output": {
                "path": str(output_path),
                "size_bytes": len(output_data),
                "sha256": sha256(output_data),
            },
            "ips": {
                "path": str(ips_path),
                "size_bytes": len(ips_data),
                "sha256": sha256(ips_data),
                "reapplied_matches_output": True,
            },
            "sector_count": len(parsed_output.sectors),
        }

    # All seven source images and every declared write are checked before any
    # D88 output reaches disk.
    for image, output_path, ips_path, ips_data in prepared.values():
        image.save(output_path)
        ips_path.parent.mkdir(parents=True, exist_ok=True)
        ips_path.write_bytes(ips_data)

    kanji_out = output_dir / "kanji" / "KANJI1.ROM"
    kanji_out.parent.mkdir(parents=True, exist_ok=True)
    kanji_out.write_bytes(kanji_target_data)
    kanji_report["output_path"] = str(kanji_out)
    kanji_report["output_sha256"] = sha256(kanji_out.read_bytes())
    kanji_ips_path = output_dir / "ips" / "KANJI1.ips"
    kanji_ips_path.parent.mkdir(parents=True, exist_ok=True)
    kanji_ips_path.write_bytes(kanji_ips_data)
    kanji_report["original_input"] = {
        "file": kanji_original_rom.name,
        "size_bytes": len(kanji_original_data),
        "sha256": sha256(kanji_original_data),
    }
    kanji_report["ips"] = {
        "path": str(kanji_ips_path),
        "size_bytes": len(kanji_ips_data),
        "sha256": sha256(kanji_ips_data),
        "reapplied_matches_output": True,
    }

    result = {
        "schema": "valis2.manual_reproduction_build.v2",
        "source_baseline": str(BASELINE_PATH.relative_to(ROOT)),
        "build_scope": str(SCOPE_PATH.relative_to(ROOT)),
        "patch_source_dir": str(SOURCE_DIR.relative_to(ROOT)),
        "kanji_reference": str(KANJI_MAP_PATH.relative_to(ROOT)),
        "kanji_reference_sha256": sha256(KANJI_MAP_PATH.read_bytes()),
        "graphics_source_dir": "source/graphics",
        "graphics_resources": graphics_reports,
        "output_dir": str(output_dir),
        "disks": disk_reports,
        "kanji1": kanji_report,
        "status": "complete",
    }
    log_path = output_dir / "build-log.json"
    log_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="valis2-manual-build",
        description="Build Valis II images and generate Korean KANJI1.ROM from the original ROM and the glyph table.",
    )
    parser.add_argument(
        "--original-dir", type=Path, default=IMPORT_DIR,
        help="Directory containing Japanese source D88 A-G (default: import/)",
    )
    parser.add_argument(
        "--kanji-original-rom", type=Path,
        help="Optional explicit path to the original 128 KiB KANJI1 ROM",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Build output directory")
    args = parser.parse_args(argv)
    try:
        result = build(
            original_dir=Path(args.original_dir),
            kanji_original_rom=args.kanji_original_rom,
            output_dir=args.out,
        )
    except (BuildError, OSError, ValueError) as exc:
        parser.error(str(exc))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
