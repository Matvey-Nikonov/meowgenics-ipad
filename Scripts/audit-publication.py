#!/usr/bin/env python3
"""Fail closed unless a Git ref's entire history contains publishable text only.

Run from the repository: python3 Scripts/audit-publication.py [REF] [--index]
The optional index check supplements history; it does not replace it. Current
ignore rules are also enforced for tracked paths. No working files are read as
publication content, and rejected secret values are never printed.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

MAX_BLOB_BYTES = 2 * 1024 * 1024
TEXT_SUFFIXES = {
    ".bash", ".c", ".cc", ".cfg", ".cmake", ".cpp", ".css", ".csv",
    ".diff", ".entitlements", ".h", ".hpp", ".html", ".ini", ".js",
    ".json", ".m", ".markdown", ".md", ".metal", ".mm", ".patch",
    ".pbxproj", ".plist", ".py", ".rb", ".rst", ".sh", ".swift",
    ".toml", ".ts", ".txt", ".xcconfig", ".xcscheme", ".xcworkspacedata",
    ".xml", ".yaml", ".yml", ".zsh",
}
TEXT_NAMES = {
    ".editorconfig", ".gitattributes", ".gitignore", "authors", "changelog",
    "cmakelists.txt", "codeowners", "copying", "copying.lib", "dockerfile",
    "gemfile", "license", "makefile", "notice", "pre-push", "readme",
}
PRIVATE_PARTS = {
    ".build", ".cache", ".git", ".local", ".ssh", "__pycache__",
    "build", "credentials", "deriveddata", "diagnostics", "downloads",
    "game-assets", "gamefiles", "logs", "mewgenics-exe", "node_modules",
    "provisioning", "recordings", "savedgames", "saves", "screenshots",
    "secrets", "xcuserdata",
}
PRIVATE_NAMES = {
    ".ds_store", ".netrc", ".npmrc", ".pypirc", "credentials.json",
    "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa", "madeira.cfg",
    "settings.local.json", "signing.xcconfig",
}
BLOCKED_SUFFIXES = {
    ".7z", ".a", ".aac", ".app", ".avi", ".bak", ".bin", ".bmp",
    ".bz2", ".cab", ".cer", ".class", ".crt", ".dat", ".db", ".dcr",
    ".der", ".dll", ".dmg", ".dmp", ".dylib", ".exe", ".fla",
    ".flac", ".gif", ".gpak", ".gz", ".heic", ".heif", ".ico",
    ".icns", ".ipa", ".jar", ".jpeg", ".jpg", ".key", ".log",
    ".m4a", ".m4v", ".mkv", ".mobileprovision", ".mov", ".mp3",
    ".mp4", ".o", ".ogg", ".otf", ".p12", ".p7b", ".p8",
    ".pak", ".pdf", ".pem", ".pfx", ".pkg", ".png", ".profdata",
    ".provisionprofile", ".pyc", ".rar", ".rne", ".rtf", ".sav",
    ".save", ".so", ".sqlite", ".sqlite3", ".svg", ".swf", ".tar",
    ".tga", ".tif", ".tiff", ".ttf", ".wasm", ".wav", ".webm",
    ".webp", ".woff", ".woff2", ".xcuserstate", ".xz", ".zip", ".zst",
}
MAGIC = (
    b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a",
    b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\x1f\x8b",
    b"\xfd7zXZ\0", b"7z\xbc\xaf\x27\x1c", b"Rar!\x1a\x07", b"BZh",
    b"\x7fELF", b"MZ", b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca", b"!<arch>\n", b"SQLite format 3\0",
    b"bplist00", b"RIFF", b"OggS", b"fLaC", b"ID3", b"%PDF-",
    b"\0asm", b"FWS", b"CWS", b"ZWS", b"wOFF", b"wOF2", b"OTTO",
)
SECRET_PATTERNS = (
    ("private key material", re.compile(
        r"(?m)^\s*-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----\s*$")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("API secret token", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{24,}\b")),
)


class AuditError(Exception):
    pass


def git(*args, input_data=None, acceptable=(0,)):
    # Replacement refs must not conceal the ancestry or bytes Git will publish.
    environment = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1")
    result = subprocess.run(["git", *args], input=input_data, capture_output=True,
                            env=environment)
    if result.returncode not in acceptable:
        raise AuditError("Git could not read the requested ref, index, or objects; "
                         "check that this is a complete repository and the ref exists.")
    return result.stdout


def path_reasons(path):
    item = PurePosixPath(path.lower())
    reasons = []
    if any(part in PRIVATE_PARTS or part.endswith((".app", ".xcarchive", ".xcresult"))
           for part in item.parts):
        reasons.append("private, game, generated, or diagnostic directory")
    if (item.name in PRIVATE_NAMES or item.name.startswith(".env") or
            ".local." in item.name or item.name.endswith(".local")):
        reasons.append("private configuration path")
    if item.suffix in BLOCKED_SUFFIXES:
        reasons.append("asset, binary, signing, save, or log file type")
    elif item.suffix not in TEXT_SUFFIXES and item.name not in TEXT_NAMES:
        reasons.append("file type is outside the text/code/license allowlist")
    return reasons


def content_reasons(data):
    if any(data.startswith(magic) for magic in MAGIC):
        return ["binary/media/archive signature"]
    if b"\0" in data or any(byte < 32 and byte not in (9, 10, 12, 13) for byte in data):
        return ["binary control bytes"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ["non-UTF-8 binary content"]
    if text.startswith("version https://git-lfs.github.com/spec/v1\n"):
        return ["Git LFS pointer (external binary content is not allowed)"]
    if re.match(r"\ufeff?\s*(?:<\?xml.*?\?>\s*)?(?:<!--.*?-->\s*)*<svg(?:\s|/?>)",
                text, re.IGNORECASE | re.DOTALL):
        return ["embedded SVG artwork"]
    return [description for description, pattern in SECRET_PATTERNS if pattern.search(text)]


def tree_entries(tree):
    for record in git("ls-tree", "-r", "-z", "--full-tree", tree).split(b"\0"):
        if record:
            header, path = record.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split()
            yield mode, kind, oid, path


def audit(ref, include_index=False):
    grafts = Path(os.fsdecode(git("rev-parse", "--git-path", "info/grafts").strip()))
    if grafts.exists() and grafts.stat().st_size:
        raise AuditError("Legacy Git grafts can hide published ancestry; remove them before auditing.")
    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        raise AuditError("Shallow history cannot be fully audited; fetch complete history first.")
    commit = git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").strip()
    trees = git("rev-list", "--format=%T", "--no-commit-header", commit.decode()).splitlines()
    entries = set()
    for tree in set(trees):
        entries.update(tree_entries(tree.decode("ascii")))
    if include_index:
        for record in git("ls-files", "--stage", "-z").split(b"\0"):
            if record:
                header, path = record.split(b"\t", 1)
                mode, oid, stage = header.decode("ascii").split()
                if stage != "0":
                    raise AuditError("Resolve the unmerged index before publication.")
                entries.add((mode, "blob" if mode != "160000" else "commit", oid, path))

    paths = {entry[3] for entry in entries}
    ignored = set(git("check-ignore", "--no-index", "-z", "--stdin",
                      input_data=b"\0".join(sorted(paths)) + (b"\0" if paths else b""),
                      acceptable=(0, 1)).split(b"\0")) - {b""}
    issues = set()
    checked = {}
    for mode, kind, oid, raw_path in sorted(entries, key=lambda entry: (entry[3], entry[2])):
        path = raw_path.decode("utf-8", "surrogateescape")
        reasons = path_reasons(path)
        if raw_path in ignored:
            reasons.append("tracked path matches current ignore rules")
        if mode not in ("100644", "100755") or kind != "blob":
            reasons.append("symlink, gitlink, or non-regular file")
        else:
            if oid not in checked:
                size = int(git("cat-file", "-s", oid).strip())
                checked[oid] = (["blob exceeds 2 MiB"] if size > MAX_BLOB_BYTES else
                                content_reasons(git("cat-file", "blob", oid)))
            reasons.extend(checked[oid])
        for reason in reasons:
            issues.add((path, oid[:12], reason))
    print(f"Audited {len(trees)} commits, {len(checked)} blobs, {len(paths)} paths"
          + (" and staged index." if include_index else "."))
    if issues:
        print("Publication blocked:", file=sys.stderr)
        for path, oid, reason in sorted(issues)[:60]:
            print(f"  {json.dumps(path)} [{oid}]: {reason}", file=sys.stderr)
        if len(issues) > 60:
            print(f"  ... {len(issues) - 60} additional findings.", file=sys.stderr)
        print("Remove these files from all history being published, or use a clean "
              "parentless publication branch. Deleting only the current file is insufficient.",
              file=sys.stderr)
        return 1
    print("PASS: no forbidden publication content found in this ref.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", nargs="?", default="HEAD", help="commit, branch, or tag to audit")
    parser.add_argument("--index", action="store_true", help="also inspect staged content")
    args = parser.parse_args()
    try:
        return audit(args.ref, args.index)
    except (AuditError, ValueError) as error:
        print(f"Publication audit failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
