# Standalone Mewgenics runtime

`Mewgenics.xcworkspace` opens the embedded Madeira runtime. The older
`MewgenicsIPad.xcodeproj` is the archive/SWF inspection app; it does not run
the Windows game.

The runtime launches `C:\Mewgenics\Mewgenics.exe` directly, with no Madeira
library or desktop launcher. StikDebug supplies JIT for each new process;
the debugger detaches after allocating the executable pool. LocalDevVPN and
the source-built StikDebug app must already be configured on the iPad.

## Build and install

Requirements: Xcode 27 with its Metal Toolchain, Apple development signing,
Python 3.12+, CMake, Ninja, bison 3, ccache, LLVM, pkgconf and 7zz. Follow
[the setup guide](../docs/SETUP.md) first and supply your own signing team,
bundle identifier, device ID and cache path in `.local/config.sh`.

```sh
bash Scripts/madeira-runtime.sh prepare
bash Scripts/madeira-runtime.sh mesa
bash Scripts/madeira-runtime.sh native
bash Scripts/madeira-runtime.sh build
bash Scripts/madeira-runtime.sh install
bash Scripts/madeira-runtime.sh game
bash Scripts/madeira-runtime.sh configure
bash Scripts/madeira-runtime.sh launch
# First installation: after reaching the menu, close Mewgenics; merge
# performance settings into the game settings file it has now created.
bash Scripts/madeira-runtime.sh configure
bash Scripts/madeira-runtime.sh launch
bash Scripts/madeira-runtime.sh log
```

`prepare` fetches pinned sources, verifies dependency checksums, applies the
patches here and creates `.local/Madeira`. `native` builds the runtime's native
libraries. `build` compiles and verifies the signed iPad app. `game` copies the
supplied assets and Mesa DLLs and stages a compatibility-patched executable.
The original `MEWGENICS_GAME_DIR/Mewgenics.exe` is never modified. Neither that
executable nor its 5.1 GB resource archive is committed.

`mesa` builds the patched Windows Zink renderer from pinned source. Its host
regression test executes extracted production functions with synthetic NIR and
Vulkan-call fixtures (it does not render on a GPU):

```sh
python3 Tests/test-mesa-zink.py \
  --source "$MEWGENICS_CACHE/sources/mesa-mirror-mesa-25.1.9" \
  --output "$MEWGENICS_CACHE/diagnostics/mesa-zink-host"
```

`build` and `install` default to an optimized Release app with development
signing: Swift uses `-O` with whole-module optimization and the app's native
bridge uses `-O2`. JIT breakpoint allocation routines retain their explicit
optimization exclusions. The build verifies the signed development-debugging
and increased-memory entitlements as well as the app signature. Set
`MEWGENICS_CONFIGURATION=Debug` for both commands to use the Debug artifact.

For an existing installation with `Documents/madeira.cfg`, diagnostic presets
preserve the current graphics, input, memory and other configuration:

```sh
bash Scripts/madeira-runtime.sh diagnostics off   # Normal play
bash Scripts/madeira-runtime.sh diagnostics stats # Lightweight periodic metrics
bash Scripts/madeira-runtime.sh diagnostics full  # Detailed graphics inspection
```

These commands only update configuration; switches apply at the next launch.
They do not restart the app. All presets disable hidden log-view processing
and verbose debug logging. `stats` records displayed-frame rate and device
metrics without the detailed graphics probes; `full` also enables Vulkan
timings, drawable inspection, window-tree dumps and periodic thread stacks. Normal play retains
errors and lifecycle logs but disables both periodic diagnostic groups.

`mesa` builds the patched Mesa 25.1.9 DLLs locally. `renderer zink` installs
those DLLs and their matching GPU configuration;
`renderer llvmpipe` restores the Mesa 26.2.3 software fallback. Both preserve
unrelated configuration and saves. Restart after switching. `Profiles/zink.cfg`
and `Profiles/native-settings.txt` document the native-resolution settings.
The runtime selects the actual landscape pixel dimensions from the iPad.

Set `MEWGENICS_CACHE` to an absolute path outside the repository. On an external
drive, confirm it is mounted before building. CMake build trees contain absolute paths and need to be
reconfigured after relocation; do not simply reuse their cached paths.
The workspace symlink must point to the relocated source directory.

## Longer-session crashes

On 2026-10-01, a later session crashed after about 58 minutes, with a responsive
cursor and stopped game audio. The game wrote a crash marker, but the original
runtime log was replaced by two short JIT handoff launches. That freeze's exact
cause is still unconfirmed; the successful Rat Bomb retest did not establish
long-session stability.

The native monitor no longer calls the inherited orphan-lock heuristic. It
mistook absent FEX-specific TEB markers for evidence that an ordinary game SRW
lock had a dead owner. Normal game locks never publish those markers. It also
counted each waiter as a separate observation, so three waiters could trigger a
forced unlock during one sample. An extracted-source host reproducer confirmed
that it released a lock while its real owner was still alive. An earlier
startup log recorded this forced release of a Mewgenics lock shortly before a
C++ exception. This is a concrete independent defect, but its role in the later
freeze remains an inference.

Recovery for a recorded FEX lock held by a confirmed dead Mach thread remains
unchanged. The rebuilt native object references those recovery functions and
does not reference the heuristic. The signed Release update was installed and
launched with permission on the physical M5 iPad. Its captured startup log
confirms JIT and creation of the 2752×2064 swapchain, with no unhandled exception
or graphics-pipeline failure in that capture. Device validation over a longer
session is pending; a successful startup does not establish that the recurring
freeze is resolved.

Logging retains four prior process logs: `Documents/madeira-log.prev.txt`,
`madeira-log.prev2.txt`, `madeira-log.prev3.txt`, and `madeira-log.prev4.txt`.
This preserves the failed game session through the JIT roundtrip. If a rename
fails, startup appends to the current log instead of truncating it. Nine host
assertions cover the handoff, archive order/count, and a failed move:

```sh
swiftc -parse-as-library -module-cache-path "$MEWGENICS_CACHE/clang-modules" \
  .local/Madeira/app/Madeira/LogArchive.swift Tests/LogArchiveTests.swift \
  -o "$MEWGENICS_CACHE/tmp/LogArchiveTests"
"$MEWGENICS_CACHE/tmp/LogArchiveTests" \
  "$MEWGENICS_CACHE/diagnostics/log-archive-$(date +%Y%m%d-%H%M%S)"
```

The on-device JIT handoff also retained the pre-update process log in
`madeira-log.prev2.txt`; the downloaded archive matched the pre-install capture
byte for byte. Private installation, startup and archive verification evidence
is kept under the cache's `diagnostics/madeira` directory, outside Git.

## Compatibility changes

- Madeira is pinned to `ee3d5c0223559abfc4b90cb99aab5dfadbc0bcc5`.
- FEX is pinned to `26859e184ad90f0e811d7f8bbd943a4b1573a2c3`.
- DXMT is pinned to `a5e0cd3d41bf248fd1c030a2e1c515ba3522f4ef`.
- GPU rendering uses Mesa 25.1.9 Zink, Wine Vulkan and statically linked
  MoltenVK 1.4.2. The device reports `Apple M5 GPU (MOLTENVK)`.
  Mesa 26 requires `nullDescriptor`, which this MoltenVK lacks. Mesa 26.2.3
  LLVMpipe remains available as a slower software fallback.
- `mesa-zink.patch` reconstructs ordinary 32-bit vertex-output/fragment-input
  slots as whole vec4 values on MoltenVK, merging disjoint fragment loads.
  Other drivers, builtins, arrays and other shader stages retain their existing
  handling. This targets the `user(locn2_3),user(locn3_3)` Metal interface error
  logged during a Rat Bomb explosion. Zink also skips a failed pipeline draw
  before it can call unsupported shader-object dispatch through a null pointer.
  The fix is adapted from the MIT-licensed BAR-on-Apple-Silicon patches.
  Synthetic host regression tests cover reconstruction and failed/successful
  dispatch. After installation on 2026-10-01, the user confirmed that crashing
  had stopped on the iPad Pro M5. The initial startup attempt failed; a
  subsequent launch initialized graphics without shader errors in its captured
  log. The cause of that initial startup failure remains undetermined.
- Hide `VK_EXT_host_image_copy` from Windows Mesa: MoltenVK depth/stencil
  images require private memory, while host-copy usage excludes it. Without
  the guard, framebuffer allocation fails and every game draw is rejected.
- Filter only optional SPIR-V debug names equal to `sampler` before shader
  creation. Otherwise SPIRV-Cross emits a texture named `sampler` that hides
  Metal's sampler type and causes shader compilation failure. Bindings,
  entry points and executable instructions are preserved. The adapter has
  malformed-input checks and an ASan/UBSan-tested standalone parser test.
  This addresses the same issue as upstream SPIRV-Cross commit `cd3fcb2`.
- Metal drawable size and layer scale use the same guest pixel dimensions.
  GPU work pauses when the app loses focus; bounded image acquisition avoids
  blocking all queue submissions behind a waiting image. Background/resume
  still needs an extended device test.
- A 384 MiB JIT pool is configured. `P_TRACED` is checked before using the
  debugger's BRK allocation protocol; `CS_DEBUGGED` alone is insufficient.
- The supplied game build, 1.1.b21239, initializes 2,246 object pools with
  1 GiB reservation chunks. The 36th active reservation exhausted the
  runtime's address range and led to an unchecked null write at game RVA
  `0x969604`. `patch-game-pools.py` changes only the verified reserve-size
  immediate in each pool initializer to 16 MiB. Existing allocation, commit
  and additional-block growth logic remains intact. Exact input SHA-256,
  constructor instructions and field destinations are validated before
  writing a separate output. Unknown game builds fail closed.
- The experimental `--expand-canvas` option clears the verified aspect-lock flag at
  RVA `0x7493ed`. The engine's existing full-window path expands 1280×720 to
  1280×960 on a 4:3 iPad, retaining the original content and proportions.
  Projection and mouse mapping share the expanded bounds. The patch changes
  one byte beyond the pool fix. Device testing exposed unfinished artwork
  outside the authored area. The user requested the original framing, so
  this option is disabled and the installed game keeps its 16:9 borders.
- Touch/Pencil uses the existing direct-position input component. Mouse
  release events are held across a presented frame, with a 500 ms timeout,
  to avoid collapsing a tap before a polling game can observe its press.
  Input is drained on the presenting window's owner thread and that window
  receives foreground activation. Before this change, clicks reached a
  window with no active/focused state and were discarded.
- Pencil hover and contact dragging use the existing absolute-position input
  mapping and keep the native cursor synchronized. The user confirmed both.
- The standalone app adds gestures to that same input component: Pencil
  squeeze or a two-finger tap sends right-click; holding either gesture holds
  the right button for Examine. Pencil double-tap or a three-finger hold
  toggles Left Control for Tactical View, with a small `TACTICAL` indicator
  while enabled. A three-finger tap sends Escape for Back/Pause. Pinching or
  two-finger vertical dragging sends the zoom wheel, with one motion source
  selected per gesture. A four-finger hold opens the existing keyboard.
  Existing combat buttons remain directly tappable. Synthetic keys/buttons
  merge with physical device state and release on focus loss. These gestures
  default on only in this app; `env.MEWGENICS_GESTURES = 0` opts out. The
  signed build compiles and the production-method host tests pass. The user
  confirmed Pencil squeeze, Pencil double-tap and three-finger Back/Pause on
  the iPad. Pinch/scroll, held Examine and keyboard access remain to be
  checked on the device.
- Retire anonymous JIT alias metadata when its guest reservation is freed;
  otherwise a reused heap can inherit stale executable-page protection.
  Protection changes are limited to the intersecting alias pages.
- Wine's missing-file resolver checks an existing parent directory once
  before entering its normal final-component lookup. The house trace showed
  repeated checks of SQLite save journal/WAL names, each walking every parent
  directory. The shortcut retains fresh file checks, case-insensitive search,
  reparse aliases and creation semantics. It never caches a missing file or
  changes database contents; unresolvable parents use the original path.
  A second optimization retains that component's directory stream and
  case-sensitivity result while checking its `?` reparse alias. It rewinds
  for the second scan and closes before advancing or recursing. All exact
  file probes remain fresh; nothing is retained across pathname queries.
- The existing audio session uses `mixWithOthers` for external music/PiP.
  Its event timer uses absolute deadlines and a short audio cushion to avoid
  repeatedly starving the output with relative 10 ms sleeps plus IPC time.
  A larger advertised device period lets SDL queue packets that cover the
  iPad's output callbacks. The user confirmed clean audio with 20 ms packets;
  diagnostics still found occasional underruns with 1,024-frame callbacks,
  so the runtime now advertises 40 ms for extra scheduling headroom. Native
  GPU samples showed no underruns with 1,024-frame callbacks.
- The app icon is generated from source. `MEWGENICS_APP_ICON` optionally supplies
  private 1024×1024 artwork for a local build; game artwork is not published.
- The app supports landscape only, requests ProMotion at the panel maximum,
  and reports that refresh rate to Wine. The standalone FPS label and its
  sampling timers are removed at the user's request. Its existing
  click-through window retains only the Tactical View indicator; display
  pacing and native performance logging are independent. Display pacing stays
  enabled; periodic metrics are opt-in through the diagnostic presets.
  `unlock_framerate true` decouples rendering from the
  fixed `update_rate 60`; `framerate_cap 120` limits rendering separately.
  With `unlock_framerate false`, the executable skips rendering whenever no
  simulation tick is due, imposing the observed 60 FPS ceiling. The status
  window also hides system status UI and supports landscape only.
  The app requests the panel maximum for all three
  `CAFrameRateRange` fields, following Apple's controlled-test guidance,
  instead of allowing a 60–120 Hz range. Diagnostics can log display-link cadence,
  Metal presentation timestamps, drawable acquisition wait, low-power state
  and thermal state. A request is not proof of actual 120 FPS.

## Current device evidence and limits

Test device: iPad Pro 13-inch M5, iPadOS 27.0.1. Native libraries and the signed
app build successfully. The user confirmed full gameplay, working clicks,
clean audio and the supplied Home Screen icon on September 30. It runs after
the pool patch and LLVMpipe switch. Softpipe was too slow to advance past
the black frame in useful time.

The user confirmed visible GPU output after both compatibility fixes. Native
2752×2064 output and `render_scale 1` are installed. Early native log samples
showed roughly 39–60 displayed frames per second, not a sustained gameplay
benchmark or evidence of 120 FPS. The game itself initially drew 16:9 black
bands inside the full-screen surface. The expanded-canvas experiment was
reverted at the user's request after it exposed unintended artwork.
Original software rendering was about 3 FPS at full scale;
`Profiles/testing-settings.txt` retains its temporary half-scale profile.

Enabling `unlock_framerate` and the user's live test disabling VSync both
left output at or below 60 FPS. The authorized diagnostic restart measured
120 Hz display-link callbacks with low-power mode off and normal thermal
state, while game presentation remained around 53–60 FPS. The user's brief
50% render-scale test also remained capped at 60. The log confirms two
swapchain images and roughly 5–8 ms average waits in `nextDrawable` after
initial loading. These measurements do not yet establish a single cause.

The runtime promotes ordinary two-image swapchains to three images.
Pinned MoltenVK 1.4.2 advertises support for two to three images and uses
the chosen count for its Metal drawable pool. This preserves all GPU
fences and semaphores; the hypothesis is that a third drawable lets rendering
continue while the other two are displayed/queued. Shared-present modes are
untouched. `env.MADEIRA_VULKAN_SWAPCHAIN_IMAGES = 2` opts out for A/B tests;
`[mewgenics-swapchain]` logs requested, chosen and actual counts. The user
confirmed 120 FPS after this change. Device logs confirm three images,
repeated 119–120 FPS display completions, and drawable waits falling to
roughly 0.003 ms after loading. This removes the presentation ceiling;
it does not establish sustained 120 FPS in every scene.

The user's September 30, 21:49 recording and matching logs show the house
scene around 25–40 FPS. Display-link callbacks remain at 120 Hz with normal
thermal state, low-power mode off and no audio underruns. Main-thread stack
samples repeatedly show filesystem path resolution. Further profiling is
needed before attributing the entire cost to a single subsystem.

A 12.35-second File Activity trace found 813,977 filesystem calls in the
game process, including 66,718 `fstatat` calls. The main game thread repeatedly
checks `steamcampaign02.sav-journal` and `.sav-wal` and walks their eight parent
directories. The native resolver shortcut targets that repeated work.
The native library and signed iPad app build successfully. A host harness
compares the actual resolver against the pinned baseline: 130 cases pass
with UBSan, including journal creation/deletion, parent replacement, case
differences, Unicode, short aliases and reparse dispatch. Its representative
missing-sidecar lookup reduces `fstatat` calls from 11 to 4. Run it with
`python3 Tests/test-wine-path-resolution.py --cache <runtime-cache>`.
Trace durations include profiler overhead. After the authorized installation,
the user reported 40–60 FPS in the house, versus the earlier 25–40. Runtime
samples span roughly 50–80 FPS during parts of that session. Settings fetched
from the device confirm `render_scale 1`, VSync off, a 120 FPS limit, and
`noise_and_grain none` / `vignette_flicker none`. This is an improvement, not
a controlled benchmark or a claim of sustained 120 FPS. A follow-up File
Activity trace captured the app while backgrounded and has zero game events;
it cannot establish a measured reduction in filesystem calls on the device.

In the next live scale test, 50% increased FPS, but
the user then restored 100% and the higher FPS persisted. The saved setting
was independently re-read as `render_scale 1`; the swapchain remained native
without being recreated during the toggle. This does not establish a causal
resolution/GPU bottleneck. The user initially associated the recurring
startup slowdown with the toggle, then isolated the effect: **waiting alone
improves FPS, and toggling after warm-up produces no further improvement**.
The target at that stage was sustained 120 FPS after warm-up at native resolution,
versus approximately 80 FPS in the house. Do not implement an
automatic render-scale reset based on the superseded hypothesis.

Static analysis of the original executable finds that the scale callback
at VA `0x14029be70` changes the saved scale, without changing pacing or
aspect flags. Frame setup at `0x1409b7870` checks target dimensions and MSAA
on each pass; initializer `0x140a28a80` creates the main RGBA8 color and
depth/stencil renderbuffers. Both initial allocation and scale changes use
that initializer. Reallocation first deletes the existing main and auxiliary
resolve/copy targets. For the current 16:9 framing, the dimension helper
at `0x1409b5dc0` requests 2752×1548 at 100%, 1376×774 at 50%, and 2752×1548
again after restoring 100%. The same MSAA check applies in both paths;
static analysis does not support a stale startup MSAA setting or establish
the driver-level cause.

`env.MADEIRA_VULKAN_DIAGNOSTICS = 1` enables attachment-allocation metadata
(actual Vulkan extent, format, sample count and usage) and cumulative elapsed
time inside acquire, submit, present, fence/semaphore wait and idle calls.
The diagnostics default off. `[mewgenics-vk-target]` records allocations and
`[mewgenics-vk-timing]` emits approximate cumulative counter snapshots every
120 present calls, including failed calls. These are not displayed-frame
counts. Durations include waiting and can overlap across threads; they are
neither GPU timings nor additive frame costs. No image pixels are read and
no synchronization or call arguments are changed. The diagnostic build was
installed and restarted with explicit permission. Its logs confirm
2752×1548 color/depth targets with one sample before and after the toggle,
and 1376×774 only during the 50% interval. Stable present-call rates before
and after were 83.46/s and 83.04/s, respectively; Metal display completions
agree. Cumulative semaphore waits average about 3.18 and 3.13 ms per present.
The first measured house interval was 55.3/s, improving before any scale
change. These observations support the user's corrected warm-up finding.
Validation: all 46 native win32u translation units compile; the signed iPad
app builds and passes `codesign --verify --deep --strict`.

The subsequent active Metal System Trace captured 987 interior game frame
groups over 13.09 seconds (about 75.4/s). Overlapping GPU intervals were
unioned, not summed across channels: game GPU activity occupies 22.07% of
the span, with mean 2.927 ms of GPU work per frame (p95 3.963 ms), versus a
mean 13.273 ms completion period and 10.340 ms between successive GPU spans.
The remaining delay in this capture lies mostly between GPU submissions;
the GPU intervals alone cannot distinguish CPU work from synchronization or
pacing. The trace does not expose the pre-existing offscreen attachment
dimensions, so full internal resolution after the toggle remains unverified.
No automatic scale toggle, shader change or synchronization bypass is applied.

A second active Metal trace began about 87 seconds after launch. It records
76.05 GPU frame groups/s with 2.945 ms mean GPU work and 22.39% GPU activity.
There are no graphics-compiler intervals during this late capture; it cannot
explain earlier warm-up. UUID-matched CPU symbolication attributes 4.04 s of
10.635 s sampled running time to `NtQueryFullAttributesFile` path resolution,
roughly half of the dominant Wine thread's sampled work. Nested directory
search and case-sensitivity checks contribute to that same cost and must not
be added again. This is the strongest measured optimization lead. It does
not justify caching missing save journals or changing save semantics.

An active 8.04-second File Activity trace confirms 4,214 missing journal/WAL
queries, with four fresh `fstatat` probes and two parent sensitivity checks
per query. The per-component reuse change reduces parent opens and
sensitivity checks from two to one each; it keeps all four file probes.
688 differential cases against an independent prior resolver/helper pass
under UBSan, including both case modes, alias and short-name precedence,
allocation/I/O failures and fresh create/delete behavior. Tracked and OS
descriptor counts remain stable; exact successful paths still use one stat
and no directory opens. UTF-16 and reparse dispatch retain host test shims.
All 39 native ntdll translation units compile, and the signed iPad app builds
and passes signature verification. This second lookup optimization was
installed and launched with explicit restart permission. The user accepted
the current performance and moved on to background/resume reliability.
Neither the measured lookup cost nor the host call reduction alone
establishes sustained 120 FPS; further performance work is deferred.

The standalone launcher now retains bootstrap, pending JIT handoff, launch
and error state in a main-actor process singleton. Previously these flags
belonged to a SwiftUI view, so recreating that view could invoke the direct
Wine launch path again, bypassing the library's separate one-session guard.
Replacement views now reattach to the existing Metal host and cannot repeat
bootstrap, request another JIT handoff or launch Wine again. A failed
preparation remains retryable, while a new OS process starts with fresh state.
No launch flags are persisted across process death.

Lifecycle logs record process/session identity, Wine status, JIT flags,
memory footprint and background/foreground notifications. One persisted
breadcrumb identifies the previous process's last recorded state, not its
termination reason. Existing GPU pause/resume calls also log elapsed time.
The captured session used about 6.4 GiB and included successful background
resumes. Accessible reports contained no matching recent fatal termination;
the latest CPU-resource report explicitly says `Action taken: none`.
Memory eviction, a GPU suspension stall and JIT loss therefore remain
unconfirmed explanations for the user's reported cold relaunches.

The synchronous GPU drain remains unchanged in this iteration. It has an
unbounded main-thread wait, but simply moving it to a worker is unsafe:
MoltenVK's idle operation commits a new Metal command buffer, and Apple
requires committed work to be scheduled before the background callback
returns. A later fix needs a scheduling-aware GPU lifecycle design if timing
or termination evidence identifies this path. See
[Apple's Metal background requirements](https://developer.apple.com/documentation/metal/preparing-your-metal-app-to-run-in-the-background)
and the [pinned MoltenVK queue implementation](https://github.com/KhronosGroup/MoltenVK/blob/v1.4.2/MoltenVK/MoltenVK/GPUObjects/MVKQueue.mm).

The production-state host harness passes view recreation before/during/after
JIT, duplicate callbacks, failed-preparation retry and fresh-process checks:
`build/host-tests/check-mewgenics-session.py` in the cached Madeira checkout.
The host test does not establish that iPadOS will retain a suspended process.
The signed iPad build succeeds and passes `codesign --verify --deep --strict`.
The user authorized installation, and the update was installed and launched
on the physical M5 iPad. Startup logs confirm JIT flags and one runtime launch
in the debugged game process. Device background/return behavior and the
removed FPS label still await the user's check. Installation, launch and
startup logs are saved as `install-resume-no-fps.log`,
`launch-resume-no-fps.log` and `run-resume-no-fps.log` in the diagnostics folder.

The next update defaults to the optimized, development-signed Release build.
The standalone launcher suspends hidden log parsing, file-tail polling and
UI flush timers while file logging continues. Detailed graphics timing and
window inspection are opt-in; functional presentation counters, foreground
activation and ProMotion remain active. Native resolution, original framing,
audio and gesture mappings are unchanged.

The Release build succeeds and passes strict signature and entitlement
checks. Production-method host tests pass for log suspension/resume, continued
file logging, concurrent callbacks, gestures and session recreation. The
diagnostic preset tests also pass, preserving unrelated settings. The user
skipped the before/after comparison, so no frame-rate gain is claimed. With
explicit permission, this update was installed and launched on October 1.
The `off` diagnostic preset preserved every unrelated runtime setting.
Startup logs confirm JIT enabled and one runtime launch in the debugged game
process (PID 7872). Gameplay performance after this update remains unmeasured.
Installation, configuration, launch and startup logs are preserved as
`install-optimized-quiet.log`, `configure-optimized-quiet.log`,
`launch-optimized-quiet.log` and `run-optimized-quiet.log` in the diagnostics folder.

The user confirmed that disabling both Vignette Flicker and Noise & Grain
stops the reported background blinking, and requested no flicker code fix.
These are existing game settings; no shader or artwork changes are applied.

The user now requires permission before any app
restart; do not install an update or relaunch the running game without it.

Do not describe the port as finished or the testing profile as the final
graphics solution. Sustained 120 FPS remains unverified.
Diagnostics are preserved under the cache's `diagnostics/madeira` directory.
The user supplies screenshots; do not capture the iPad screen automatically.

Upstream: [Madeira](https://github.com/willfaust/Madeira),
[Mesa Windows distribution](https://github.com/pal1000/mesa-dist-win),
[Zink documentation](https://docs.mesa3d.org/drivers/zink.html),
[MoltenVK](https://github.com/KhronosGroup/MoltenVK/releases/tag/v1.4.2),
[SPIRV-Cross naming fix](https://github.com/KhronosGroup/SPIRV-Cross/commit/cd3fcb2603ede297edb90ab5a679e4ac814055e2),
[Apple ProMotion timing and controlled testing](https://developer.apple.com/documentation/quartzcore/optimizing-iphone-and-ipad-apps-to-support-promotion-displays).
