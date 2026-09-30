# Touch and Apple Pencil controls

The game keeps its existing desktop interface. Touch and Pencil positions map
directly to the game cursor, including the original letterboxed play area.

| Action | Touch | Apple Pencil Pro |
| --- | --- | --- |
| Move pointer | Touch and drag | Hover, or touch and drag |
| Select / left-click | Tap | Tap |
| Left-button drag | Keep one finger down and drag | Keep the tip down and drag |
| Right-click / context action | Two-finger tap | Squeeze |
| Hold right button / Examine | Two-finger hold | Hold the squeeze |
| Tactical View | Three-finger hold toggles it | Double-tap toggles it |
| Back / Pause / Escape | Three-finger tap | Use the same touch gesture |
| Zoom | Pinch, or two-finger vertical drag | Use the same touch gesture |
| Show keyboard | Four-finger hold | Use the same touch gesture |

The small `TACTICAL` indicator means Left Control is being held for Tactical
View. Repeat the toggle to release it. Synthetic held keys and buttons release
when the app loses focus, avoiding a stuck button when switching apps.

Combat actions remain available through the game's visible buttons. A keyboard
can provide its normal shortcuts, including `1`, `2`, `3`, `Q`, `W`, `E`, `R`,
`T` and `Y`; consult the game's Controls screen for current bindings. The
gesture layer does not replace or alter those bindings.

Pencil hover, contact dragging, squeeze, double-tap and three-finger Back/Pause
were confirmed on the test iPad. Held Examine, pinch/scroll and keyboard access
are implemented and covered by host logic tests, but have not all been confirmed
in a complete device playthrough. Squeeze requires Pencil Pro; hover requires
compatible Pencil/iPad hardware. Touch alternatives remain available.

To disable these added multi-touch/Pencil shortcuts, set
`env.MEWGENICS_GESTURES = 0` in the device's `Documents/madeira.cfg` while the game
is closed, then relaunch. Normal direct pointer input remains the underlying
control method.

The app is landscape-only. Its status bar and FPS overlay are hidden during
gameplay. The black bands are intentional: expanding the game canvas revealed
content outside the authored view, so the current setup preserves all intended
content without stretching or cropping.
