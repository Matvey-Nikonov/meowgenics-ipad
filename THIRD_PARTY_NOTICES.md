# Source and dependency notices

This is an unofficial compatibility project. Mewgenics, its executable, game
data, music and artwork are not included or licensed by this repository. Users
supply their own game installation; generated executable patches stay local.

Original project code and documentation are offered under GPL-3.0-or-later
(see [LICENSE](LICENSE)). Modified third-party code retains its applicable
upstream license and notices. This declaration does not relicense upstream
material or proprietary game/Apple/Microsoft files.

| Material | Source and license |
| --- | --- |
| `Runtime/Patches/madeira.patch` | [Madeira](https://github.com/willfaust/Madeira/tree/ee3d5c0223559abfc4b90cb99aab5dfadbc0bcc5), GPL-3.0-or-later, with its [Apple converter exception](LICENSES/Madeira-Apple-exception.md). |
| `Runtime/Patches/fex.patch` | [FEX fork](https://github.com/willfaust/FEX/tree/26859e184ad90f0e811d7f8bbd943a4b1573a2c3), [MIT](LICENSES/FEX-MIT.txt). |
| `Runtime/Patches/dxmt.patch` | [DXMT fork](https://github.com/willfaust/dxmt/tree/a5e0cd3d41bf248fd1c030a2e1c515ba3522f4ef), [MIT](LICENSES/DXMT-MIT.txt); embedded components retain their own notices. |
| `Runtime/Patches/wine.patch` and Wine-derived baseline in `Tests/test-wine-path-resolution.py` | [Wine fork](https://github.com/willfaust/wine/tree/074e0e368b634fe6e01dc774a7221410d4d92458), LGPL-2.1-or-later; see [license text](LICENSES/Wine-LGPL-2.1.txt) and source attribution in the test. |

The scripts obtain other dependencies directly from upstream, outside this Git
repository: Mesa, MoltenVK, LLVM/llvm-mingw, FreeType and the Microsoft Visual C++
runtime. Madeira also supplies/builds components such as FFmpeg and GnuTLS.
Their source trees and bundled notices remain authoritative for their licenses.
StikDebug is a separate application, obtained/built from
[its project](https://github.com/StikDebug/StikDebug), with its own AGPL-3.0 terms.

The setup pins source revisions and verifies downloaded artifact hashes.
`build/stage-licenses.sh` in the prepared Madeira checkout refreshes its bundled
notices. This repository publishes source only, not an IPA or third-party binary
distribution. Any future binary release needs its own complete corresponding
source and dependency-notice preparation.
