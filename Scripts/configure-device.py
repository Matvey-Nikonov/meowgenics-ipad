#!/usr/bin/env python3
"""Merge native GPU settings on a closed app, keeping backups and all saves."""
import argparse
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def merge(text, profile, separator):
    values = {}
    for line in profile.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split(None if separator == " " else separator, 1)
        values[key.strip()] = value.strip()
    lines = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        key = stripped.split(None if separator == " " else separator, 1)[0].strip() if stripped else ""
        if stripped.startswith("#") or key not in values:
            lines.append(line)
    result = "".join(lines)
    if result and not result.endswith(("\n", "\r")):
        result += "\n"
    joiner = " = " if separator == "=" else " "
    return result + "".join(f"{key}{joiner}{value}\n" for key, value in values.items())


def configuration_paths(listing):
    # Only accept paths from a successful, structurally valid device response.
    if listing.get("info", {}).get("outcome") != "success":
        raise ValueError("Device file listing did not succeed")
    files = listing["result"]["files"]
    paths = []
    for entry in files:
        relative = PurePosixPath(entry["relativePath"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unexpected device path")
        paths.append(relative)
    game = [p for p in paths if p.parts[:3] == ("wine", "drive_c", "users") and
            p.match("wine/drive_c/users/*/AppData/Roaming/Glaiel Games/Mewgenics/*/settings.txt")]
    return PurePosixPath("madeira.cfg") in paths, sorted(set(game))


def configure(device, bundle, cache):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
    backup = cache / "diagnostics/madeira" / ("configure-" + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    domain = ["--device", device, "--domain-type", "appDataContainer", "--domain-identifier", bundle]
    listing = backup / "files.json"
    subprocess.run(["xcrun", "devicectl", "device", "info", "files", *domain,
                    "--subdirectory", "Documents", "--recurse", "--json-output", str(listing)],
                   check=True, stdout=subprocess.DEVNULL)
    has_runtime, settings = configuration_paths(json.loads(listing.read_text()))
    targets = [(PurePosixPath("madeira.cfg"), has_runtime, ROOT / "Runtime/Profiles/zink.cfg", "=")]
    targets += [(p, True, ROOT / "Runtime/Profiles/native-settings.txt", " ") for p in settings]
    manifest = []
    for index, (relative, exists, profile, separator) in enumerate(targets):
        before = backup / f"{index}-before.txt"
        after = backup / f"{index}-after.txt"
        remote = "Documents/" + str(relative)
        if exists:
            subprocess.run(["xcrun", "devicectl", "device", "copy", "from", *domain,
                            "--source", remote, "--destination", str(before)], check=True)
            with before.open(newline="") as file:
                current = file.read()
        else:
            current = ""
        with after.open("w", newline="") as file:
            file.write(merge(current, profile.read_text(), separator))
        # Record restoration information before making the device change.
        manifest.append({"device_path": remote, "original_existed": exists,
                         "before": before.name if exists else None, "after": after.name})
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        subprocess.run(["xcrun", "devicectl", "device", "copy", "to", *domain,
                        "--source", str(after), "--destination", remote], check=True)
    print(f"Configured Zink/native output and {len(settings)} game settings file(s). Backups: {backup}")
    if not settings:
        print("After the first successful game load, close it and run configure again to apply the 120 FPS game settings.")
    print("No saves changed. Settings apply at the next launch; this command does not launch or restart.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    configure(args.device, args.bundle, args.cache)
