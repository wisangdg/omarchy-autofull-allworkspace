# AutoFull Allworkspace

An [Omarchy](https://omarchy.org) shell **bar plugin** that makes **every new
window open fullscreen**. One icon in the bar, one keyboard shortcut, two
fullscreen flavours.

![preview](preview.png)

## Features

- Every newly opened window starts fullscreen.
- Two modes: **true fullscreen** (`SUPER+F`) or **full width / maximized**
  (`SUPER+ALT+F`).
- Toggle on/off from the bar icon or with `SUPER+ALT+X`.
- **Right-click the bar icon** to switch mode.
- Windows already open are adjusted at toggle time; windows opened afterwards
  follow the rule automatically.
- **Does not fight you.** If you manually un-fullscreen a window (`SUPER+F`),
  it stays that way — even across config reloads. Reopen the app, or toggle
  off → on, to expand again.
- State persists across reloads and reboots.
- Failed config reloads restore the previous rule and saved mode.
- Honors `XDG_STATE_HOME` and `XDG_CONFIG_HOME` (including custom paths).

## Install

### From git (recommended)

```bash
omarchy plugin add https://github.com/wisangdg/omarchy-autofull-allworkspace --enable
```

The bar icon appears immediately and works on its own (it uses the script
bundled inside the plugin).

### Add the keyboard shortcut (optional)

Copy the helper onto your `PATH`:

```bash
install -Dm755 ~/.config/omarchy/plugins/wdg.autofull/bin/omarchy-autofull-workspace \
  ~/.local/bin/omarchy-autofull-workspace
```

Add the binding to `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + ALT + X", "AutoFull Allworkspace (toggle)", "omarchy-autofull-workspace")
```

Then reload Hyprland (`hyprctl reload`).

## Usage & shortcuts

| Action | Shortcut | Works out of the box |
|---|---|---|
| Toggle on / off | **`SUPER + ALT + X`** | after adding the binding |
| Toggle on / off | **left-click the bar icon** | yes |
| Switch mode | **right-click the bar icon** | yes |
| True fullscreen (mode) | `SUPER + F` | Hyprland default |
| Full width (mode) | `SUPER + ALT + F` | Hyprland default |

The icon is dimmed when AutoFull is **off** and highlighted when it is **on**.
Hover it for a tooltip showing the current state and mode.

## Modes

| Mode | Equivalent | Result |
|---|---|---|
| `maximized` *(default)* | `SUPER+ALT+F` | fills the workspace, bar and gaps stay visible |
| `fullscreen` | `SUPER+F` | true fullscreen, bar hidden |

Switch mode from the icon (right-click) or from the command line:

```bash
omarchy-autofull-workspace mode fullscreen
omarchy-autofull-workspace mode maximized
omarchy-autofull-workspace bar      # print "on:maximized", "off:fullscreen", ...
```

Or edit `~/.config/omarchy/autofull-workspace.conf`
(`$XDG_CONFIG_HOME/omarchy/autofull-workspace.conf` when set):

```
mode=maximized
```

While the bar widget is running, it automatically applies edits to this file.
Without the widget, run `omarchy-autofull-workspace sync` after editing. Sync
does nothing while AutoFull is off, and an unchanged mode never re-expands
windows you manually restored. While enabled, `status` and `bar` report the
installed rule's mode, so a pending or failed edit is not shown as applied.

## How it works

The plugin writes a plain Hyprland Lua toggle:

- `~/.local/state/omarchy/toggles/hypr/autofull-workspace.lua` — the window rule
  (`o.window(".*", { maximize = true })` or `{ fullscreen = true }`), which is
  auto-loaded by Omarchy on `hyprctl reload`.
- Enabling writes the rule and expands currently open windows once.
- Disabling removes the rule and clears fullscreen/maximized on every window.
- The rule only ever affects windows opened while it is active; it is never
  re-applied on reload, which is why manual changes stick.
- Rule and configuration writes are atomic, and commands are serialized.
  If reload fails, the previous files are restored and a recovery reload is
  attempted. Failures are reported instead of sending a success notification.
- If adjusting existing windows fails after a successful reload, the installed
  rule remains active and the command reports that the window update failed.

The paths above use the default XDG directories. When `XDG_STATE_HOME` or
`XDG_CONFIG_HOME` is set to a nonempty value, both the helper and widget use
that location instead. A bare `hyprctl reload` does not synchronize a manually
edited mode; use the widget or the `sync` command.

## Development checks

```bash
bash -n bin/omarchy-autofull-workspace
python3 -m unittest discover -s tests -v
AUTOFULL_QML_TESTS=1 python3 -m unittest discover -s tests -v
```

Tests use temporary XDG directories and a mock `hyprctl`; they never resize
desktop windows. The last command also tests the actual widget in headless
Quickshell with minimal host UI stubs.

## Files

```
wdg.autofull/
├── manifest.json                 plugin manifest
├── AutoFull.qml                   bar widget (icon, tooltip, click handling)
├── bin/omarchy-autofull-workspace toggle + mode CLI
├── preview.png / preview.svg     marketplace preview
├── README.md
└── LICENSE
```

## Uninstall

```bash
"${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/wdg.autofull/bin/omarchy-autofull-workspace" off
omarchy plugin remove wdg.autofull
rm -f ~/.local/bin/omarchy-autofull-workspace \
      ~/.config/omarchy/autofull-workspace.conf
```

Then remove the `SUPER + ALT + X` binding from
`~/.config/hypr/bindings.lua`.

## License

MIT — see [LICENSE](LICENSE).
