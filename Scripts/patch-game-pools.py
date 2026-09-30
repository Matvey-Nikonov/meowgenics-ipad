#!/usr/bin/env python3
"""Stage the supplied Mewgenics 1.1.b21239 with smaller allocator reserves.

The original is never modified. Only the reserve-size immediate in verified
pool constructors changes; commit sizes, object layouts and growth code stay
intact. Refuse every unrecognized game build rather than guessing offsets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

EXPECTED_SHA256 = "4127cd6a792ae528bca6f65a8873dd61789591937d87656c2b586a5e30eb77ea"
POOL_COUNT = 2246
RESERVE_BYTES = 16 * 1024 * 1024


def patch(source: Path, destination: Path, expand_canvas: bool = False):
    original = source.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"Unsupported game executable SHA-256: {digest}")
    if source.resolve() == destination.resolve():
        raise ValueError("Destination must differ from the original executable")
    data = bytearray(original)
    # PE .text: RVA 0x1000, file offset 0x400, length 0xe3d800.
    # Each initializer calls the same pool constructor at RVA 0x9693d0,
    # then sets element size, reserve size and initial growth count.
    sites = []
    signed = lambda offset: struct.unpack_from("<i", original, offset)[0]
    pattern = rb"\x48\xc7\x05....\x00\x00\x00\x40"
    for match in re.finditer(pattern, original[0x400:0xe3dc00], re.DOTALL):
        offset = match.start() + 0x400
        start = offset - 27
        rva = start + 0xc00
        obj = rva + 11 + signed(start + 7)
        checks = [
            original[start:start + 7] == bytes.fromhex("48 83 ec 28 48 8d 0d"),
            original[start + 11] == 0xe8,
            rva + 16 + signed(start + 12) == 0x9693d0,
            original[start + 16:start + 19] == bytes.fromhex("48 c7 05"),
            original[start + 38:start + 41] == bytes.fromhex("48 c7 05"),
            original[start + 49:start + 54] == bytes.fromhex("48 83 c4 28 c3"),
            rva + 27 + signed(start + 19) == obj + 16,
            rva + 38 + signed(start + 30) == obj,
            rva + 49 + signed(start + 41) == obj + 8,
            signed(start + 45) == 1,
            0 < signed(start + 23) < RESERVE_BYTES,
            0x12e7000 <= obj < 0x14233b8 - 0xa0,
        ]
        if not all(checks):
            raise ValueError(f"Unexpected allocator initializer at RVA {rva:#x}")
        struct.pack_into("<I", data, offset + 7, RESERVE_BYTES)
        sites.append({"rva": hex(rva + 27), "pool_rva": hex(obj)})
    if len(sites) != POOL_COUNT:
        raise ValueError(f"Expected {POOL_COUNT} pools, found {len(sites)}")
    if expand_canvas:
        # The engine already supports a proportional, expanded logical canvas.
        # Its constructor locks that path off at object+0xd9f. Clearing only
        # that byte enables the full-window framebuffer, projection and shared
        # mouse conversion. At 4:3 the authored 1280x720 stays inside a
        # 1280x960 canvas (y=-120..840); no cropping or stretching is applied.
        aspect_offset = 0x7487ed
        expected = bytes.fromhex("66 c7 86 9f 0d 00 00 01 00")
        if original[aspect_offset:aspect_offset + len(expected)] != expected or original.count(expected) != 1:
            raise ValueError("Unexpected engine aspect-lock initializer")
        data[aspect_offset + 7] = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    manifest = {
        "original_sha256": digest,
        "patched_sha256": hashlib.sha256(data).hexdigest(),
        "original_reserve_bytes": 1024 * 1024 * 1024,
        "patched_reserve_bytes": RESERVE_BYTES,
        "pool_count": len(sites),
        "expanded_canvas": expand_canvas,
        "aspect_lock_rva": "0x7493ed" if expand_canvas else None,
        "sites": sites,
    }
    destination.with_suffix(".patch.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Staged {len(sites)} verified pool reserves at 16 MiB: {destination}")
    if expand_canvas:
        print("Enabled the engine's proportional expanded-canvas mode")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--expand-canvas", action="store_true", help="Enable the existing full-window canvas mode")
    args = parser.parse_args()
    patch(args.source, args.destination, args.expand_canvas)
