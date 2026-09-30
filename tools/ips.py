"""Small IPS encoder and verifier for same-size disk image patches."""

from __future__ import annotations


class IpsError(ValueError):
    """An IPS patch is malformed or cannot represent the requested change."""


def encode_ips(source: bytes, target: bytes) -> bytes:
    """Encode only differing byte runs; image size must remain unchanged."""

    if len(source) != len(target):
        raise IpsError("IPS source and target lengths must match")
    if len(source) > 0x1000000:
        raise IpsError("IPS cannot address an input larger than 16 MiB")
    output = bytearray(b"PATCH")
    offset = 0
    while offset < len(source):
        if source[offset] == target[offset]:
            offset += 1
            continue
        start = offset
        offset += 1
        while offset < len(source) and source[offset] != target[offset] and offset - start < 0xFFFF:
            offset += 1
        length = offset - start
        if start == 0x454F46:
            raise IpsError("IPS data record collides with the EOF marker")
        output.extend(start.to_bytes(3, "big"))
        output.extend(length.to_bytes(2, "big"))
        output.extend(target[start:offset])
    output.extend(b"EOF")
    return bytes(output)


def apply_ips(source: bytes, patch: bytes) -> bytes:
    """Apply a data-record-only IPS patch and preserve source length."""

    if not patch.startswith(b"PATCH") or not patch.endswith(b"EOF"):
        raise IpsError("IPS must start with PATCH and end with EOF")
    data = bytearray(source)
    cursor = 5
    end = len(patch) - 3
    while cursor < end:
        if cursor + 5 > end:
            raise IpsError("truncated IPS record header")
        offset = int.from_bytes(patch[cursor:cursor + 3], "big")
        length = int.from_bytes(patch[cursor + 3:cursor + 5], "big")
        cursor += 5
        if length == 0:
            if cursor + 3 > end:
                raise IpsError("truncated IPS RLE record")
            length = int.from_bytes(patch[cursor:cursor + 2], "big")
            value = patch[cursor + 2]
            cursor += 3
            payload = bytes((value,)) * length
        else:
            if cursor + length > end:
                raise IpsError("truncated IPS payload")
            payload = patch[cursor:cursor + length]
            cursor += length
        if not length or offset + length > len(data):
            raise IpsError("IPS record is empty or outside the source image")
        data[offset:offset + length] = payload
    if cursor != end:
        raise IpsError("unexpected bytes before IPS EOF")
    return bytes(data)
