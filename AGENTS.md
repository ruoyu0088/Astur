# AGENTS.md — Astur

Guidance for AI agents (and humans) working on this repo. Read this first.

## Who keeps these docs

The repository owner does not edit `AGENTS.md`, `CLAUDE.md` or
`CONTRIBUTING.md`, and does not log their changes here: they commit code. The
coding assistant owns these three files — keep them true, and fold whatever it
learns about the project (a new thread, a trap, a deliberate oddity) into them
so the next session starts from the map, not from the source.

Two kinds of docs, two rules:

- **Assistant docs** — this file, `CLAUDE.md`, `CONTRIBUTING.md`. Edit freely
  when they drift from the code.
- **User-facing docs** — `README.md`, the config templates in
  `crates/astur-config/src/lib.rs`, and the schema `tools/gen_schema.py` writes
  into `tools/astur_settings.py`. After the owner commits, check these against
  the code; if they disagree, ask the owner before changing them.

Audit after every owner commit:

1. `git log --oneline <last-audited>..HEAD`, then read the diffs. `<last-audited>`
   is the tip of `main` the previous session left behind; when unsure,
   `git log --oneline -15` and start from the first commit you do not recognise.
2. New or renamed config key / hotkey? Then README's hotkey table and feature
   list, the template comment, `Config::defaults()`, the parser, and the
   regenerated schema all need to know. `python tools/gen_schema.py` must report
   as many keys as the templates carry (count both).
3. Defaults still agree? The test
   `reload_groups(&Config::defaults(), &default_config()).is_empty()` covers the
   live-reload fields; for the rest, compare the template's values with
   `defaults()`.
4. `cargo build` / `test --workspace` / `fmt --check` / `clippy -D warnings`,
   then ask before touching user-facing docs.

## What Astur is

A fast, free, portable **tiling window manager for Windows 10/11**, shipped as a
single Rust `.exe` with no installer and no required config. Core hooks:

- **Alt + left-drag** — move any window from anywhere on it (no title bar needed).
- **Alt + right-drag** — resize from the nearest corner (red bracket marker).
- **Tiling** — `dwindle` (spiral, default), `master`, `columns`, `grid`,
  `monocle`, or Niri-style `scrolling` (column strip, off-screen columns
  parked outside the virtual screen, tabbed columns).
  Layout is per monitor (`monitor_layouts`).
- **Up to 20 virtual workspaces** (`MAX_WORKSPACES`), shared or per-monitor.
- **Per-monitor status bar** (workspace pills, title, clock, CPU/RAM/battery,
  keyboard language, disk, uptime, custom command text, music buttons, logo;
  palettes, strip/floating/islands/pills shapes, anti-aliased shapes on a
  cached DIB, Segoe Fluent / MDL2 glyph icons, per-widget pill colours,
  powerline segments, hover highlight; per-widget left/right/middle click
  actions from astur-config `BAR_ACTIONS` run by the manager
  (`Cmd::BarAction` -> `run_bar_action`, sharing `run_action` with extra
  hotkeys); `monitors` picks the screens; 9 preset looks as data in
  astur-config `BAR_PRESETS`, set through the editor's individual keys; the
  focused monitor's bar rings its active workspace mark with `focus_border`,
  so a row of bars says which screen has the keyboard; app icons come from
  the window itself (`WM_GETICON`, then its class icon, resolved on the icon
  worker) and fall back to the exe file's icon, so each Python script shows
  the icon it sets; the icon worker re-reads those icons every 2.5 s, so a
  window that swaps its own (a chat badge, a dirty mark) updates without a
  restart).
- **Workspace-switch animation** — overlay compositor: off/slide/spring/fade.
- **Window glide** — windows animate to their tile slot on open/move/resize/
  re-tile/scroll via an overlay of live DWM thumbnails (off/glide).
- **App launcher** — Alt+Space opens a fuzzy app picker (Start Menu shortcuts),
  hook-driven with no foreground focus.
- **Swap-workspace mode** — main+P: the bar says SWAP MODE, the next key
  picks the workspace to swap this one's windows with (digit, workspace key,
  or main+A / main+D for previous / next); layouts stay per workspace.
- **Minimize** — main+Q minimizes the focused window; pressing it again
  within a moment restores every window that key minimized.
- **Restore all** — main+V (`key_restore_all`) brings back every minimized
  window of the workspace however it was minimized: the floats come back in
  front, the tiles re-flow, and the focus stays put unless it was minimized.
- Coloured DWM borders, unfocused dimming, focus-follows-mouse, per-app rules,
  live config hot-reload. A window an app brings up on another workspace is
  followed there: taskbar activation holds the foreground, and a window we hid
  for its workspace (`was_hidden_by_us`, e.g. a browser re-shown by a link
  click from another workspace) counts as intent to be seen too, so `Cmd::Add`
  switches instead of leaving it visible over the active tiles. The hooks
  clear `HIDDEN_BY_US` in the SHOW handler itself, so that fact rides on
  `Cmd::Add`'s third field: read it there, never in the manager, which runs
  after the marker is gone.

The Astur modifier is the **main key** (`main_key`, config `MainKey`): Right Alt
by default, fully reserved (apps never see it; Right Alt + an unbound
typing/editing/navigation key is swallowed, never passed bare — see
`swallow_unbound`; the other Alt is untouched; Alt+Tab still works via a synthetic
Alt). Left Alt can be reserved the same way (`lalt`). Caps Lock can be reserved
the same way. Win, Alt or Ctrl+Win are passed
through instead: only bound keys are swallowed, plus the 0xE8 mask key so Start /
menu bars don't open (`needs_mask`). Every hotkey is one load from the lock-free
`BINDS` table, filled from astur-config's pure `compile_keys`.

## Project goals (the bar to hold)

1. **Zero-setup.** Run the exe, Alt-drag works immediately. No config to start.
2. **Tiny + fast.** Single portable exe. The global mouse hook is the hottest path
   in the whole OS input stream — it must never block, allocate, or lock
   needlessly. Latency over features.
3. **Hooks are sacred.** `mouse_proc` / `keyboard_proc` sit on the OS-wide input
   path: no lock without an atomic guard, no allocation, no `SetWindowPos`. Push a
   `Cmd` and let the manager or a worker do the work.
4. **Never break window management.** Cosmetics (animations, bar) are layered
   *over* a switch/tile that already happened correctly and instantly. A dropped
   or failed animation must never lose or misplace a window.
5. **Tile placement is INSTANT.** `animate_to` is a historical name — it places,
   it does not animate. Real glide goes through the snapshot overlay, never
   per-frame real-window `SetWindowPos` (tried, removed).
6. **Smooth.** Beat komorebi/GlazeWM/Seelen on motion polish — that is the
   headline differentiator (see `README.md` comparison table).
7. **Honest docs.** If a feature is staged or removed, the README must not claim
   it.
8. **Keep the testable parts Win32-free.** `astur-config` has zero Win32;
   `layout.rs` is `RECT` maths only. That is what makes them unit-testable.

## Build / run / quit

Cargo workspace (v2). Astur Lite = the frozen `v1.0.0` tag; this tree is the full
"Astur".

```bash
cargo build --release -p astur # target/release/astur.exe  (LTO, strip, panic=abort)
cargo build                    # fast debug build of the whole workspace
cargo run -p astur             # run the WM from source
```

Quit: tray Quit or `Ctrl+C` in the console (runs `restore_all_windows`: shows
hidden windows and unparks parked ones; an exit watchdog ends the process 2 s
after the restore starts, so a hung app cannot keep it alive), or kill the
process (the next launch's crash rescue does the same from
`~/.astur/rescue.lst`).

Config lives in `%USERPROFILE%\.astur\astur.conf` + `navbar.conf`, both created
on first run, fully commented, **hot-reloaded on save**.

Toolchain wrinkles:

- Default toolchain is MSVC. If `link.exe` / `vcvars` is not reachable in the
  shell, verify compilation with the self-contained GNU toolchain instead:
  `cargo +stable-x86_64-pc-windows-gnu build --target x86_64-pc-windows-gnu`
  (add `-p astur` for the WM alone).
- Crate downloads failing with a cert-revocation error
  (`CRYPT_E_NO_REVOCATION_CHECK`): prefix with `CARGO_HTTP_CHECK_REVOKE=false`.
- Do not build the MSVC target from Git Bash: MSYS `link` shadows the real
  `link.exe`.
- The release profile is LTO + strip + `panic = "abort"`, and `codegen-units = 1`
  is what makes "one compilation unit" literal.
- Rebuilding while Astur runs fails with "Access is denied" on
  `target\release\astur.exe`: close it first (tray Quit, or `WM_CLOSE` to the
  `astur_marker` / `astur_bar` / `astur_sink` windows so it restores the
  windows it hid).

## File map (workspace)

| File | Lines (approx) | What |
|---|---|---|
| `crates/astur/src/main.rs` | ~28700 | Everything Win32: hooks, worker threads, manager, scrolling strip model, bar, tab bars, compositors, launcher, file search, system menu. One big file by preference: splitting a crate into modules does not change Rust build time (still one compilation unit, and `codegen-units = 1` in release makes it literal). |
| `crates/astur/src/layout.rs` | ~1300 | Pure tiling geometry (dwindle, master, columns, grid, monocle, scrolling strip: spans, offset clamp, peek/park `classify`, `park_spot`) + tests. `RECT` type only, no Win32 calls. |
| `crates/astur/src/yasb.rs` | ~800 | GlazeWM-compatible workspace WebSocket API for YASB (loopback only, off by default). |
| `crates/astur-config/src/lib.rs` | ~5800 | `Config` struct, `LAYOUTS` (the one list of layout names), bar `PALETTES`, `BAR_PRESETS`, `BAR_ACTIONS` / `BAR_CLICK_DEFAULTS` and the shared bar formatters (`format_clock`, `format_date`, `workspace_label`, `bar_on`), documented-default file templates, key/value parser. **No Win32** — pure data, shared with the settings GUI (aliased `config` in the WM). |
| `tools/astur_settings.py` | ~1500 | The settings editor users run: one file, Python 3 + tkinter, no third-party packages. It edits both `astur.conf` and `navbar.conf` as text (`ConfFile`: `get` / `set` per line, comments and order kept, `.bak` on save) with widgets driven by `SCHEMA_DATA`; `RecordsDialog` edits the `;;` record keys (window rules, extra hotkeys, launcher entries, system actions) and the `widget:colour` list, `WindowPicker` fills exe / class / title from the open windows (ctypes `EnumWindows`), `Ctrl+F` searches every section, and `watch_disk` reloads a file changed from outside. `python tools/gen_schema.py` regenerates `SCHEMA_DATA` from the templates in `crates/astur-config/src/lib.rs`; `--selftest` round-trips both files. The WM starts it with `settings_python` (empty = `python` on PATH) - see `tray_open_settings` in `crates/astur/src/main.rs`. |
| `Cargo.toml` (root) | — | `[workspace]` manifest + release profile. WM deps live in `crates/astur/Cargo.toml`. |

`main.rs` is large but sectioned with `// ====` banners. Use the function map
(`grep -n "^fn \|^unsafe extern\|^struct \|^static " crates/astur/src/main.rs`).

## Website (GitHub Pages)

`docs/` is the project site, published from `main` / `docs` at
`https://ruoyu0088.github.io/Astur/`. It is deliberately plain: no build step,
no JavaScript, no external requests, and every local path relative (the project
page lives under `/Astur/`).

- `docs/index.html` — landing page: hero mock, six feature cards, layout
  diagrams (including scrolling), bar/launcher/keyboard sections, install, FAQ.
- `docs/docs.html` — the user manual: getting started, tiling, layouts,
  workspaces, scrolling, floating, bar, launcher/menu, hotkeys, settings,
  config files, window rules, troubleshooting. No build-from-source or
  internals sections.
- `docs/style.css` — all styling, including the CSS-only keyboard tabs.
- `docs/assets/screens/` — screenshot slots plus `README.md`, the Chinese
  shot list the owner follows when replacing the placeholders. Replace a PNG
  with the same filename; the page follows the image's own aspect ratio, so a
  close size is enough. Do not rename the files or edit the HTML.
- Preview with `python -m http.server -d docs 8123`.

When a release changes a default, a config key or the settings editor, update
`docs/docs.html` and the landing claims as part of the release audit, then
check `python tools/gen_schema.py` still agrees with the templates. The
keyboard diagram is hand-written: keep its labels short (a 1u key fits about
six characters at the rendered size) and keep the tiling/scrolling tabs in
sync with the real bindings.

## Threads (mental model)

The process is a set of single-purpose threads talking over `Mutex`/`Condvar`
queues. Keep it that way — do not move work onto the hooks (main thread).

- **Main thread** — installs and runs the hooks: `mouse_proc` / `keyboard_proc`
  (`WH_MOUSE_LL` / `WH_KEYBOARD_LL`) and `win_event_proc` (out-of-context
  WinEvents). Hooks must return fast: push a `Cmd`, do no work, no lock without
  an atomic guard (`ANY_DRAG`/`MAIN_DOWN`/`BIND_LIVE`/`SCROLLMON_N` let them early-out).
  Also owns the bar windows, the tray and the scrolling layout's tab-bar
  windows (`astur_tabs`, synced from the manager's `TAB_SNAPSHOT` by
  `tab_bars_sync`; clicks push `Cmd::TabClick`, nothing places windows).
- **Manager loop** (`manager_loop` / `Manager`) — owns all window/workspace/
  strip state. Drains the command queue (`CMDQ`). All `SetWindowPos`/tiling/
  switching/parking here, live Alt-drag placement included (`place_drag_frame`).
  Between commands it also runs the #19.1 border re-assert passes on a
  deadline in its own wait (`BorderRecheck`), with no extra thread.
- **Transition worker** (`transition_worker` / `run_transition`) — owns the
  workspace-switch overlay, pumps its own message loop, GDI-composites frames
  (fade: DWM blends a second, layered overlay instead).
- **Motion worker** (`glide_worker` / `run_window_glide`, thread "glide") —
  window motion overlay (move/open/close/reflow/scroll): live DWM thumbnails
  of already-placed windows over the wallpaper, re-aimed in place while it
  runs (`retarget_glide`). Owns its overlay, pump and every thumbnail.
- **Wallpaper capture** (`wallpaper_capture_worker`) — renders the wallpaper
  backdrop for both compositors (PrintWindow of the wallpaper window only).
- **Cold-snapshot worker** (`cold_worker`) — PrintWindows cold parked tiles
  (blank DWM surface: hidden, minimised, or never on screen since shown) into
  the `COLD` cache so the motion can draw them. Besides the wallpaper capture,
  the only thread that PrintWindows (never the manager, a compositor or a
  hook). A hung app may block it; nothing waits on it.
- **Stats worker** (`stats_worker`) — polls CPU/RAM/battery ~2s for the bar.
- **Slow stats worker** (`slow_worker`, thread "slow-stats") — the disk
  widget's free space (30 s) and the custom widget's command (its own
  interval, killed after 5 s); both can block, so never on the stats worker.
  Idle unless those widgets are listed.
- **Disk writers** (`state_worker`, `mru_worker`, `rescue_worker`) — the
  manager only fills a latest-wins slot; the disk I/O (state, launcher MRU,
  `rescue.lst`) runs here, so a slow disk never delays a command.
- **Focus-follow worker**, **config watcher**, **launcher**, **sysmenu**,
  **icon/file-search workers**, **IPC**, **YASB**, **hook watchdog**,
  **exit watchdog** (spawned only once an exit restore starts) — as named.
- **Focus sink** (`focus_sink_thread`, thread "focus-sink") — owns one hidden
  `astur_sink` window and pumps it. The manager's loop tail
  (`claim_empty_focus`) makes it the foreground when Astur's focus turns to
  nothing (#25), so keys typed then land here, never on the hook thread.

## Conventions

- **No emojis in code.** Monochrome only, UI surfaces only.
- Win32 calls are `unsafe`; keep `unsafe` blocks tight and comment the invariant.
- **Never wait on an app's thread.** A window that stopped pumping makes a
  synchronous ShowWindow, BringWindowToTop, SetWindowPos, SetWindowPlacement or
  SetWindowLongW wait for ever (measured), and the manager thread carries every
  hotkey, so one hung app froze the whole WM. On a foreign window: post the
  show/hide (ShowWindowAsync), the raise and the placement
  (SWP_ASYNCWINDOWPOS), the park (WPF_ASYNCWINDOWPLACEMENT); where the API has
  no posted form (SetWindowPlacement, SetWindowLongW) check IsHungAppWindow and
  skip. Astur's own windows stay synchronous.
- Hot paths: no allocation, no `Mutex` lock unless an atomic guard says there's
  work. Comment *why* a fast-path exists so nobody "simplifies" it away.
- Colours are `COLORREF` (`0x00BBGGRR`) internally; config parses `#RRGGBB`.
- Cosmetic threads get bitmap/rect data by **single-owner hand-off, never
  shared** — a handle the owner gives up, moved rather than copied (the
  incoming workspace snapshot is taken out of the cache; the outgoing capture
  goes to the transition worker and is handed back as the snapshot; a cold
  window's snapshot is taken out of its cache into the motion request and
  freed by the glide worker). Exactly
  one thread owns, and frees, each bitmap at any moment; the owned `Bmp` type
  (no `Clone`) enforces it for snapshots. Deselect, then `GdiFlush`, before
  every hand-off.
- Prefer the simplest built-in Win32 path first; document alternatives + tradeoffs
  in code comments before adding complexity.
- **Writing style.** In chat: lead with the judgement, then the why; terse is
  fine. In code, comments, commit messages and docs: normal prose, no filler.
  Flag every real flaw you see instead of smoothing it over.

## Upstream audit log

"Who keeps these docs" says where an audit starts. This log is the other half:
what upstream's commits turned out to be, so the next session does not
re-derive a verdict that is already settled. Reopen an item only when its
premise changed (the line in its entry says which premise), otherwise start at
the next tip.

**2026-11-22, upstream 2.4.2** — 8 commits on top of merge base `3d9f06f`
(v2.4.1); this tree was 2.8.2, 79 commits ahead. Two change sets and one doc
block: PR #37 (`7decc49` plus review commits `685c817`, `6861677`) with nine
2.4.2 fixes, PR #36 (`4824da2` plus review `b16e97f`) for `#30` Defender false
positives, and `4288a7c` (README Star History). All reviewed; none adopted.

- **`#35` mask at the main key's release instead of at the trigger.** The mask
  exists only for a *passed-through* Win or Alt main key; `needs_mask` is false
  for a reserved key and `mask_main` returns early when `MAIN_VK != 0`. Our main
  key is RAlt and fully reserved, so no path reaches it. Premise to watch: a
  `main_key` of `win` or a passed-through Alt.
- **`#32` keep an app-fullscreen or user-maximised tile as it is across a
  switch.** Our maximise is fill mode (`FILLED` / `FilledWs`: remember the rect
  and the floating state, keep the layout), never Win32 `IsZoomed`, so the
  user-maximised half cannot happen. The app-fullscreen half (F11, a video, a
  borderless game) would still apply to this tree, and was judged not wanted:
  we have our own maximise key and do not recommend Win's. Premise to watch:
  adopting Win's maximise.
- **Focus skips minimised windows.** Already ours, commit `195e57c`: `focusable`
  = not the toggled-away scratchpad and not `IsIconic`, used by `focus_target`,
  `focus_step` and `active_window_rects`.
- **`#33` per-monitor layouts follow screen position after a display change.**
  Only reachable when monitors are hot-plugged, undocked or the machine wakes
  with a different screen set. Premise to watch: multi-monitor hot-plug users.
- **`taskkill` without `/F` leaves Astur running headless.** Real in this tree
  too — the marker is the only `WM_CLOSE` handler and it is hidden, so taskkill
  posts to the visible bars, `DefWindowProc` destroys them, and an open
  launcher's capture flag then eats every key. Judged not worth fixing: ending
  Astur gently is not something we do, and tray Quit / menu Exit cover it.
- **A key held while the launcher or power menu opens stays stuck down.** Real
  here as well: both capture branches eat every non-modifier up without asking
  whether the system still holds the key. Judged not worth it — it takes a
  non-modifier held while the popup is opened, which our hotkeys do not do.
- **Scratchpad `#22`** — a toggled-away scratchpad counted as an occupied
  workspace (bar pill, YASB), re-show before clearing state on reload, un-park
  on return, Notepad in the settings app list. Cosmetic in our use.
- **Administrator mode** — launches through Explorer, custom bar widget off
  while elevated, IPC accepting elevated clients only. Not adopted; our own
  elevation checks (`process_elevated`, `foreground_elevated`, the owner-only
  pipe descriptor) already cover the part we care about.
- **`#30` Defender false positives** (`Trojan:Win32/Bearfoos.A!ml` on an
  unsigned exe) — not adopted, but the premise to watch is concrete: this tree
  still spawns a hidden `cmd /C start` from `launch_now`, `astur.rc` still
  carries only the icon (no `VERSIONINFO`, no manifest), and the clipboard
  listener is registered unconditionally. If a Defender verdict ever hits this
  build, those three are the first to change. Note that half of that patch has
  no target here: there is no `astur-settings` crate (the editor is
  `tools/astur_settings.py`) and no `packaging/` installer.
- **`4288a7c`** — README Star History block, docs only; our README is our own.

The diffs were read as combined patches kept in `.git/upstream-review/`
(untracked by design, gone with a fresh clone); regenerate them from
`git format-patch 3d9f06f..upstream/main` rather than trusting that folder.
