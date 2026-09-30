# Build and install your own copy

Run the commands below from the repository root unless a step says otherwise.
They build a standalone Mewgenics launcher for a **physical iPad**. This is not a
Simulator workflow or an App Store build.

## 1. Prepare the Mac and iPad

The tested development environment uses an Apple Silicon Mac and Xcode 27 with
the iOS SDK and Metal Toolchain. Install and open Xcode once, select its developer
directory if multiple versions are installed, and accept its setup prompts.
Install the Metal Toolchain through Xcode's component settings if it is missing.
Check the selected tools:

```sh
xcodebuild -version
xcrun --sdk iphoneos --show-sdk-path
xcrun --sdk iphoneos --find metal
```

Install the command-line dependencies with Homebrew:

```sh
brew install python@3.12 cmake ninja bison ccache sevenzip llvm pkgconf
```

Ensure `python3` is Python 3.12 or newer and that `7zz`, `cmake`, `ninja`,
`ccache`, Bison 3 and `llvm-objcopy` are available. The runtime script adds the
Apple Silicon Homebrew Bison and LLVM directories to its build PATH. The native
scripts have not been validated on Intel Macs.

Connect and unlock the iPad, approve the computer's Trust prompt, and enable
Developer Mode as requested by Xcode. Add your Apple account in Xcode and use
your own development team and an app identifier you control. The resulting app
must retain `get-task-allow` and the increased-memory entitlement; the build
script checks them. Do not remove these checks to work around provisioning
errors. Signing-account capabilities and profile expiry need to be handled by
your own account.

Choose a cache location with room for the upstream source trees, downloads,
native build outputs and the game staging copy. These are substantially larger
than this source repository. On an external disk, verify that the disk is
mounted before using its path. Use a path without spaces for compatibility with
the upstream native build scripts.

## 2. Build and configure StikDebug

Follow the current
[official StikDebug source-build instructions](https://github.com/StikDebug/StikDebug#building-from-source).
The basic sequence is:

```sh
git clone https://github.com/StikDebug/StikDebug.git /path/to/local/StikDebug
open /path/to/local/StikDebug/StikDebug.xcodeproj
```

In Xcode, select the StikDebug target, choose your signing team and a unique
bundle identifier, select the connected iPad, then build and run. Complete any
device trust prompts.

StikDebug also needs a pairing record for **your iPad** and an enabled loopback
VPN such as LocalDevVPN. Follow its
[pairing and VPN instructions](https://github.com/StikDebug/StikDebug#how-to-enable-jit),
import the pairing record, and verify its device connection before continuing.
Keep pairing records private; they do not belong in this repository.

This launcher opens StikDebug with its bundled JIT script when a new game process
needs JIT. A separate Madeira app installation is not required. The tested game
launch returns from StikDebug to Mewgenics automatically. Offline cold-start
behavior is not promised; previously connected VPN/JIT sessions are a different
case from starting everything with no network.

## 3. Set personal build configuration

Clone the public repository, then create the ignored local configuration:

```sh
git clone https://github.com/Matvey-Nikonov/meowgenics-ipad.git
cd meowgenics-ipad
mkdir -p .local
cp config.example.sh .local/config.sh
```

Edit `.local/config.sh` and fill in the values described by the template:

| Variable | Value |
| --- | --- |
| `MEWGENICS_CACHE` | Absolute path outside the repository for dependencies, builds and diagnostics. |
| `DEVELOPMENT_TEAM` | Your Apple development team identifier. |
| `MEWGENICS_BUNDLE_ID` | A unique bundle identifier you control. Keep it stable for updates. |
| `DEVICE_UDID` | The connected physical iPad's identifier. |
| `MEWGENICS_GAME_DIR` | Absolute path to your own Windows game installation. |
| `MEWGENICS_APP_ICON` | Optional path to your own local icon image; omit to use the source-only default. |

Find the device identifier in Xcode's Devices and Simulators window or list
connected devices with:

```sh
xcrun devicectl list devices
```

The script reads `.local/config.sh` as shell configuration. Keep it local, and
review any configuration before sourcing it. Do not put passwords or signing
private keys into it.

## 4. Supply a compatible copy of the game

Use game files obtained through your own licensed copy. This project does not
download the game or provide a license/DRM bypass. Leave the installation outside
the Git checkout. At minimum, the launcher checks for `Mewgenics.exe`,
`resources.gpak` and the graphics DLL supplied by the build tooling; keep the
original installation's required support files with the game.

Only this exact executable is supported by the allocator compatibility patch:

| Field | Accepted value |
| --- | --- |
| Tested game build | `1.1.b21239` |
| `Mewgenics.exe` SHA-256 | `4127cd6a792ae528bca6f65a8873dd61789591937d87656c2b586a5e30eb77ea` |

Check your original file before the long native build:

```sh
shasum -a 256 /path/to/your/game/Mewgenics.exe
```

A matching version label alone is insufficient: different storefronts or
updates may have different executables. If the hash differs, stop here. A new
version requires fresh analysis and validation; do not remove the hash guard or
substitute offsets. Compatibility with every retail installation has not been
established.

The patcher writes a **separate** staged executable with smaller initial memory
reservations. It leaves the source executable and archive untouched. Expanded
canvas mode is not part of the recommended setup.

## 5. Fetch sources and build

```sh
bash Scripts/madeira-runtime.sh prepare
bash Scripts/madeira-runtime.sh native
bash Scripts/madeira-runtime.sh build
```

`prepare` fetches pinned Madeira and its forked dependencies, checks downloaded
archive hashes, applies the source patches, and creates the ignored
`.local/Madeira` link. It also obtains the compatible Mesa and MoltenVK packages
and stages the Microsoft runtime locally. Dependency downloads require network
access. Microsoft's redistributable URL can change contents; a checksum failure
must be investigated, not bypassed.

`native` builds the required native libraries. `build` produces an optimized
Release app with development signing and verifies the app signature and required
entitlements. Release is intentional: JIT still needs development debugging
access. To build a Debug artifact, set `MEWGENICS_CONFIGURATION=Debug` consistently
for both build and install.

After preparation, open `Mewgenics.xcworkspace` if you want to inspect the runtime
in Xcode. The runtime scheme is `Madeira`; the installed app is Mewgenics. The
separate `MewgenicsIPad.xcodeproj` only inspects archives and SWF files.

Preserve the dependency pins. In particular, the GPU path uses **Mesa 25.1.9**
with **MoltenVK 1.4.2**; swapping in the software fallback's Mesa version breaks
this verified combination.

## 6. Install, initialize and configure

Keep the iPad unlocked and LocalDevVPN connected:

```sh
bash Scripts/madeira-runtime.sh install
bash Scripts/madeira-runtime.sh game
bash Scripts/madeira-runtime.sh configure
bash Scripts/madeira-runtime.sh launch
```

`game` transfers your local game files, stages the compatibility-patched
executable and installs the matching GPU graphics DLLs. No game data becomes
part of the Git repository. The first `configure` creates native GPU defaults;
it reports that game settings do not exist yet. On first launch, let the runtime initialize its Wine
prefix and let the game reach its initial menu. This creates the runtime and
game configuration files.

**Save if necessary and close Mewgenics before the next command.** The game must
not be writing its settings while they are updated:

```sh
bash Scripts/madeira-runtime.sh configure
bash Scripts/madeira-runtime.sh launch
```

`configure` applies the recommended native-resolution Zink runtime options and
updates only recognized game settings, preserving unrelated settings and saves.
The profile uses 100% render scale, MSAA off, VSync off, independent rendering
with a 120 FPS limit, and no Noise & Grain or Vignette Flicker. The game's
simulation update rate remains 60. Original 16:9 framing is retained.

The display requests the iPad panel's maximum refresh rate. A 120 FPS limit is
not a guarantee that all scenes can render at 120 FPS. Allow the game to warm up
before judging performance. See [the control guide](CONTROLS.md) for Pencil and
touch gestures.

## Updates, diagnostics and recovery

For an app-only update, keep the same bundle identifier and signing identity,
close the game after saving, then build and install again. Do not uninstall the
app as a routine update step: its container holds the Wine prefix and saves.
Back up that container with your normal device/Xcode workflow before experiments.
The `game` command is not required for an app-only update.

Diagnostics are quiet by default. These commands change flags for the next
launch and do not restart the game:

```sh
bash Scripts/madeira-runtime.sh diagnostics stats
bash Scripts/madeira-runtime.sh log
bash Scripts/madeira-runtime.sh diagnostics off
```

Use `diagnostics full` only for a targeted investigation because detailed probes
add work. Logs go under your cache's `diagnostics/madeira` directory. Inspect and
redact them before sharing.

| Symptom | Check |
| --- | --- |
| Unsupported executable hash | Verify the exact supported build; do not bypass the patcher's guard. |
| JIT request fails | Verify StikDebug pairing, the VPN connection, Developer Mode, provisioning and the signed debugging entitlement. |
| Missing game installation | Check `MEWGENICS_GAME_DIR`, transfer completion and the files named in the error. |
| Black screen with audio | Check that both Mesa DLLs are from the matching Zink package and that the runtime uses the Zink profile. |
| 60 FPS ceiling | Check independent rendering/120 FPS settings, device refresh capability and Low Power Mode; rerun `configure` only with the game closed. |
| Background return starts over | The OS may have terminated the process; background retention is not guaranteed. Save before leaving. |
| Download checksum changes | Stop and validate the upstream artifact/version before changing a pinned hash. |

For host-only checks, `python3 Tests/test-runtime-diagnostics.py` does not require
an iPad. The archive/SWF fixture tests can run without game data using
`MEWGENICS_CACHE_DIR=/path/to/test-cache bash Scripts/test-core.sh`. These checks
do not establish device performance or compatibility with another game build.
