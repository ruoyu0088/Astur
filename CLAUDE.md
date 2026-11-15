# CLAUDE.md — Astur

Read this first, every session. `AGENTS.md` has the map of the code, the
threads and the conventions.

## Standing order: keep the docs true

**A change that makes the docs wrong is not finished until the docs are right.**

- Behaviour, a key, or a config option changed -> update `README.md` (hotkey
  table, feature list) and, for a key, the template comments in
  `crates/astur-config/src/lib.rs`; then run `python tools/gen_schema.py` so
  the settings editor shows it.
- Design or tradeoff worth remembering -> a comment next to the code that
  makes the choice, not a separate document.
- New thread, ownership rule, or hot path -> a line in `AGENTS.md`.
- Win32 call that is slow, buggy, or misleading -> comment it where it is
  used, with the measurement or the reason.

Honest docs are a project goal (see `AGENTS.md` "bar to hold" #5).

## What Astur is

Fast, free, portable tiling window manager for Windows 10/11. Single Rust `.exe`,
no installer, no required config. Alt-drag move, nearest-corner resize, dwindle/
master tiling, ≤20 workspaces, per-monitor status bar, composited workspace +
window animations. The main key (`main_key`) is the modifier: Right Alt by default,
reserved (apps never see it); Left Alt (also reserved), Win / Alt / Ctrl+Win
(passed through, masked) or Caps Lock (reserved) are options.

## The bar to hold (don't regress these)

1. **Never break window management.** Animations/bar are cosmetics layered *over*
   a switch/tile that already happened instantly and correctly. A dropped or
   failed animation must never lose or misplace a window.
2. **Hooks are sacred.** `mouse_proc`/`keyboard_proc` are on the OS-wide input
   path. No locks without an atomic guard, no allocation, no `SetWindowPos`. Push
   a `Cmd` and let the manager/worker do the work. Measure before/after.
3. **Smooth is the headline.** Beat komorebi/GlazeWM/Seelen on motion polish.
   Silky over feature-count.
4. **Tile placement is INSTANT.** `animate_to` is a historical name — leave it
   instant. Real glide goes through the snapshot overlay, never per-frame
   real-window `SetWindowPos` (tried, removed).
5. Keep `astur-config` (+ `layout.rs`) Win32-free / Win32-light — the trivially
   testable parts. `astur-config` is its own crate now and has zero Win32.

## Code layout (Cargo workspace, v2)

The repo is a Cargo workspace. Astur Lite = the frozen `v1.0.0` git tag (single exe,
pre-workspace); the workspace below is the evolving full "Astur" (v2).

- `crates/astur/src/main.rs` — everything Win32: hooks, manager loop, compositors,
  bar, launcher, system menu, file search. The binary users run. It is one file
  because we prefer it that way, not for build speed: splitting a crate into
  modules does not change Rust build time (the crate is still one compilation
  unit, and `codegen-units = 1` in release makes that literal). If it ever gets
  split, say so honestly — don't reuse the old rationale.
- `crates/astur/src/layout.rs` — pure geometry (`dwindle_layout`, `master_stack`).
  Uses the `RECT` type only; no Win32 calls.
- `crates/astur-config/src/lib.rs` — pure parsing → `Config`. **No Win32.** Shared by
  the WM and the settings GUI so they never drift; aliased as `config` in the WM.
- `tools/astur_settings.py` — the settings editor: one file, Python 3 + tkinter,
  no third-party packages. It renders `ConfFile` fields from `SCHEMA_DATA`, which
  `tools/gen_schema.py` generates out of the two config templates in
  `crates/astur-config/src/lib.rs` (`DEFAULT_CONFIG`, `DEFAULT_NAVBAR`) — rerun
  the generator after adding or changing a key, or the editor will not show it.
  Saving keeps the file's comments and line order and leaves a `.bak`. The WM
  starts it through `settings_python` / `python` (see `tray_open_settings`).


## Build / verify

Default toolchain is MSVC. If the MSVC linker isn't reachable in the shell
(no `link.exe` / no `vcvars`), build with the installed self-contained GNU
toolchain to verify compilation (from the workspace root builds all crates; add
`-p astur` for just the WM):

```
cargo +stable-x86_64-pc-windows-gnu build --target x86_64-pc-windows-gnu
```

If crate downloads fail with a cert-revocation error
(`CRYPT_E_NO_REVOCATION_CHECK`), prefix with `CARGO_HTTP_CHECK_REVOKE=false`.
Note: Git Bash's MSYS `link` shadows MSVC `link.exe` — don't build MSVC from Bash.

## Style

Caveman mode is on globally (terse, drop articles/filler). Code, commits, and
PRs are written normal. No emojis in code. Start answers with a clear judgment,
then the why; flag every real flaw.
