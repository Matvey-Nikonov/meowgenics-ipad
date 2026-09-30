#!/usr/bin/env python3
"""Host checks for safe configuration merge and source-generated icons."""
import json
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
config = runpy.run_path(str(ROOT / "Scripts/configure-device.py"))
icons = runpy.run_path(str(ROOT / "Scripts/stage-app-icon.py"))


class SetupTools(unittest.TestCase):
    def test_build_script_without_private_icon(self):
        # Exercise the real shell entry point; only Xcode/signing are mocked.
        # In particular this covers macOS Bash 3 with set -u and no icon option.
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as temp:
            base = Path(temp)
            repo, cache, commands = base / "repo", base / "cache", base / "commands"
            (repo / "Scripts").mkdir(parents=True)
            for name in ["madeira-runtime.sh", "stage-app-icon.py"]:
                shutil.copy2(ROOT / "Scripts" / name, repo / "Scripts" / name)
            native = cache / "sources/Madeira"
            (native / "build").mkdir(parents=True)
            (native / "build/stage-licenses.sh").write_text("#!/bin/sh\nexit 0\n")
            commands.mkdir()
            (commands / "xcodebuild").write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPTURE_ARGS\"\n")
            (commands / "codesign").write_text("#!/bin/sh\nif [ \"$1\" = -d ]; then\ncat <<'PLIST'\n"
                "<?xml version=\"1.0\"?><plist version=\"1.0\"><dict><key>get-task-allow</key><true/>"
                "<key>com.apple.developer.kernel.increased-memory-limit</key><true/></dict></plist>\nPLIST\nfi\n")
            for command in commands.iterdir():
                command.chmod(0o755)
            env = dict(os.environ, MEWGENICS_CACHE=str(cache), DEVELOPMENT_TEAM="TESTTEAM01",
                       MEWGENICS_BUNDLE_ID="org.test.mewgenics", MEWGENICS_APP_ICON="",
                       PATH=str(commands) + os.pathsep + os.environ["PATH"],
                       CAPTURE_ARGS=str(base / "arguments.txt"))
            env.pop("DEVICE_UDID", None)
            subprocess.run(["/bin/bash", str(repo / "Scripts/madeira-runtime.sh"), "build"],
                           check=True, env=env, capture_output=True)
            args = (base / "arguments.txt").read_text().splitlines()
            self.assertIn("DEVELOPMENT_TEAM=TESTTEAM01", args)
            self.assertIn("PRODUCT_BUNDLE_IDENTIFIER=org.test.mewgenics", args)
            self.assertIn("generic/platform=iOS", args)
            self.assertTrue((native / "app/Madeira/Assets.xcassets/AppIcon.appiconset/AppIcon.png").is_file())

    def test_device_configuration_preserves_saves_and_backups(self):
        settings = "Documents/wine/drive_c/users/mobile/AppData/Roaming/Glaiel Games/Mewgenics/example/settings.txt"
        files = {"Documents/madeira.cfg": "pool = 123\ncustom = retain\n",
                 settings: "render_scale 0.5\nMasterVolume 71\n",
                 settings.replace("settings.txt", "campaign.sav"): "untouched save"}
        writes = []
        def device_command(command, **kwargs):
            if command[3:5] == ["info", "files"]:
                Path(command[command.index("--json-output") + 1]).write_text(json.dumps({
                    "info": {"outcome": "success"}, "result": {"files": [
                        {"relativePath": name.removeprefix("Documents/")} for name in files]}}))
            elif command[3:5] == ["copy", "from"]:
                Path(command[command.index("--destination") + 1]).write_text(files[command[command.index("--source") + 1]])
            elif command[3:5] == ["copy", "to"]:
                destination = command[command.index("--destination") + 1]
                writes.append(destination)
                files[destination] = Path(command[command.index("--source") + 1]).read_text()
            else:
                self.fail(f"Unexpected device operation: {command[:5]}")
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as temp:
            with patch.object(config["subprocess"], "run", side_effect=device_command):
                config["configure"]("test-device", "org.example.test", Path(temp))
            manifest = next(Path(temp).rglob("manifest.json"))
            entries = json.loads(manifest.read_text())
            self.assertEqual(len(entries), 2)
            self.assertEqual((manifest.parent / entries[0]["before"]).read_text(), "pool = 123\ncustom = retain\n")
            self.assertEqual(set(writes), {"Documents/madeira.cfg", settings})
            self.assertIn("custom = retain", files["Documents/madeira.cfg"])
            self.assertIn("MasterVolume 71", files[settings])
            self.assertIn("render_scale 1", files[settings])
            self.assertEqual(files[settings.replace("settings.txt", "campaign.sav")], "untouched save")

    def test_merge_preserves_unknown_settings(self):
        original = "# comment\r\nrender_scale 0.5\r\nvolume 73\r\nrender_scale\t0.25\r\ncustom value=other"
        result = config["merge"](original, "# defaults\nrender_scale 1\nvsync false\n", " ")
        self.assertEqual(result, "# comment\r\nvolume 73\r\ncustom value=other\nrender_scale 1\nvsync false\n")
        self.assertEqual(config["merge"](result, "render_scale 1\nvsync false", " "), result)
        self.assertEqual(config["merge"]("custom = a=b\n", "pool = 384", "="), "custom = a=b\npool = 384\n")

    def test_device_discovery_is_narrow(self):
        path = "wine/drive_c/users/mobile/AppData/Roaming/Glaiel Games/Mewgenics/example/settings.txt"
        listing = {"info": {"outcome": "success"}, "result": {"files": [
            {"relativePath": p} for p in ["madeira.cfg", path, "wine/drive_c/Mewgenics/settings.txt", "private.sav"]]}}
        exists, settings = config["configuration_paths"](listing)
        self.assertTrue(exists)
        self.assertEqual([str(p) for p in settings], [path])
        listing["result"]["files"].append({"relativePath": "../madeira.cfg"})
        with self.assertRaises(ValueError):
            config["configuration_paths"](listing)
        with self.assertRaises(ValueError):
            config["configuration_paths"]({"info": {"outcome": "failure"}})

    def test_icon_default_and_private_override(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as temp:
            root = Path(temp)
            destination = root / "Assets.xcassets"
            icons["stage"](destination)
            image = destination / "AppIcon.appiconset/AppIcon.png"
            data = image.read_bytes()
            self.assertEqual(struct.unpack(">II", data[16:24]), (1024, 1024))
            contents = json.loads((image.parent / "Contents.json").read_text())
            self.assertEqual(contents["images"][0]["filename"], image.name)
            private = root / "private.png"
            private.write_bytes(data)
            stale = image.parent / "Mewgenics.png"
            stale.write_bytes(b"stale")
            icons["stage"](destination, private)
            self.assertEqual(image.read_bytes(), data)
            self.assertEqual(private.read_bytes(), data)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
