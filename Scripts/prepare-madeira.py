#!/usr/bin/env python3
"""Fetch pinned runtime sources and apply the standalone Mewgenics patches.

Requires Git, CMake, Ninja, Python 3.12+, bison 3, ccache, 7zz and Xcode with
the Metal Toolchain. Sources, downloads and build products stay in CACHE.
"""
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(sys.argv[1]).expanduser().resolve()
SOURCE = CACHE / "sources/Madeira"
DOWNLOADS = CACHE / "downloads"
DOWNLOADS.mkdir(parents=True, exist_ok=True)


def run(*args, cwd=None, quiet=False):
    return subprocess.run(args, cwd=cwd, check=True,
                          stdout=subprocess.DEVNULL if quiet else None)


def checkout(url, revision, path, branch=None):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        args = ["git", "clone", "--depth", "1"]
        if branch:
            args += ["--branch", branch]
        run(*args, url, str(path))
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
    if current != revision:
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=path):
            raise SystemExit(f"Refusing to change modified checkout: {path}")
        run("git", "fetch", "--depth", "1", "origin", revision, cwd=path)
        run("git", "checkout", "--detach", revision, cwd=path)


def download(url, name, sha):
    path = DOWNLOADS / name
    if not path.exists():
        pending = path.with_suffix(path.suffix + ".partial")
        print("Downloading", name, flush=True)
        urllib.request.urlretrieve(url, pending)
        if hashlib.file_digest(pending.open("rb"), "sha256").hexdigest() != sha:
            raise SystemExit(f"Checksum mismatch: {pending}")
        pending.rename(path)
    with path.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != sha:
            raise SystemExit(f"Checksum mismatch: {path}")
    return path


def extract_tar(archive, destination, final_name):
    final = destination / final_name
    if final.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        first = tar.getmembers()[0].name.split("/")[0]
        tar.extractall(destination, filter="data")
    extracted = destination / first
    if extracted != final:
        extracted.rename(final)


def patch(name, path):
    file = ROOT / "Runtime/Patches" / (name + ".patch")
    applied = subprocess.run(["git", "apply", "--reverse", "--check", str(file)],
                             cwd=path, capture_output=True).returncode == 0
    if not applied:
        run("git", "apply", "--check", str(file), cwd=path)
        run("git", "apply", str(file), cwd=path)


checkout("https://github.com/willfaust/Madeira.git",
         "ee3d5c0223559abfc4b90cb99aab5dfadbc0bcc5", SOURCE)
for name, folder in [("fex", "FEX"), ("wine", "wine"), ("dxmt", "research/dxmt")]:
    path = SOURCE / folder
    # Keep an already-patched working checkout, including local commits. For a
    # new clone, initialize precisely Madeira's recorded gitlink and children.
    applied = path.exists() and subprocess.run(
        ["git", "apply", "--reverse", "--check", str(ROOT / "Runtime/Patches" / (name + ".patch"))],
        cwd=path, capture_output=True).returncode == 0
    if not applied:
        run("git", "submodule", "update", "--init", "--recursive", "--depth", "1", "--jobs", "4", folder, cwd=SOURCE)
checkout("https://github.com/freetype/freetype.git",
         "42608f77f20749dd6ddc9e0536788eaad70ea4b5", SOURCE / "research/freetype", "VER-2-13-3")
for name, folder in [("madeira", SOURCE), ("fex", SOURCE / "FEX"),
                     ("dxmt", SOURCE / "research/dxmt"), ("wine", SOURCE / "wine")]:
    patch(name, folder)
# Artwork is private/generated, never downloaded from the game or this repo.
run(sys.executable, str(ROOT / "Scripts/stage-app-icon.py"), str(SOURCE / "app/Madeira/Assets.xcassets"))

mingw = "llvm-mingw-20260421-ucrt-macos-universal"
archive = download(f"https://github.com/mstorsjo/llvm-mingw/releases/download/20260421/{mingw}.tar.xz",
                   mingw + ".tar.xz", "bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7")
extract_tar(archive, SOURCE / "toolchains", mingw)
archive = download("https://github.com/llvm/llvm-project/archive/8dfdcc7b7bf66834a761bd8de445840ef68e4d1a.tar.gz",
                   "llvm-15.0.7.tar.gz", "b7f15ee379144b0c26a64ff9a1f27d0ea341a0db0c91b71c66bbfa8b310788ac")
extract_tar(archive, SOURCE / "toolchains", "llvm-project")
cmake = SOURCE / "toolchains/llvm-project/llvm/cmake/modules/AddLLVM.cmake"
cmake.write_text(cmake.read_text().replace('MATCHES "Darwin"', 'MATCHES "Darwin|iOS"'))

archive = download("https://github.com/pal1000/mesa-dist-win/releases/download/26.2.3/mesa3d-26.2.3-release-mingw.7z",
                   "mesa3d-26.2.3-release-mingw.7z", "ea3b70889aa062815e1b124196d8a542f1fc4232c3da773a23b76cc9e4b9a57a")
mesa = CACHE / "packages/mesa"
if not (mesa / "x64/libgallium_wgl.dll").exists():
    run("7zz", "x", "-y", str(archive), "-o" + str(mesa), quiet=True)

# Zink 26 requires robustness2.nullDescriptor, which MoltenVK 1.4.2 lacks.
archive = download("https://github.com/pal1000/mesa-dist-win/releases/download/25.1.9/mesa3d-25.1.9-release-mingw.7z",
                   "mesa3d-25.1.9-release-mingw.7z", "5d6cd7fe78c524a534bdfa92bfb437cb914c9d291ab5f4d48185a71f2d8a2210")
mesa_zink = CACHE / "packages/mesa-zink"
if not (mesa_zink / "x64/libgallium_wgl.dll").exists():
    run("7zz", "x", "-y", str(archive), "-o" + str(mesa_zink), quiet=True)

archive = download("https://github.com/KhronosGroup/MoltenVK/releases/download/v1.4.2/MoltenVK-ios.tar",
                   "MoltenVK-ios-1.4.2.tar", "b5d947b1660e6e9fed40b9cd2387e160aaab9e80b775c0cef7e14059405178c1")
moltenvk = CACHE / "packages/moltenvk-1.4.2"
extract_tar(archive, moltenvk, "MoltenVK")
shutil.copy2(moltenvk / "MoltenVK/MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a",
             SOURCE / "app/Madeira/libMoltenVK.a")
shutil.copy2(moltenvk / "MoltenVK/LICENSE", SOURCE / "app/Madeira/licenses/LICENSE-MOLTENVK.txt")

# Extract the original Microsoft DLLs from the installer's embedded CABs.
# The hash intentionally fails closed if Microsoft's rolling download changes.
redist = download("https://aka.ms/vc14/vc_redist.x64.exe", "vc_redist.x64.exe",
                  "843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c")
vc = CACHE / "packages/vcredist"
vc.mkdir(parents=True, exist_ok=True)
d = redist.read_bytes()
pos, n = 0, 0
while (pos := d.find(b"MSCF", pos)) >= 0:
    if pos + 36 < len(d):
        size = struct.unpack_from("<I", d, pos + 8)[0]
        if d[pos + 4:pos + 8] == b"\0" * 4 and 36 < size <= len(d) - pos:
            cab = vc / f"container{n}.cab"
            cab.write_bytes(d[pos:pos + size])
            run("7zz", "x", "-y", str(cab), "-o" + str(vc / f"container{n}"), quiet=True)
            n += 1
    pos += 4
minimum = vc / "a4-files"
run("7zz", "x", "-y", str(vc / "container1/a4"), "-o" + str(minimum), quiet=True)
output = SOURCE / "app/Madeira/x86_64-vcruntime"
output.mkdir(exist_ok=True)
for dll in minimum.glob("*.dll_amd64"):
    shutil.copy2(dll, output / dll.name.removesuffix("_amd64"))

local = ROOT / ".local"
local.mkdir(exist_ok=True)
link = local / "Madeira"
if link.is_symlink() and link.resolve() != SOURCE:
    raise SystemExit(f"Existing runtime link points elsewhere: {link}")
if not link.exists():
    link.symlink_to(SOURCE, target_is_directory=True)
print("Ready:", SOURCE / "app/Madeira.xcodeproj")
