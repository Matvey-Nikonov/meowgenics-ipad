#!/usr/bin/env python3
"""Build the pinned Windows Zink renderer with the MoltenVK battle-effect fix.

Called by madeira-runtime.sh mesa. Everything generated stays in its cache.
No device operations; the original downloaded Mesa package is preserved.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "8106697112b0aa56c6c58631d31323251e6951d35d80f09ff457836d94dc3906"


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, target, sha):
    if not target.exists():
        pending = target.with_suffix(target.suffix + ".partial")
        with urllib.request.urlopen(url, timeout=60) as response, pending.open("wb") as out:
            shutil.copyfileobj(response, out)
        if digest(pending) != sha:
            raise SystemExit(f"Download checksum mismatch: {target.name}")
        pending.rename(target)
    if digest(target) != sha:
        raise SystemExit(f"Archive checksum mismatch: {target.name}")


def check_package(cache):
    package = cache / "packages/mesa-zink-patched"
    manifest = package / "build.json"
    if not manifest.is_file():
        raise SystemExit("Patched renderer is missing; run madeira-runtime.sh mesa first")
    data = json.loads(manifest.read_text())
    if (data.get("source_sha256") != SOURCE_SHA or
            data.get("patch_sha256") != digest(ROOT / "Runtime/Patches/mesa-zink.patch")):
        raise SystemExit("Renderer source/patch changed; rebuild with madeira-runtime.sh mesa")
    for name in ("opengl32.dll", "libgallium_wgl.dll"):
        dll = package / "x64" / name
        if not dll.is_file() or digest(dll) != data.get("dll_sha256", {}).get(name):
            raise SystemExit(f"Patched renderer is incomplete or modified: {name}")


def build(cache):
    cache = cache.expanduser().resolve()
    if cache.is_relative_to(ROOT):
        raise SystemExit("Mesa cache must be outside the source repository")
    toolchain = cache / "sources/Madeira/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin"
    if not (toolchain / "x86_64-w64-mingw32-clang").is_file():
        raise SystemExit("Run madeira-runtime.sh prepare first (llvm-mingw is missing)")
    for folder in ("tmp", "downloads", "sources", "packages/pip", "tools"):
        (cache / folder).mkdir(parents=True, exist_ok=True)
    os.environ.update(TMPDIR=str(cache / "tmp"), PIP_CACHE_DIR=str(cache / "packages/pip"))
    archive = cache / "downloads/mesa-25.1.9-source.tar.gz"
    download("https://codeload.github.com/chaotic-cx/mesa-mirror/tar.gz/refs/tags/mesa-25.1.9",
             archive, SOURCE_SHA)
    source = cache / "sources/mesa-mirror-mesa-25.1.9"
    if not source.exists():
        with tarfile.open(archive) as tar:
            tar.extractall(cache / "sources", filter="data")
    patch = ROOT / "Runtime/Patches/mesa-zink.patch"
    applied = subprocess.run(["git", "apply", "--reverse", "--check", str(patch)],
                             cwd=source, capture_output=True).returncode == 0
    if not applied:
        run("git", "apply", "--check", patch, cwd=source)
        run("git", "apply", patch, cwd=source)

    # Preload Meson's pinned zlib fallback over HTTPS instead of its HTTP URL.
    packagecache = source / "subprojects/packagecache"
    packagecache.mkdir(exist_ok=True)
    download("https://github.com/mesonbuild/wrapdb/releases/download/zlib_1.3.1-1/zlib-1.3.1.tar.gz",
             packagecache / "zlib-1.3.1.tar.gz",
             "9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23")
    download("https://wrapdb.mesonbuild.com/v2/zlib_1.3.1-1/get_patch",
             packagecache / "zlib_1.3.1-1_patch.zip",
             "e79b98eb24a75392009cec6f99ca5cdca9881ff20bfa174e8b8926d5c7a47095")

    venv = cache / "tools/mesa-python"
    if not (venv / "bin/python").exists():
        run(sys.executable, "-m", "venv", venv)
    requirements = ["meson==1.7.2", "Mako==1.3.10", "MarkupSafe==3.0.3",
                    "PyYAML==6.0.2", "packaging==25.0"]
    check = subprocess.run([str(venv / "bin/python"), "-c",
        "import importlib.metadata as m; "
        "assert all(m.version(p.split('==')[0]) == p.split('==')[1] "
        "for p in " + repr(requirements) + ")"], capture_output=True)
    if check.returncode:
        run(venv / "bin/python", "-m", "pip", "install", *requirements)
    os.environ["PATH"] = str(venv / "bin") + os.pathsep + os.environ["PATH"]
    build_dir = cache / "mesa-build-win64"
    cross = cache / "tools/mesa-win64.ini"
    bins = {"c": "clang", "cpp": "clang++", "ar": "ar", "strip": "strip",
            "windres": "windres"}
    cross.write_text("[binaries]\n" + "".join(
        f"{key} = {str(toolchain / ('x86_64-w64-mingw32-' + value))!r}\n"
        for key, value in bins.items()) + """
[host_machine]
system = 'windows'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
[properties]
needs_exe_wrapper = true
[built-in options]
c_args = ['-O2']
cpp_args = ['-O2']
c_link_args = ['-static-libgcc']
cpp_link_args = ['-static-libgcc', '-static-libstdc++']
""")
    options = ["--buildtype=release", "--default-library=static",
               "-Dgallium-drivers=zink", "-Dvulkan-drivers=", "-Dplatforms=windows",
               "-Dopengl=true", "-Dgles1=disabled", "-Dgles2=disabled",
               "-Degl=disabled", "-Dglx=disabled", "-Dglvnd=disabled",
               "-Dshared-glapi=enabled", "-Dllvm=disabled", "-Dshader-cache=disabled",
               "-Dvalgrind=disabled", "-Dlibunwind=disabled", "-Dgallium-va=disabled",
               "-Dgallium-vdpau=disabled", "-Dgallium-xa=disabled", "-Dgallium-nine=false",
               "-Dzstd=disabled", "-Dzlib=enabled", "-Dxmlconfig=disabled"]
    run(venv / "bin/meson", "setup", *(["--reconfigure"] if
        (build_dir / "meson-private/coredata.dat").exists() else []),
        build_dir, source, "--cross-file", cross, *options)
    products = {"libgallium_wgl.dll": "src/gallium/targets/wgl/libgallium_wgl.dll",
                "opengl32.dll": "src/gallium/targets/libgl-gdi/opengl32.dll"}
    run("ninja", "-C", build_dir, "-j", os.environ.get("JOBS", "12"), *products.values())
    package = cache / "packages/mesa-zink-patched"
    (package / "x64").mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, relative in products.items():
        dll = build_dir / relative
        # No unshipped compiler/compression DLL may become a hidden dependency.
        imports = subprocess.check_output([str(toolchain / "llvm-objdump"), "-p", str(dll)], text=True)
        bad = [line.strip() for line in imports.splitlines() if "DLL Name:" in line and
               any(word in line.lower() for word in ("libc++", "libwinpthread", "libz-", "libgcc"))]
        if bad:
            raise SystemExit("Unexpected renderer runtime dependencies: " + repr(bad))
        shutil.copy2(dll, package / "x64" / name)
        hashes[name] = digest(dll)
    shutil.copy2(ROOT / "LICENSES/BAR-Mesa-MIT.txt", package / "BAR-Mesa-MIT.txt")
    (package / "build.json").write_text(json.dumps({
        "mesa": "25.1.9", "source_sha256": SOURCE_SHA,
        "patch_sha256": digest(patch), "dll_sha256": hashes}, indent=2) + "\n")
    check_package(cache)
    print("Patched renderer ready:", package)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[2] == "--check":
        check_package(Path(sys.argv[1]))
    else:
        build(Path(sys.argv[1]))
