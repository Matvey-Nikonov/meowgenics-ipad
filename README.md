# Mewgenics for iPad

An experimental, standalone iPad launcher for a locally supplied Windows copy of
Mewgenics. It starts the game directly through a patched
[Madeira runtime](https://github.com/willfaust/Madeira), using FEX translation,
Wine, and Mesa Zink over MoltenVK for GPU rendering.

**You must supply your own legally obtained game files.** This repository
contains source, patches, build scripts and configuration examples. It does not
provide the game executable, resource archive, commercial artwork, saves or a
ready-to-play IPA. It is an unofficial project and is not affiliated with the
game's developers.

**Free and open source:** the project's original code and documentation use
[GNU GPL v3 or later](LICENSE). See [License](#license) and [Credits](#credits).

## What works

- Direct launch into Mewgenics, without Madeira's library interface.
- Landscape display at the iPad's native pixel dimensions, preserving the
  game's original 16:9 framing.
- Touch and Apple Pencil pointer input, hover, dragging and gesture shortcuts.
- Mixed audio, so other audio and picture-in-picture can continue playing.
- ProMotion support and removal of the previous 60 FPS presentation limit.
- Development-signed Release builds with JIT enabled through StikDebug.

Gameplay, clean audio and the principal Pencil gestures were tested on an iPad
Pro 13-inch M5 running iPadOS 27.0.1. Some scenes reach 120 FPS; sustained 120 FPS
throughout the game is **not** established. Loading and JIT warm-up can be slow.
Other iPads and OS versions have not been validated by this project.

## Build your own

Follow **[the setup guide](docs/SETUP.md)** for dependencies, signing, JIT setup,
game compatibility and installation. The build requires an Apple Silicon Mac,
Xcode, a physical iPad, and your own Apple development signing identity.

The compatibility patch currently accepts only the tested **1.1.b21239**
executable with the SHA-256 listed in the setup guide. Other game builds fail
closed instead of applying offsets to an unknown executable.

- [Touch and Pencil controls](docs/CONTROLS.md)
- [Runtime implementation and test history](Runtime/README.md)
- [Personal configuration template](config.example.sh)
- [Publishing and source-only checks](docs/PUBLISHING.md)
- [License and third-party notices](THIRD_PARTY_NOTICES.md)

`Mewgenics.xcworkspace` opens the runtime after preparation. The separate
`MewgenicsIPad.xcodeproj` is an earlier archive/SWF inspection tool; it is not the
game launcher.

## What stays local

Keep game files outside the repository and point `MEWGENICS_GAME_DIR` at them.
Personal settings belong in the ignored `.local/config.sh`. Downloads, patched
executables and compiled dependencies go into `MEWGENICS_CACHE`, outside the
source tree. An optional personal icon also stays outside the repository.

Do not attach game files, saves, signing material, pairing records or unreviewed
device logs to issues or pull requests. When reporting a problem, include the
device model, OS version, game version/hash, reproduction steps and a relevant
redacted log excerpt.

## Known limits

JIT is required for this route. Each new app process needs the StikDebug setup;
the game itself runs locally after launch. Cold-start JIT without a network
connection has not been validated. iPadOS can terminate a backgrounded process,
so reliable resume after every background interval is not guaranteed.

Black bands preserve the game's authored 16:9 content on a 4:3 iPad. The
experimental expanded canvas exposes artwork outside the intended view and is
disabled. Noise & Grain and Vignette Flicker are disabled in the recommended
settings because the tested configuration showed distracting background flicker.

This repository does not publish binary releases or game assets. Dependency
licenses and upstream notices continue to apply to the runtime and its patches.

## License

The project's original code and documentation are licensed under
**GPL-3.0-or-later**, consistent with Madeira. You may use, study, modify and
redistribute them, including commercially, under the license's terms. When
distributing covered modifications, retain the notices and provide the
corresponding source under the applicable GPL terms. The software comes without
warranty. Read the complete [license](LICENSE) for the conditions.

Third-party components keep their own licenses and applicable exceptions; see
[the source and dependency notices](THIRD_PARTY_NOTICES.md). This license does
not grant rights to Mewgenics itself, its assets, or proprietary dependencies.
Each player must supply their own legally obtained game files.

## Credits

This project builds on the work of these upstream projects and their contributors:

| Project | Contribution |
| --- | --- |
| [Madeira](https://github.com/willfaust/Madeira), by Will Faust and contributors | iOS runtime, Windows-game launch infrastructure and integration of the translation layers. |
| [FEX-Emu](https://github.com/FEX-Emu/FEX) and [Madeira's FEX fork](https://github.com/willfaust/FEX) | Translation of x86-64 game code to ARM64. |
| [Wine](https://www.winehq.org/) and [Madeira's Wine fork](https://github.com/willfaust/wine) | Windows API compatibility. |
| [Mesa / Zink](https://docs.mesa3d.org/drivers/zink.html) and [Mesa Windows distribution](https://github.com/pal1000/mesa-dist-win) | OpenGL rendering through Vulkan and the Windows Mesa builds. |
| [MoltenVK](https://github.com/KhronosGroup/MoltenVK) | Vulkan implementation over Apple's Metal graphics API. |
| [DXMT](https://github.com/3Shain/dxmt) and [Madeira's DXMT fork](https://github.com/willfaust/dxmt) | Madeira's Direct3D/Metal infrastructure; this game's tested rendering path uses Zink. |
| [StikDebug](https://github.com/StikDebug/StikDebug) and [idevice](https://github.com/jkcoxson/idevice) | On-device debugger/JIT setup and device communication. |

LLVM/llvm-mingw, FreeType, FFmpeg, GnuTLS and other dependencies also retain
their upstream credits and licenses. The pinned sources and license notices
are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
