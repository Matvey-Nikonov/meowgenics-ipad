#!/usr/bin/env python3
"""Prepare a diagnostic preset without replacing unrelated runtime settings."""
from pathlib import Path
import argparse


def configure(text: str, mode: str) -> str:
    if mode not in ("off", "stats", "full"):
        raise ValueError(f"Unknown diagnostic mode: {mode}")
    values = {
        "env.MADEIRA_VULKAN_DIAGNOSTICS": "1" if mode == "full" else "0",
        "env.MADEIRA_DEVICE_STATS": "0" if mode == "off" else "1",
        "env.MADEIRA_UI_LOG_IDLE": "1",
        "env.MADEIRA_DEBUG_VERBOSE": "0",
    }
    lines = []
    for line in text.splitlines(keepends=True):
        key = line.split("=", 1)[0].strip()
        if key not in values:
            lines.append(line)
    result = "".join(lines)
    if result and not result.endswith(("\r", "\n")):
        result += "\n"
    return result + "".join(f"{key} = {value}\n" for key, value in values.items())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("mode", choices=("off", "stats", "full"))
    args = parser.parse_args()
    with args.source.open(newline="") as file:
        result = configure(file.read(), args.mode)
    with args.destination.open("w", newline="") as file:
        file.write(result)
