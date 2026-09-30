#!/usr/bin/env python3
"""Exercise patched Mesa IO reconstruction and pipeline failure on the host.

The functions under test are extracted from the supplied Mesa tree, with one
C-to-C++ void-pointer cast; the fixture substitutes only NIR object plumbing and
Vulkan dispatch. This does not claim GPU/rendering coverage. No game data,
device, or network is used. Negative controls must fail when either fix is removed.
Keep generated sources and execution logs with the other diagnostic results.
"""
import argparse
from pathlib import Path
import re
import shutil
import subprocess


def extract_function(source, name):
    match = re.search(r"(?:template\s*<[^>]+>\s*)?static\s+[^;{}]+?\b" +
                      re.escape(name) + r"\s*\([^;{}]*\)\s*\{", source)
    if not match:
        raise RuntimeError(f"Cannot locate actual source function: {name}")
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Patched Mesa 25.1.9 source directory")
    parser.add_argument("--output", type=Path, required=True,
                        help="Organized diagnostic directory for retained results")
    parser.add_argument("--cxx", default=shutil.which("clang++") or "c++")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    zink = args.source / "src/gallium/drivers/zink"
    compiler = (zink / "zink_compiler.c").read_text()
    draw = (zink / "zink_draw.cpp").read_text()
    start = compiler.index("struct rework_io_state {")
    end = compiler.index("/* for a given mode, generate variables */", start)
    io_functions = compiler[start:end]
    # C permits this implicit conversion; C++ (needed for the actual draw
    # template) does not. This changes no production control flow.
    io_functions = io_functions.replace("struct rework_io_state *ris = data;",
                                        "struct rework_io_state *ris = (struct rework_io_state *)data;")
    pipeline_function = extract_function(draw, "update_gfx_pipeline")

    # Include the real outer draw guard as well as update_gfx_pipeline. Everything
    # before this call is unrelated setup; everything after is draw submission.
    guard_start = draw.index("   bool pipeline_changed = update_gfx_pipeline",
                            draw.index("zink_draw(struct pipe_context"))
    guard_end = draw.index("   if (BATCH_CHANGED || ctx->vp_state_changed", guard_start)
    draw_guard = draw[guard_start:guard_end]
    fixture = (Path(__file__).parent / "mesa-zink-host.cpp").read_text()
    generated = fixture.replace("// INSERT_ACTUAL_IO_FUNCTIONS", io_functions)
    generated = generated.replace("// INSERT_ACTUAL_PIPELINE_FUNCTION", pipeline_function)
    generated = generated.replace("// INSERT_ACTUAL_DRAW_GUARD", draw_guard)

    def run_fixture(name, contents):
        output_source = args.output / f"{name}.cpp"
        output_source.write_text(contents)
        binary = args.output / name
        command = [args.cxx, "-std=c++20", "-O2", "-g", "-Wall", "-Wextra",
                   "-Wno-unused-parameter", "-Wno-unused-function",
                   "-Wno-unused-variable", "-Wno-missing-field-initializers",
                   "-Wno-c99-designator", str(output_source), "-o", str(binary)]
        compiled = subprocess.run(command, text=True, capture_output=True)
        compile_log = args.output / f"{name}-compile.log"
        compile_log.write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise RuntimeError(f"Host compile failed; see {compile_log}")
        result = subprocess.run([str(binary)], text=True, capture_output=True)
        result_log = args.output / f"{name}-result.log"
        result_log.write_text(result.stdout + result.stderr)
        return result

    result = run_fixture("mesa-zink-host", generated)
    print(result.stdout, end="")
    if result.returncode:
        raise RuntimeError(f"Regression test failed; see {args.output}")

    # Do not silently accept a fixture that merely checks its own mocks: remove
    # each production correction in turn and require its specific regression.
    original_helper = extract_function(io_functions, "moltenvk_whole_io_slot")
    io_disabled = generated.replace(original_helper, original_helper[:original_helper.index("{")] +
                                    "{ return false; }")
    failure_block = re.search(r"\s*if \(!pipeline\) \{\s*"
                              r"ctx->gfx_pipeline_state\.pipeline = VK_NULL_HANDLE;\s*"
                              r"return false;\s*\}", pipeline_function)
    if not failure_block:
        raise RuntimeError("Cannot isolate production failure guard for negative control")
    guard_disabled = generated.replace(pipeline_function, pipeline_function.replace(failure_block[0], ""))
    for name, contents, expected in (
        ("negative-no-io-fix", io_disabled, "Scan merges both disjoint loads"),
        ("negative-no-pipeline-guard", guard_disabled,
         "Pipeline failure cannot call unsupported shader-object entry point"),
    ):
        negative = run_fixture(name, contents)
        if negative.returncode != 1 or f"FAIL: {expected}" not in negative.stderr:
            raise RuntimeError(f"Negative control did not detect its regression: {name}")
        print(f"PASS: {name} correctly detects the original defect")


if __name__ == "__main__":
    main()
