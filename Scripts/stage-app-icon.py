#!/usr/bin/env python3
"""Stage a private icon or generate a neutral icon; no game artwork is included."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import zlib


def placeholder() -> bytes:
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    # An original geometric tablet symbol, generated without bundled media.
    rows = []
    for y in range(1024):
        row = bytearray([0])
        for x in range(1024):
            outline = 208 <= x < 816 and 272 <= y < 752 and not (244 <= x < 780 and 308 <= y < 716)
            row.extend((220, 230, 243) if outline else (33, 45, 65))
        rows.append(row)
    header = struct.pack(">IIBBBBB", 1024, 1024, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


def stage(destination: Path, private_icon: Path | None = None):
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "Contents.json").write_text(json.dumps({"info": {"author": "xcode", "version": 1}}) + "\n")
    appicon = destination / "AppIcon.appiconset"
    appicon.mkdir(exist_ok=True)
    image = appicon / "AppIcon.png"
    if private_icon:
        header = private_icon.read_bytes()[:33]
        if (len(header) < 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or
                struct.unpack(">II", header[16:24]) != (1024, 1024)):
            raise ValueError("MEWGENICS_APP_ICON must be a 1024x1024 PNG")
        shutil.copy2(private_icon, image)
    else:
        image.write_bytes(placeholder())
    # The catalog is generated output; discard stale icon images from old builds.
    for old in appicon.glob("*.png"):
        if old != image:
            old.unlink()
    (appicon / "Contents.json").write_text(json.dumps({
        "images": [{"filename": "AppIcon.png", "idiom": "universal", "platform": "ios", "size": "1024x1024"}],
        "info": {"author": "xcode", "version": 1}}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--icon", type=Path)
    args = parser.parse_args()
    stage(args.destination, args.icon)
