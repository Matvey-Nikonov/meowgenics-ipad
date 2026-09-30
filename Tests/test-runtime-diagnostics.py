#!/usr/bin/env python3
"""Ensure diagnostic presets cannot discard unrelated game/runtime settings."""
from pathlib import Path
import runpy
import unittest

configure = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                              "Scripts/configure-runtime-diagnostics.py"))["configure"]


class DiagnosticPresets(unittest.TestCase):
    def test_preserves_unrelated_configuration(self):
        untouched = ("# env.MADEIRA_VULKAN_DIAGNOSTICS = example\r\n"
                     "pool = 384\r\n"
                     "display.native = 1\r\n"
                     "env.GALLIUM_DRIVER = zink\r\n"
                     "custom = value=with=equals\r\n"
                     "\r\n")
        source = (" env.MADEIRA_VULKAN_DIAGNOSTICS = 1\r\n" + untouched +
                  "env.MADEIRA_VULKAN_DIAGNOSTICS=0\r\n"
                  "env.MADEIRA_DEVICE_STATS = 1")
        for mode in ("off", "stats", "full"):
            result = configure(source, mode)
            self.assertTrue(result.startswith(untouched))
            self.assertEqual(result, configure(result, mode))
            keys = [line.split("=", 1)[0].strip() for line in result.splitlines()
                    if not line.startswith("#")]
            self.assertEqual(keys.count("env.MADEIRA_VULKAN_DIAGNOSTICS"), 1)

    def test_modes_and_empty_file(self):
        for mode, gpu, stats in (("off", "0", "0"), ("stats", "0", "1"), ("full", "1", "1")):
            values = dict(line.split(" = ") for line in configure("", mode).splitlines())
            self.assertEqual(values["env.MADEIRA_VULKAN_DIAGNOSTICS"], gpu)
            self.assertEqual(values["env.MADEIRA_DEVICE_STATS"], stats)
            self.assertEqual(values["env.MADEIRA_DEBUG_VERBOSE"], "0")
            self.assertEqual(values["env.MADEIRA_UI_LOG_IDLE"], "1")

    def test_missing_newline_and_invalid_mode(self):
        self.assertTrue(configure("pool = 384", "off").startswith("pool = 384\n"))
        with self.assertRaises(ValueError):
            configure("pool = 384", "invalid")


if __name__ == "__main__":
    unittest.main()
