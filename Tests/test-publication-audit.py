#!/usr/bin/env python3
"""Publication guard regression tests; fixtures remain under the caller's TMPDIR."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "Scripts/audit-publication.py"
HOOK = ROOT / ".githooks/pre-push"
spec = importlib.util.spec_from_file_location("publication_audit", AUDIT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicationAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="publication-audit-", dir=os.environ["TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Publication Test")
        self.git("config", "user.email", "publication@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("README.md", b"Text-only project.\n")
        self.commit()

    def git(self, *args, input_data=None):
        return subprocess.run(["git", *args], cwd=self.repo, input=input_data,
                              check=True, capture_output=True).stdout

    def write(self, path, data):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self):
        self.git("add", "-A", "-f")
        self.git("commit", "-qm", "Fixture")
        return self.git("rev-parse", "HEAD").decode().strip()

    def audit(self, *args):
        return subprocess.run(["python3", str(AUDIT), *args], cwd=self.repo, capture_output=True)

    def test_clean_and_regex_source_files(self):
        self.write("Scripts/audit-publication.py", AUDIT.read_bytes())
        self.write("Tests/test-publication-audit.py", Path(__file__).read_bytes())
        self.commit()
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_renamed_png_detected_from_signature(self):
        self.write("README.txt", b"\x89PNG\r\n\x1a\nrenamed artwork")
        self.commit()
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"binary/media/archive signature", result.stderr)

    def test_deleted_icon_stays_blocked_but_clean_ancestor_passes(self):
        clean = self.git("rev-parse", "HEAD").decode().strip()
        self.write("Runtime/icon.png", b"fake fixture image")
        self.commit()
        (self.repo / "Runtime/icon.png").unlink()
        self.commit()
        self.assertEqual(self.audit().returncode, 1)
        self.assertEqual(self.audit(clean).returncode, 0)

    def test_parentless_clean_branch_excludes_old_assets(self):
        self.write("icon.png", b"asset")
        self.commit()
        self.git("checkout", "--orphan", "publication")
        self.git("rm", "-rf", ".")
        self.write("README.md", b"Clean publication.\n")
        self.commit()
        self.assertEqual(self.audit().returncode, 0)

    def test_git_replace_cannot_hide_assets(self):
        clean = self.git("rev-parse", "HEAD").decode().strip()
        self.write("icon.png", b"asset")
        dirty = self.commit()
        self.git("replace", dirty, clean)
        self.assertEqual(self.audit().returncode, 1)

    def test_ignored_and_private_paths(self):
        self.write(".gitignore", b"private-settings.json\n")
        self.write("private-settings.json", b"{}\n")
        self.write(".local/options.txt", b"private\n")
        self.write(".env", b"setting=value\n")
        self.commit()
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"matches current ignore rules", result.stderr)
        self.assertIn(b"private configuration path", result.stderr)

    def test_index_checked_only_when_requested(self):
        self.write("asset.jpg", b"staged media")
        self.git("add", "asset.jpg")
        self.assertEqual(self.audit().returncode, 0)
        self.assertEqual(self.audit("--index").returncode, 1)

    def test_special_path_characters_are_safe(self):
        self.write("odd\nfile\tname.txt", b"\0binary")
        self.commit()
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'odd\\nfile\\tname.txt', result.stderr)

    def test_symlink_and_gitlink_rejected(self):
        (self.repo / "link.txt").symlink_to("README.md")
        self.commit()
        result = self.audit()
        self.assertIn(b"symlink, gitlink", result.stderr)
        sha = self.git("rev-parse", "HEAD").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{sha},dependency")
        result = self.audit("--index")
        self.assertIn(b'"dependency"', result.stderr)

    def test_large_blob_and_plain_text_asset_extensions_rejected(self):
        self.write("large.txt", b"a" * (module.MAX_BLOB_BYTES + 1))
        self.write("screenshot.svg", b"<svg/>\n")
        self.write("session.log", b"recording\n")
        self.commit()
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"blob exceeds 2 MiB", result.stderr)
        self.assertIn(b"asset, binary, signing, save, or log", result.stderr)

    def test_secret_values_not_printed(self):
        token = "ghp_" + "aB3cD4eF5" * 5
        self.write("config.txt", token.encode())
        self.commit()
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"GitHub token", result.stderr)
        self.assertNotIn(token.encode(), result.stdout + result.stderr)
        key = "-----BEGIN " + "PRIVATE KEY-----\nfixture\n"
        self.assertIn("private key material", module.content_reasons(key.encode()))

    def test_magic_and_binary_content(self):
        for payload in (b"MZfixture", b"!<arch>\nfixture", b"PK\x03\x04fixture",
                        b"SQLite format 3\0", b"invalid utf8 \xff", b"null\0byte"):
            self.assertTrue(module.content_reasons(payload), payload)
        self.assertTrue(module.content_reasons(b'<svg xmlns="fixture">'))
        self.assertTrue(module.content_reasons(b'<svg/>'))
        self.assertEqual(module.content_reasons(b'pattern = r"<svg(?:\\s|>)"\n'), [])
        self.assertTrue(module.content_reasons(
            b"version https://git-lfs.github.com/spec/v1\noid sha256:fixture\n"))

    def test_missing_ref_fails_closed(self):
        self.assertEqual(self.audit("missing-ref").returncode, 1)

    def test_hook_scans_all_push_refs_and_skips_deletions(self):
        self.write("Scripts/audit-publication.py", AUDIT.read_bytes())
        clean = self.commit()
        self.write("art.png", b"asset")
        dirty = self.commit()
        zeros = "0" * 40
        refs = (f"refs/heads/clean {clean} refs/heads/clean {zeros}\n"
                f"refs/heads/private {dirty} refs/heads/private {zeros}\n"
                f"(delete) {zeros} refs/heads/deleted {dirty}\n").encode()
        result = subprocess.run(["sh", str(HOOK)], cwd=self.repo, input=refs, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"refs/heads/clean", result.stdout)
        self.assertIn(b"refs/heads/private", result.stdout)
        self.assertNotIn(b"Checking publication ref (delete)", result.stdout)
        clean_only = refs.splitlines(keepends=True)[0]
        result = subprocess.run(["sh", str(HOOK)], cwd=self.repo,
                                input=clean_only, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["sh", str(HOOK)], cwd=self.repo,
                                input=b"".join(reversed(refs.splitlines(keepends=True))),
                                capture_output=True)
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
