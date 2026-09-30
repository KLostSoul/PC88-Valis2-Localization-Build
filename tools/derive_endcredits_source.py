"""Transcribe the reviewed End Credits translation worksheet to raw bytes.

Each of the 26 translated groups is read in document order. The only text
encoding source is the explicit character/token lookup table. Control tokens
are literal markers in the worksheet; fullwidth spaces are retained as 81 40.
The generated patch rows cover only the documented End Credits payload sectors.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

from .d88 import D88Image


ROOT = Path(__file__).resolve().parents[1]
WORKSHEET = ROOT.parent / "Ending Credits" / "Valis2_EndCredits_Analysis_Translation_Worksheet_ControlCodes_2026-08-08.docx"
ANALYSIS = ROOT / "analysis" / "itemized" / "11_Valis2Project15_분석.md"
GLYPH_MAP = ROOT / "source" / "kanji" / "glyph-assignment-reference.csv"
BASELINE = ROOT / "source" / "manual-build" / "source-baseline.json"
OUTPUT = ROOT / "source" / "manual-build" / "disk-A__end-credits.json"

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
RAW_SEGMENTS = ((0x9B98, 0x238, 0), (0x9DE0, 0x400, 0x238), (0xA1F0, 0x2F0, 0x638))
STREAM_SIZE = 0x928
TRANSLATED_SIZE = 2265


class SourceError(ValueError):
    pass


def load_character_tokens() -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    with GLYPH_MAP.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            char = row["char"]
            token = bytes.fromhex(row["token_hex"])
            if char in result or len(token) != 2:
                raise SourceError(f"Duplicate or invalid glyph token row: {char!r}")
            result[char] = token
    if len(result) != 558:
        raise SourceError(f"Expected 558 explicit character/token rows, found {len(result)}")
    return result


def read_credit_rows() -> list[list[str]]:
    with zipfile.ZipFile(WORKSHEET) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    tables = document.findall(".//w:tbl", WORD_NS)
    if len(tables) <= 7:
        raise SourceError("Credits worksheet is missing translation table 7")
    rows: list[list[str]] = []
    for table_row in tables[7].findall("./w:tr", WORD_NS)[1:]:
        cells = [
            "".join(text.text or "" for text in cell.findall(".//w:t", WORD_NS))
            for cell in table_row.findall("./w:tc", WORD_NS)
        ]
        if len(cells) != 6:
            raise SourceError(f"Credits row has {len(cells)} cells, expected 6")
        rows.append(cells)
    if len(rows) != 26:
        raise SourceError(f"Expected 26 translated credit groups, found {len(rows)}")
    return rows


def encode_translation(text: str, char_tokens: dict[str, bytes]) -> bytes:
    output = bytearray()
    cursor = 0
    while cursor < len(text):
        if text.startswith("␠", cursor):
            output.extend(b"\x81\x40")
            cursor += 1
            continue
        control = re.match(r"\[([0-9A-Fa-f ]+)\]", text[cursor:])
        if control:
            output.extend(bytes.fromhex(control.group(1)))
            cursor += len(control.group(0))
            continue
        char = text[cursor]
        token = char_tokens.get(char)
        if token is not None:
            output.extend(token)
        else:
            try:
                output.extend(char.encode("cp932"))
            except UnicodeEncodeError as exc:
                raise SourceError(f"No explicit glyph or CP932 token for {char!r}") from exc
        cursor += 1
    return bytes(output)


def build_source(original_disk_a: Path) -> dict:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["disks"]["A"]
    image_data = original_disk_a.read_bytes()
    source_sha = hashlib.sha256(image_data).hexdigest()
    if len(image_data) != baseline["size_bytes"] or source_sha != baseline["sha256"]:
        raise SourceError("Disk A does not match the directly recorded Japanese source identity")
    image = D88Image.read_verified(
        original_disk_a,
        expected_size=baseline["size_bytes"],
        expected_sha256=baseline["sha256"],
    )

    char_tokens = load_character_tokens()
    segments = []
    payload = bytearray()
    for source_row, cells in enumerate(read_credit_rows(), 1):
        row_no, ram_range, section, _original, translated, notes = cells
        if int(row_no) != source_row:
            raise SourceError(f"Credits table row order mismatch at {source_row}: {row_no}")
        encoded = encode_translation(translated, char_tokens)
        start = len(payload)
        payload.extend(encoded)
        segments.append({
            "source_row": row_no,
            "ram_range": ram_range,
            "section": section,
            "translated_text": translated,
            "payload_start": start,
            "payload_end_exclusive": len(payload),
            "payload_bytes": len(encoded),
            "control_notes": notes,
            "evidence_ref": f"{WORKSHEET.relative_to(ROOT.parent).as_posix()}#table-7-row-{int(row_no) + 1}",
        })

    if len(payload) != TRANSLATED_SIZE or payload[-1:] != b"\xFF":
        raise SourceError(
            f"Translated stream must be {TRANSLATED_SIZE} bytes and end in FF; "
            f"got {len(payload)} bytes, tail={payload[-1:].hex()}"
        )
    if len(payload) > STREAM_SIZE:
        raise SourceError("Translated credits stream exceeds the documented payload extent")
    final_stream = bytes(payload) + bytes(STREAM_SIZE - len(payload))

    raw_rows = []
    for raw_offset, length, payload_start in RAW_SEGMENTS:
        sector = image.sector_at_payload(raw_offset, length)
        new_bytes = final_stream[payload_start:payload_start + length]
        if len(new_bytes) != length:
            raise SourceError("Credits scatter segment does not cover its declared D88 payload")
        payload_end = payload_start + length
        contributing_rows = [
            item["source_row"]
            for item in segments
            if item["payload_start"] < payload_end
            and item["payload_end_exclusive"] > payload_start
        ]
        first_table_row = int(contributing_rows[0]) + 1 if contributing_rows else None
        last_table_row = int(contributing_rows[-1]) + 1 if contributing_rows else None
        evidence = (
            f"{WORKSHEET.relative_to(ROOT.parent).as_posix()}#table-7-rows-"
            f"{first_table_row}-{last_table_row}; "
            f"{WORKSHEET.relative_to(ROOT.parent).as_posix()}#table-5; "
            f"{ANALYSIS.relative_to(ROOT.parent).as_posix()}#section-4; "
            f"raw CHRN {sector.chrn}"
        )
        if payload_end > len(payload):
            evidence += "; final 79-byte zero fill per section 4"
        raw_rows.append({
            "id": f"A-CREDITS-{raw_offset:05X}",
            "offset": f"0x{raw_offset:05X}",
            "old_hex": image_data[raw_offset:raw_offset + length].hex(" ").upper(),
            "new_hex": new_bytes.hex(" ").upper(),
            "evidence_ref": evidence,
            "status": "confirmed",
        })

    return {
        "schema": "valis2.manual_patch_set.v1",
        "disk": "A",
        "component_id": "a_end_credits",
        "component": "end_credits_repacked_stream",
        "complete": True,
        "baseline": baseline,
        "source_docs": [
            WORKSHEET.relative_to(ROOT.parent).as_posix(),
            ANALYSIS.relative_to(ROOT.parent).as_posix(),
        ],
        "layout": {
            "stream_ram_start": "0xC9C8",
            "stream_ram_end_inclusive": "0xD2EF",
            "translated_stream_bytes": len(payload),
            "terminator_ram": "0xD2A0",
            "zero_fill_ram_start": "0xD2A1",
            "zero_fill_bytes": 79,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "segments": segments,
        },
        "rows": raw_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create explicit raw rows for End Credits from its direct worksheet.")
    parser.add_argument("--disk-a", type=Path, required=True, help="Japanese source Disk A")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    value = build_source(args.disk_a.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.out.resolve()),
        "segments": len(value["layout"]["segments"]),
        "patch_rows": len(value["rows"]),
        "translated_stream_bytes": value["layout"]["translated_stream_bytes"],
        "terminator": value["layout"]["terminator_ram"],
        "zero_fill_bytes": value["layout"]["zero_fill_bytes"],
        "payload_sha256": value["layout"]["payload_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
