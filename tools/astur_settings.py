#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Astur settings editor -- one file, tkinter only.

Edits the two files Astur reads:

    %USERPROFILE%\\.astur\\astur.conf     window manager
    %USERPROFILE%\\.astur\\navbar.conf    status bar

Both are plain `key = value` text with the explanation in the comments.
Astur watches them, so saving is enough; no restart, no IPC.

Every write is line level: only the keys you changed are rewritten, and the
comments, order and blank lines of the rest of the file stay as they are.
Saves are atomic (temp file + os.replace) with a .bak of the previous text,
so Astur can never read a half written file.

The form is generated from SCHEMA_DATA (see tools/gen_schema.py in the Astur
tree): one tuple per key -- name, kind, default, extra, help. Adding a key is
one line there, not one more widget here.

Usage:
    pythonw astur_settings.py [--astur PATH] [--navbar PATH]
    python  astur_settings.py --selftest      # read -> write -> byte compare

Only the standard library is used (tkinter + ctypes).
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import sys
import tempfile
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk

# --------------------------------------------------------------------------
# Appearance
# --------------------------------------------------------------------------

BG = "#1e1f24"          # window background
PANEL = "#26272e"       # cards, sidebar
FIELD = "#2f3039"       # entry background
BORDER = "#3a3b45"
FG = "#d7d8dc"          # normal text
DIM = "#8b8d96"         # help text
ACCENT = "#5b9dd9"      # selection, focus
OK = "#6fbf73"
WARN = "#d9a13b"
ERR = "#e0716b"
FLASH = "#3d5a7a"       # the row highlight after a search jump

FONT = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI Semibold", 9)
FONT_TITLE = ("Segoe UI Semibold", 12)
FONT_MONO = ("Consolas", 9)

DOCS = ("astur", "navbar")
DOC_TITLES = {"astur": "astur.conf", "navbar": "navbar.conf"}

# Widget names the bar knows, for the zone list fields.
BAR_WIDGETS = (
    "workspaces apps keyboard title layout cpu mem net volume battery disk "
    "date clock media uptime custom logo separator spacer"
).split()

KEY_NAMES = (
    "Space Tab Enter Backspace Esc Left Up Right Down Home End PgUp PgDn "
    "Insert Delete [ ] ` - = ; ' , . / \\"
).split()


# --------------------------------------------------------------------------
# Open windows, for the window-rule picker
# --------------------------------------------------------------------------

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _win_text(hwnd: int, fn) -> str:
    buf = ctypes.create_unicode_buffer(512)
    fn(hwnd, buf, 512)
    return buf.value


def list_windows() -> list[tuple[str, str, str]]:
    """(title, class, exe name) of every visible top level window with a title."""
    found: list[tuple[str, str, str]] = []

    def visit(hwnd, _param):
        if not _user32.IsWindowVisible(hwnd):
            return True
        title = _win_text(hwnd, _user32.GetWindowTextW)
        if not title.strip():
            return True
        klass = _win_text(hwnd, _user32.GetClassNameW)
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = ""
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                       False, pid.value)
        if handle:
            try:
                size = wintypes.DWORD(1024)
                buf = ctypes.create_unicode_buffer(size.value)
                if _kernel32.QueryFullProcessImageNameW(handle, 0, buf,
                                                        ctypes.byref(size)):
                    exe = os.path.basename(buf.value)
            finally:
                _kernel32.CloseHandle(handle)
        found.append((title, klass, exe))
        return True

    _user32.EnumWindows(_ENUM_PROC(visit), 0)
    found.sort(key=lambda r: (r[2].lower(), r[0].lower()))
    return found


# --------------------------------------------------------------------------
# Where the files are
# --------------------------------------------------------------------------

def default_path(doc: str) -> Path:
    """The same lookup Astur uses: an environment override, else ~/.astur."""
    env = os.environ.get("ASTUR_CONFIG" if doc == "astur" else "ASTUR_NAVBAR")
    if env:
        return Path(env).expanduser()
    name = "astur.conf" if doc == "astur" else "navbar.conf"
    return Path.home() / ".astur" / name


# --------------------------------------------------------------------------
# One config file
# --------------------------------------------------------------------------

_KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_.-]+)(\s*)=(\s*)(.*)$")


class ConfFile:
    """A `key = value` file that remembers its exact text.

    `lines` keeps every line with its original ending, so a rewrite that
    changes nothing reproduces the file byte for byte (see --selftest).
    """

    def __init__(self, doc: str, path: Path) -> None:
        self.doc = doc
        self.path = path
        self.lines: list[str] = []
        self.text = ""
        self.mtime_ns = 0

    # -- reading ------------------------------------------------------
    def load(self) -> None:
        self.text = self.path.read_text(encoding="utf-8")
        self.lines = self.text.splitlines(keepends=True)
        self.mtime_ns = self.path.stat().st_mtime_ns

    def changed_on_disk(self) -> bool:
        try:
            return self.path.stat().st_mtime_ns != self.mtime_ns
        except OSError:
            return True

    def get(self, key: str) -> str | None:
        """The value as written, or None when the key is not in the file."""
        for line in self.lines:
            m = _KEY_RE.match(line.rstrip("\r\n"))
            if m and m.group(2) == key:
                return m.group(5).strip()
        return None

    def effective(self, key: str, default: str = "") -> str:
        value = self.get(key)
        return default if value is None else value

    # -- writing ------------------------------------------------------
    def set(self, key: str, value: str) -> bool:
        """Change one key in place. Returns True when the text changed.

        A missing key is appended at the end, which Astur accepts: the files
        are read key by key, not in a fixed order.
        """
        for i, line in enumerate(self.lines):
            body = line.rstrip("\r\n")
            m = _KEY_RE.match(body)
            if m and m.group(2) == key:
                if m.group(5).strip() == value:
                    return False
                ending = line[len(body):]
                indent, name, pad, after, _old = m.groups()
                self.lines[i] = f"{indent}{name}{pad}={after}{value}{ending}"
                return True
        ending = "\r\n" if self._uses_crlf() else "\n"
        if self.lines and not self.lines[-1].endswith(("\n", "\r")):
            self.lines[-1] += ending
        self.lines.append(f"{key} = {value}{ending}")
        return True

    def _uses_crlf(self) -> bool:
        return "\r\n" in "".join(self.lines[:200])

    def render(self) -> str:
        return "".join(self.lines)

    def save(self) -> bool:
        """Write atomically, keeping one .bak of the previous text."""
        new = self.render()
        if new == self.text:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                self.path.with_suffix(self.path.suffix + ".bak").write_text(
                    self.text, encoding="utf-8", newline="")
            except OSError:
                pass
        fd, tmp = tempfile.mkstemp(prefix=".astur-", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self.text = new
        self.lines = new.splitlines(keepends=True)
        self.mtime_ns = self.path.stat().st_mtime_ns
        return True


# --------------------------------------------------------------------------
# Schema: one entry per key, generated by tools/gen_schema.py from the
# Rust templates (DEFAULT_CONFIG / DEFAULT_NAVBAR in astur-config/src/lib.rs).
# Do not edit by hand: change the comment or the value in lib.rs and re-run
#     python tools/gen_schema.py
# --------------------------------------------------------------------------

# @@SCHEMA-BEGIN@@
SCHEMA_DATA = {
    "astur": [
        ("Workspaces & layout", [
            ("workspace_mode", "enum", "shared", "shared|per_monitor", "How workspaces map to monitors. shared = workspaces are numbered globally, starting from your MAIN (primary) monitor and rotating outward. With 3 monitors, ws1 = main monitor, ws2 = next, ws3 = next, ws4 = main (its 2nd workspace), and s..."),
            ("workspaces", "number", "10", "1..20", "Number of workspaces. int 1 - 20 shared mode = TOTAL across all monitors (distributed from the main monitor outward). per_monitor mode = workspaces per monitor. More keys than 10 are fine (workspace_keys = 1 2 3 4 5 6 7 8 9 0 G). A works..."),
            ("workspace_keys", "key", "1 2 3 4 5 6 7 8 9 0", "", "Keys (with LEFT ALT) that select workspaces 1, 2, 3, ... in order. Add Shift to MOVE the focused window to that workspace instead. Avoid the fixed binds (J K H L M T F W R C [ ], arrows, Enter, Space, Home, End): a fixed bind wins and th..."),
            ("workspace_names", "list", "Web, Code, Chat, Files, Media", "", "Optional display labels. Missing positions fall back to workspace number. list; quote-free names should not contain commas."),
            ("workspace_icons", "text", "", "", "Optional compact pills. Text, symbols from selected font, or icon-font glyphs."),
            ("start_tiled", "bool", "true", "", "Tile windows automatically on launch (Alt+T toggles at runtime). bool"),
            ("layout", "enum", "dwindle", "dwindle|master|columns|grid|monocle|scrolling", "Tiling layout. dwindle = each new window splits the remaining space, spiralling into the bottom corner (spiral default). master = one large master column on the left, the rest stacked on the right. columns = equal-width columns grid = ba..."),
            ("monitor_layouts", "text", "", "", "Per-monitor layout, by monitor number (1 = leftmost, as in window_rules). Empty or 'default' = use layout above. Example: scrolling on monitor 1 and master on monitor 3: monitor_layouts = scrolling, , master"),
            ("workspace_layouts", "text", "", "", "Per-workspace layout, by workspace number (1 = the first). Empty or 'default' = use the workspace's monitor's layout. Example: scrolling on ws1, the monitor layout for ws2, master on ws3: workspace_layouts = scrolling, , master"),
            ("master_ratio", "number", "0.55", "0.10..0.90", "Fraction of the width given to the master window (master layout, and the master split that Alt+H / Alt+L adjust). float 0.10 - 0.90"),
            ("scroll_default_width", "number", "0.5", "0.10..1.00", "Scrolling layout: width of a new column, as a fraction of the screen (0.5 = two columns side by side). float 0.10 - 1.00"),
            ("scroll_width_presets", "list", "0.333, 0.5, 0.667, 1.0", "", "Column widths Alt+R cycles through, smallest to largest. floats 0.10 - 1.00"),
            ("scroll_height_presets", "list", "0.333, 0.5, 0.667", "", "Window heights within a column Alt+Shift+R cycles through, smallest to largest. floats 0.10 - 0.90"),
            ("scroll_center", "enum", "never", "never|always|on-overflow", "When focus moves to a column, the view: never = scrolls only as far as needed to show it fully always = keeps the focused column centred on-overflow = stays put if the column fits, otherwise centres it values: never | always | on-overflow"),
            ("tab_bar_height", "number", "26", "16..64", "Height of the tab bar on a tabbed column (Alt+Shift+T). int 16 - 64"),
        ]),
        ("Gaps", [
            ("outer_gap", "number", "8", "", "Gap in pixels between windows and the screen edge. int (>= 0)"),
            ("inner_gap", "number", "8", "", "Gap in pixels between adjacent windows. int (>= 0)"),
        ]),
        ("Focus & cursor behaviour", [
            ("cursor_follows_focus", "bool", "true", "", "Warp the mouse cursor onto the window that gains focus via Alt+arrows and on workspace switches. bool"),
            ("focus_follows_mouse", "bool", "false", "", "Focus follows mouse: hovering a window with the cursor focuses it, like Focus follows mouse. Off by default (Windows focus-steal is more abrupt than on Linux); set true to enable. bool"),
        ]),
        ("Animations", [
            ("animations", "bool", "true", "", "Enable animations. bool"),
            ("animation_ms", "number", "140", "0..2000", "Animation duration in milliseconds. Lower = snappier, higher = smoother. 0 disables (same as animations = false). Up to 250, clicks and the wheel pass through a running animation to the windows (already in their final place underneath);..."),
            ("workspace_anim", "enum", "slide", "off|slide|fade", "Workspace-switch animation style: off - instant switch, no overlay slide - old slides off one edge, new slides in from the other (default) spring - slide that overshoots the target then settles back (Hyprland-like) fade - old fades out,..."),
            ("workspace_slide", "bool", "true", "", "Back-compat toggle. false forces workspace_anim = off; true leaves it as set. Prefer workspace_anim above. Needs animations = true. bool"),
            ("window_anim", "text", "glide", "", "Window move / open / close / re-tile animation: off - instant placement glide - windows glide to their new slots, moving and resizing together (the live window image is scaled in between, 1:1 at both ends). New layouts or keyboard/mouse..."),
            ("animation_easing", "enum", "cubic", "cubic|smooth|spring", "Motion curve used by popup/placement transitions. values: cubic | smooth | spring"),
        ]),
        ("Appearance: theme, window borders & dimming", [
            ("theme", "enum", "dark", "dark|light|auto", "Colour theme for Astur's own surfaces (launcher, system menu, and any bar colour left at its default — explicit navbar.conf colours always win). dark = dark surfaces (default) light = light surfaces auto = follow the Windows app theme (S..."),
            ("acrylic", "bool", "false", "", "EXPERIMENTAL: acrylic blur behind the launcher and system menu (frosted-glass look). Uses an undocumented Windows API; if popups render oddly, turn it off. bool"),
            ("popup_font_name", "text", "Segoe UI", "", "Popup typography and geometry. See the pixel note at the top of this file."),
            ("popup_font_size", "number", "18", "", ""),
            ("popup_font_weight", "number", "400", "", ""),
            ("popup_radius", "number", "16", "", ""),
            ("popup_border_width", "number", "1", "", ""),
            ("popup_opacity", "number", "94", "", ""),
            ("popup_bg", "colour", "auto", "", "Set colours to auto to follow theme, or explicit #RRGGBB."),
            ("popup_fg", "text", "auto", "", ""),
            ("popup_muted", "text", "auto", "", ""),
            ("popup_accent", "text", "auto", "", ""),
            ("popup_accent_fg", "text", "auto", "", ""),
            ("popup_border", "text", "auto", "", ""),
            ("unfocused_opacity", "number", "0.8", "0.10..1.00", "Dim unfocused windows to this opacity. float 0.10 - 1.00 (1.0 = disabled) Trade-off worth knowing: any value below 1.0 makes Astur add WS_EX_LAYERED to every window it manages, which puts those apps on a different composition path. A few..."),
            ("border_enabled", "bool", "true", "", "Coloured window borders. Requires Windows 11 (no effect on Windows 10). bool"),
            ("focused_border", "colour", "#66AAFF", "", "Border colour of the focused window. colour"),
            ("unfocused_border", "colour", "#223A5E", "", "Border colour of unfocused windows. colour"),
        ]),
        ("Window rules", [
            ("ignore_classes", "text", "", "", "Never tile/manage these (in addition to the built-in shell/tooltip/lock-screen filtering). Example: ignore_classes = TaskManagerWindow, MyOverlayClass"),
            ("float_classes", "text", "", "", "Manage but always float these (let the app place them; don't tile). Example: float_classes = #32770, MsiDialogCloseClass"),
            ("window_rules", "records", "", "action|exe|class|title|workspace|monitor", "Rich rules. Records separated by ;;, fields by |: action|exe|class|title|workspace|monitor Empty match fields are wildcards. workspace/monitor are 1-based; 0/empty = unset. They decide where an app's windows go: ones that open later and..."),
        ]),
        ("Launcher and system menu", [
            ("terminal", "text", "wt.exe", "", "Program launched by Alt+Enter: a cmd.exe command line run through `start`, so PATH and App Execution Aliases (e.g. wt.exe) resolve and arguments work (wt -p Ubuntu). Quote a path with spaces (or whose %VARIABLES% expand to spaces) when a..."),
            ("browser", "text", "", "", "Program launched by Alt+Shift+Enter. Leave EMPTY to open the system default browser. text"),
            ("launcher_enabled", "bool", "true", "", "Alt+Space picker. Placement: cursor_monitor | focused_monitor | primary_monitor"),
            ("launcher_width", "number", "660", "", ""),
            ("launcher_wide_width", "number", "1060", "", ""),
            ("launcher_height", "number", "452", "", ""),
            ("launcher_row_height", "number", "40", "", ""),
            ("launcher_icon_size", "number", "32", "", ""),
            ("launcher_padding", "number", "16", "", ""),
            ("launcher_selection_radius", "number", "12", "", ""),
            ("launcher_placement", "text", "cursor_monitor", "", ""),
            ("launcher_max_results", "number", "40", "", ""),
            ("launcher_mru", "bool", "true", "", ""),
            ("launcher_source_apps", "bool", "true", "", "Providers can be enabled independently."),
            ("launcher_source_files", "bool", "true", "", ""),
            ("launcher_source_calc", "bool", "true", "", ""),
            ("launcher_source_web", "bool", "true", "", ""),
            ("launcher_source_windows", "bool", "false", "", ""),
            ("launcher_source_clipboard", "bool", "false", "", ""),
            ("launcher_source_emoji", "bool", "false", "", ""),
            ("launcher_web_url", "text", "https://www.google.com/search?q={query}", "", ""),
            ("launcher_file_scope", "text", "", "", "Empty file scope uses current user profile. Excludes are comma-separated path fragments."),
            ("launcher_file_exclude", "list", ".git, node_modules, target", "", ""),
            ("launcher_entries", "records", "", "label|target|icon", "Custom records: label|target|icon ;; label|target|icon. icon: auto/path/builtin name."),
            ("system_menu_enabled", "bool", "true", "", "The system (power) menu: lock, sleep, restart and Astur's own actions. key_system_menu below binds it like the other hotkeys (Alt+. by default)."),
            ("system_menu_width", "number", "380", "", ""),
            ("system_power_items", "list", "lock, sleep, hibernate, sign_out, restart, shutdown", "", "Built-ins: lock sleep hibernate sign_out restart shutdown settings open_config reload restart_astur exit_astur screenshot wallpapers. Order controls menu order."),
            ("system_setup_items", "list", "settings, open_config, reload, restart_astur, exit_astur, screenshot, wallpapers", "", ""),
            ("system_actions", "records", "", "category|label|command", "Custom: category|label|target|icon|confirm, records separated by ;;"),
        ]),
        ("Optional desktop features", [
            ("alt_tab_replacement", "bool", "false", "", ""),
            ("scratchpad_enabled", "bool", "false", "", ""),
            ("scratchpad_command", "text", "wt.exe", "", ""),
            ("scratchpad_class", "text", "CASCADIA_HOSTING_WINDOW_CLASS", "", ""),
            ("clipboard_history", "bool", "false", "", ""),
            ("clipboard_limit", "number", "50", "", ""),
            ("clipboard_prefix", "text", ">", "", ""),
            ("emoji_picker", "bool", "false", "", ""),
            ("emoji_prefix", "text", ":", "", ""),
            ("wallpaper_dir", "text", "", "", ""),
            ("workspace_wallpapers", "text", "", "", "One wallpaper path per workspace, separated by ;;. Empty positions do nothing."),
            ("media_enabled", "bool", "false", "", ""),
            ("persist_state", "bool", "true", "", ""),
            ("log_level", "text", "error", "", "Diagnostics log at %USERPROFILE%\\.astur\\astur.log (rotates at 1 MB). off = write nothing error = failures only (default) info = + startup environment, monitors/DPI, hook re-arms, config reloads debug = + per-command detail and latency pr..."),
            ("ipc_enabled", "bool", "false", "", "Local named-pipe command API. Pipe name only; no remote/network listener. The pipe is restricted to your own user account and rejects remote clients."),
            ("ipc_pipe", "text", "astur", "", ""),
            ("ipc_allow_launch", "bool", "false", "", "Allow `launch <command>` over IPC to run arbitrary commands. Window-management verbs (switch/move/focus/layout/...) work regardless. Leave this off unless you actually script launching through Astur: on, any process running as you can us..."),
            ("yasb_enabled", "bool", "false", "", "YASB workspace integration. Uses YASB's existing GlazeWM workspace widget. WebSocket server on 127.0.0.1 only; independent of the named-pipe API above. Local processes can read workspace/window handles and switch workspaces. Browser orig..."),
            ("yasb_port", "number", "6123", "", ""),
            ("foreground_lock_disable", "bool", "true", "", "Windows normally refuses to let a background app steal the foreground. Astur disables that timeout so focus changes land reliably. It is a SYSTEM-WIDE setting affecting every application, not just Astur; the previous value is put back wh..."),
            ("async_window_pos", "bool", "true", "", "Place windows without waiting for each app to finish moving (posted SetWindowPos). A re-tile then completes after the slowest app instead of after every app in turn, and a busy app no longer delays the next command that only moves window..."),
            ("extra_hotkeys", "records", "ALT+GRAVE|scratchpad|", "chord|action|argument", "Extra bindings: chord|action|argument ;; chord|action|argument A chord is keys joined by +: MOD (the main key, see main_key below), CTRL, SHIFT, ALT, WIN and one key name. It needs MOD, ALT or WIN. With main_key = lalt, ALT is Left Alt,..."),
            ("main_key", "key", "lalt", "", "============================================================================ Hotkeys (the main key, Left Alt unless main_key says otherwise) ============================================================================ The main key is hel..."),
            ("key_focus_next", "key", "J", "", "Alt + left-drag move window under cursor (drops back into the tiling) Alt + right-drag resize nearest corner (red bracket marker) Alt+T toggle tiling on/off (floating mode; workspaces kept) Alt+J / Alt+K focus next / previous window in t..."),
            ("key_focus_prev", "text", "K", "", ""),
            ("key_shrink_master", "text", "H", "", ""),
            ("key_grow_master", "text", "L", "", ""),
            ("key_promote_master", "text", "M", "", ""),
            ("key_toggle_tiling", "text", "T", "", ""),
            ("key_toggle_float", "text", "F", "", ""),
            ("key_close_window", "text", "W", "", ""),
            ("key_cycle_width", "text", "R", "", ""),
            ("key_center_column", "text", "C", "", ""),
            ("key_consume_left", "text", "[", "", ""),
            ("key_consume_right", "text", "]", "", ""),
            ("key_fill_desktop", "text", "E", "", ""),
            ("key_system_menu", "text", "'", "", ""),
            ("key_switch_ws_1", "list", ",", "", "Alt+, / Alt+. / Alt+/ go to the 1st / 2nd / 3rd workspace of the focused monitor, in that monitor's own order (a screen holding 2, 4, 6, 8 goes to 2, 4, 6)."),
            ("key_switch_ws_2", "text", ".", "", ""),
            ("key_switch_ws_3", "text", "/", "", ""),
        ]),
    ],
    "navbar": [
        ("General", [
            ("enabled", "bool", "true", "", "Show the bars. bool (set false to disable entirely)"),
            ("height", "number", "28", "0..200", "Bar thickness in pixels. int 0 - 200 (0 also disables it)"),
            ("bottom", "bool", "false", "", "Dock the bars at the bottom of each screen instead of the top. bool"),
            ("padding", "number", "8", "0..200", "Horizontal padding from each bar edge, in px. int 0 - 200"),
            ("font_name", "text", "Segoe UI", "", "Font family for all bar text. text (e.g. Segoe UI, Cascadia Code, Consolas)"),
            ("font_size", "number", "0", "0..100", "Text height in px. 0 = auto (about half the bar height). int 0 - 100"),
            ("font_weight", "number", "600", "100..900", "Text weight: 400 = regular, 600 = semi-bold, 700 = bold. int 100 - 900"),
        ]),
        ("Style", [
            ("shape", "enum", "", "|strip|islands|pills", "Bar shape: strip full-width bar along the screen edge (the default) floating detached from the edges by `margin`, with rounded corners islands a strip with a rounded island behind each zone pills a strip with a rounded pill behind each w..."),
            ("floating", "bool", "false", "", "Floating bar: detached from the screen edge with a margin and rounded corners (waybar/Hyprland style). false = classic full-width strip. Ignored while a `shape` line is set. bool"),
            ("margin", "number", "8", "0..200", "Gap between a floating bar and the screen edges, in px. int 0 - 200"),
            ("radius", "number", "12", "0..40", "Corner radius of a floating bar, an island or a pill, in px. At least half the height draws a full capsule. int 0 - 40"),
            ("island_padding", "number", "10", "0..50", "Space between an island's or a pill's edge and its content, in px. int 0 - 50"),
            ("border_width", "number", "0", "0..10", "Outline width in px, 0 = none: around a floating bar, each island or each pill; a strip gets a line along its inner edge. Colour: `border`. int 0 - 10"),
            ("workspace_style", "enum", "box", "box|pill|underline|dot", "How the active workspace is marked: box accent block behind its number (the default) pill rounded accent pill behind its number underline short accent line under its number dot a dot per workspace instead of numbers (dim = empty), the ac..."),
            ("widget_colors", "colors", "", "widget:colour", "Pills shape only: a colour per widget's pill, as widget:colour pairs. A colour is a palette swatch (red orange yellow green teal blue purple pink; switching palette or theme recolours it), surface, or #RRGGBB. Text on a coloured pill is..."),
            ("separator_style", "enum", "line", "line|dot|powerline", "What the separator widget draws: line a thin line (the default) dot a small dot powerline a small arrow; with shape = pills the pills join edge to edge into square segments with arrow ends"),
            ("hover", "bool", "false", "", "Highlight the clickable item under the mouse pointer. bool"),
            ("title_bold", "bool", "false", "", "Draw the window title in bold. bool"),
            ("autohide", "bool", "false", "", "Auto-hide: the bar slides away and stops reserving screen space; move the mouse to the bar's screen edge to reveal it. bool"),
            ("left", "list", "workspaces apps", "widget", "--------------------------------------------------------------------------- Layout: three zones. List widget names per zone (space separated, drawn in order). Available widgets: workspaces the workspace pills (click to switch) apps app b..."),
            ("center", "list", "title", "widget", ""),
            ("right", "list", "layout cpu mem net volume battery date clock", "widget", ""),
        ]),
        ("Behaviour", [
            ("wheel_workspaces", "bool", "true", "", "Mouse wheel over the bar switches to the previous/next workspace, one per full wheel notch (a touchpad or smooth-scrolling wheel must scroll a whole notch's worth), and a fast spin lands straight on its last workspace. The wheel over the..."),
            ("hide_empty_workspaces", "bool", "false", "", "Hide empty workspace pills, showing only the active one and those with windows. false = show every workspace the monitor owns. bool"),
            ("monitors", "text", "all", "", "Which screens get a bar: all, primary (the main screen only), or screen numbers counted from the left, e.g. 1 3. A screen without a bar keeps its whole height for windows."),
        ]),
        ("Workspace marks", [
            ("workspace_label", "enum", "auto", "auto|number|name|icon|icon_name", "What each workspace mark shows (names and icons are workspace_names and workspace_icons in astur.conf): auto its icon, else its name, else its number (the default) number always the number name the name (the number when it has none) icon..."),
            ("workspace_apps", "key", "0", "", "How many app icons each workspace mark shows for the apps open there (not with workspace_style = dot): 0 hides them, 5 shows up to 5. true and false still work (3 and 0), the way this key started. number, 0 to 8"),
        ]),
        ("Widget toggles", [
            ("show_title", "bool", "true", "", "Show the focused window title. bool"),
            ("show_layout", "bool", "true", "", "Show the layout name + tiling/floating state. bool"),
            ("show_clock", "bool", "true", "", "Show the clock. bool"),
            ("clock_24h", "bool", "true", "", "24-hour clock when clock_format is empty; false = 12-hour with am/pm. bool"),
            ("show_date", "bool", "false", "", "Show the date. bool"),
            ("date_format", "text", "ddd dd MMM", "", "Date format tokens: yyyy yy MMMM (June) MMM (Jun) MM dddd (Friday) ddd (Fri) dd d (day without a leading zero, when no letter touches it) (e.g. \"ddd dd MMM\" -> Fri 19 Jun, \"dddd d MMMM\" -> Friday 19 June)"),
            ("show_cpu", "bool", "true", "", "Live system stats. Updated every ~2s. bool"),
            ("show_mem", "bool", "true", "", ""),
            ("show_battery", "bool", "true", "", ""),
            ("show_net", "bool", "false", "", "Network down/up speed (updated every ~2s). bool"),
            ("show_volume", "bool", "true", "", "Speaker volume %. Wheel over it adjusts; click toggles mute. bool"),
            ("show_apps", "bool", "false", "", "App buttons: an icon per window on the active workspace; click focuses. bool"),
            ("show_media", "bool", "false", "", "Current media title. Requires media_enabled in astur.conf."),
        ]),
        ("Spacing, labels and icons", [
            ("widget_gap", "number", "16", "", ""),
            ("icon_size", "number", "20", "", ""),
            ("workspace_width", "number", "34", "", ""),
            ("icon_mode", "enum", "both", "icon|text|both|glyph|glyph_only", "How cpu / mem / net / volume / battery show: icon label only text value only both label + value glyph a Windows icon + value: Segoe Fluent Icons (Windows 11), else Segoe MDL2 Assets. Battery shows its level (and charging), volume its lev..."),
            ("show_tooltips", "bool", "true", "", ""),
            ("show_app_labels", "bool", "false", "", ""),
            ("cpu_format", "text", "{value}%", "", ""),
            ("mem_format", "text", "{value}%", "", ""),
            ("battery_format", "text", "{value}%", "", ""),
            ("net_format", "text", "D:{down} U:{up}", "", ""),
            ("volume_format", "text", "{value}%", "", ""),
            ("clock_format", "text", "HH:mm", "", "Clock tokens: HH H (24-hour) hh h (12-hour) mm ss (seconds: the bar then repaints every second) tt (am/pm) TT (AM/PM). Empty = clock_24h decides between HH:mm and h:mm tt."),
            ("icon_cpu", "text", "CPU", "", "Labels for icon / both. Plain text works everywhere; your own icon-font glyphs work when font_name has them."),
            ("icon_mem", "text", "RAM", "", ""),
            ("icon_battery", "text", "BAT", "", ""),
            ("icon_net", "text", "NET", "", ""),
            ("icon_volume", "text", "VOL", "", ""),
            ("icon_disk", "text", "DISK", "", ""),
        ]),
        ("More widgets (listed in a zone = shown)", [
            ("title_format", "text", "{title}", "", "Title text. Tokens: {title} (the window's title), {app} (the app's name, e.g. Microsoft Edge)."),
            ("keyboard_format", "text", "{lang}", "", "Keyboard language. Tokens: {lang} (ENG, DEU, ...) {region} (US, GB, ...)."),
            ("disk_drive", "text", "C:", "", "The drive (or folder) the disk widget measures, checked every 30 s: C, C: or a folder path."),
            ("disk_format", "text", "{free}", "", "Disk tokens: {free} {used} {total} {value} (percent used)."),
            ("uptime_format", "text", "{value}", "", "Uptime token: {value} (42m, 5h 12m, 3d 4h)."),
            ("custom_command", "text", "", "", "custom: a command run hidden (as cmd /C) every custom_interval seconds (1 - 3600); its first output line is {output}. Stopped after 5 s. Empty = custom_format alone, as plain text."),
            ("custom_format", "text", "{output}", "", ""),
            ("custom_interval", "number", "10", "", ""),
            ("palette", "colour", "classic", "", "Colour palette the 'auto' colours come from: classic (the default), catppuccin, nord, gruvbox, rosepine, mono, or system (Windows neutrals and your Windows accent colour, read at start and on reload). Each has a dark and a light variant;..."),
            ("bg", "colour", "auto", "", "Colours: 'auto' follows the palette and theme, or set an explicit #RRGGBB to override that colour permanently."),
            ("fg", "text", "auto", "", ""),
            ("accent", "text", "auto", "", "Active-workspace pill highlight."),
            ("inactive", "text", "auto", "", "Empty workspaces / layout / stats text."),
            ("accent_fg", "colour", "auto", "", "Text on the accent highlight. auto = the palette's, or bg while bg is set."),
            ("surface", "text", "auto", "", "Island and pill fill."),
            ("border", "colour", "auto", "", "Outline colour (see border_width). auto = the inactive colour."),
        ]),
    ],
}
# @@SCHEMA-END@@


class Field:
    """One setting: what to call it, how to edit it, what it means."""

    __slots__ = ("doc", "section", "key", "kind", "default", "extra", "help",
                 "label", "choices", "spec", "lo", "hi")

    def __init__(self, doc: str, section: str, key: str, kind: str,
                 default: str, extra: str, help_: str) -> None:
        self.doc = doc
        self.section = section
        self.key = key
        self.kind = kind
        self.default = default
        self.extra = extra
        self.help = help_
        self.choices: list[str] = []
        self.spec: list[str] = []
        self.lo = self.hi = None
        if kind == "enum":
            self.choices = [c for c in extra.split("|")]
        elif kind == "records":
            self.spec = re.split(r"[|:]", extra) if extra else []
        elif kind == "colors":
            # `widget:colour` pairs, space separated (widget_colors).
            self.spec = ["widget", "colour"]
        elif kind == "number" and ".." in extra:
            a, b = extra.split("..", 1)
            try:
                self.lo, self.hi = float(a), float(b)
            except ValueError:
                self.lo = self.hi = None
        self.label = pretty_label(key)

    def normalise(self, raw: str) -> str:
        """Turn what the widget holds into the text the file should get."""
        raw = raw.strip()
        if self.kind == "bool":
            return "true" if raw.lower() in ("1", "true", "yes", "on") else "false"
        if self.kind == "number" and raw:
            try:
                n = float(raw)
            except ValueError:
                return self.default
            if self.lo is not None and n < self.lo:
                n = self.lo
            if self.hi is not None and n > self.hi:
                n = self.hi
            return str(int(n)) if n == int(n) and "." not in self.default else f"{n:g}"
        if self.kind == "colour":
            return raw if re.fullmatch(r"#[0-9A-Fa-f]{6}", raw) else self.default
        return raw


def pretty_label(key: str) -> str:
    name = key[4:] + " key" if key.startswith("key_") else key
    if name.startswith("bar_"):
        name = name[4:]
    return name.replace("_", " ").strip().capitalize()


def build_fields() -> dict[str, list[tuple[str, list[Field]]]]:
    out: dict[str, list[tuple[str, list[Field]]]] = {}
    for doc in DOCS:
        sections = []
        for title, rows in SCHEMA_DATA[doc]:
            sections.append((title, [Field(doc, title, *row) for row in rows]))
        out[doc] = sections
    # Two keys have their own widgets: they pick from the layout list, so they
    # need that list and a kind the form renderer knows.
    layouts = next((f.choices for f in out["astur"][0][1] if f.key == "layout"), [])
    for secs in out.values():
        for _title, fields in secs:
            for field in fields:
                if field.key == "workspace_layouts":
                    field.kind, field.choices = "ws_layouts", layouts
                elif field.key == "monitor_layouts":
                    field.kind, field.choices = "mon_layouts", layouts
    return out


FIELDS = build_fields()
BY_KEY = {(f.doc, f.key): f for secs in FIELDS.values() for _, fs in secs for f in fs}
LAYOUTS = [c for c in next(f.choices for f in FIELDS["astur"][0][1]
                           if f.key == "layout")]


# --------------------------------------------------------------------------
# Small widgets
# --------------------------------------------------------------------------

def style_init(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                    bordercolor=BORDER, lightcolor=PANEL, darkcolor=PANEL,
                    troughcolor=PANEL, focuscolor=ACCENT)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Panel.TLabel", background=PANEL, foreground=FG)
    style.configure("Dim.TLabel", background=BG, foreground=DIM)
    style.configure("Title.TLabel", background=BG, foreground=FG, font=FONT_TITLE)
    style.configure("Key.TLabel", background=BG, foreground=FG, font=FONT_BOLD)
    style.configure("TButton", background=FIELD, foreground=FG, borderwidth=1,
                    focusthickness=0, padding=(8, 3))
    style.map("TButton", background=[("active", BORDER)], foreground=[("disabled", DIM)])
    style.configure("Accent.TButton", background=ACCENT, foreground="#101216",
                    font=FONT_BOLD)
    style.map("Accent.TButton", background=[("active", "#6fb0e8")])
    style.configure("TEntry", fieldbackground=FIELD, foreground=FG,
                    insertcolor=FG, borderwidth=1, padding=3)
    style.map("TEntry", fieldbackground=[("readonly", PANEL)])
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD,
                    foreground=FG, arrowcolor=FG, borderwidth=1, padding=3)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)],
              foreground=[("readonly", FG)])
    style.configure("TCheckbutton", background=BG, foreground=FG,
                    indicatorbackground=FIELD, indicatorforeground=FG)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                    foreground=FG, borderwidth=0, rowheight=24)
    style.map("Treeview", background=[("selected", ACCENT)],
              foreground=[("selected", "#101216")])
    style.configure("Treeview.Heading", background=PANEL, foreground=DIM,
                    relief="flat", font=FONT)
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#101216")


def scrollable(parent: tk.Widget) -> tuple[tk.Canvas, tk.Frame]:
    canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
    bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    inner = tk.Frame(canvas, bg=BG)
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>",
                lambda e: canvas.itemconfigure(window, width=e.width))
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        canvas.bind_all(seq, lambda e: _wheel(canvas, e), add="+")
    return canvas, inner


def _wheel(canvas: tk.Canvas, event: tk.Event) -> None:
    if str(event.widget).startswith(str(canvas)) or _inside(event.widget, canvas):
        delta = event.delta or 0
        step = -1 if (delta > 0 or event.num == 4) else 1
        canvas.yview_scroll(step, "units")


def _inside(widget: tk.Widget, parent: tk.Widget) -> bool:
    while widget is not None:
        if widget is parent:
            return True
        widget = getattr(widget, "master", None)
    return False


class ColorField(tk.Frame):
    """Entry + swatch; the swatch opens the picker, the text takes #RRGGBB."""

    def __init__(self, parent: tk.Widget, value: str, on_change) -> None:
        super().__init__(parent, bg=BG)
        self.on_change = on_change
        self.var = tk.StringVar(value=value)
        self.entry = ttk.Entry(self, textvariable=self.var, width=11)
        self.entry.pack(side="left")
        self.swatch = tk.Button(self, width=3, bg=value or PANEL, relief="flat",
                                highlightthickness=1, highlightbackground=BORDER,
                                command=self.pick)
        self.swatch.pack(side="left", padx=(6, 0), ipady=1)
        self.var.trace_add("write", lambda *_: self.sync())
        self.sync()

    def sync(self) -> None:
        value = self.var.get().strip()
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            self.swatch.configure(bg=value)
        self.on_change(value)

    def pick(self) -> None:
        _rgb, value = colorchooser.askcolor(color=self.var.get() or "#000000",
                                            parent=self, title="Colour")
        if value:
            self.var.set(value.upper())


class WindowPicker(tk.Toplevel):
    """Pick one of the open windows; hands (title, class, exe) to the caller."""

    def __init__(self, parent: tk.Widget, on_pick) -> None:
        super().__init__(parent)
        self.title("Pick a window")
        self.configure(bg=BG)
        self.transient(parent.winfo_toplevel())
        self.on_pick = on_pick
        self.geometry("820x430")

        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x")
        tk.Label(head, text="Open windows", bg=PANEL, fg=FG, font=FONT_BOLD,
                 padx=10, pady=6).pack(side="left")
        tk.Label(head, text="Double-click a row to use it.",
                 bg=PANEL, fg=DIM, padx=6).pack(side="left")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        self.tree = ttk.Treeview(body, columns=("title", "class", "exe"),
                                 show="headings", selectmode="browse")
        for col, width in (("title", 380), ("class", 190), ("exe", 200)):
            self.tree.heading(col, text=col.capitalize())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self.use())
        for row in list_windows():
            self.tree.insert("", "end", values=row)
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0])

        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Use", style="Accent.TButton",
                   command=self.use).pack(side="right", padx=(0, 6))

    def use(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], "values")
        self.on_pick(*values)
        self.destroy()


class RecordsDialog(tk.Toplevel):
    """Table editor for the `a|b|c ;; a|b|c` keys (window rules, hotkeys...).

    `rec_sep=None` is for the other shape, the space separated `name:value`
    pairs of `widget_colors` (a comma or a space splits pairs, never a colon).
    """

    def __init__(self, parent: tk.Widget, title: str, spec: list[str],
                 value: str, on_ok, rec_sep: str | None = ";;",
                 is_colors: bool = False) -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG)
        self.transient(parent.winfo_toplevel())
        self.on_ok = on_ok
        self.rec_sep = rec_sep
        self.is_colors = is_colors
        self.spec = spec or ["value"]
        self.rows = self._parse(value)
        self.current: int | None = None
        w = 120 + 130 * min(3, len(self.spec))
        self.geometry(f"{min(max(w, 560 if is_colors else w), 900)}x470")

        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x")
        tk.Label(head, text=title, bg=PANEL, fg=FG, font=FONT_BOLD,
                 padx=10, pady=6).pack(side="left")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=8)

        self.tree = ttk.Treeview(body, columns=self.spec, show="headings",
                                 selectmode="browse")
        for col in self.spec:
            self.tree.heading(col, text=col.capitalize())
            self.tree.column(col, width=max(90, 620 // len(self.spec)), anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.select_row())

        edit = tk.Frame(self, bg=BG)
        edit.pack(fill="x", padx=10)
        self.vars: list[tk.StringVar] = []
        per_row = 3
        for c in range(min(per_row, len(self.spec))):
            edit.grid_columnconfigure(c, weight=1, uniform="field")
        for i, col in enumerate(self.spec):
            cell = tk.Frame(edit, bg=BG)
            cell.grid(row=i // per_row, column=i % per_row, sticky="ew",
                      padx=(0, 6), pady=(0, 4))
            tk.Label(cell, text=col.capitalize(), bg=BG, fg=DIM,
                     font=FONT).pack(anchor="w")
            line = tk.Frame(cell, bg=BG)
            line.pack(fill="x")
            var = tk.StringVar()
            ttk.Entry(line, textvariable=var).pack(side="left", fill="x",
                                                   expand=True)
            ttk.Button(line, text="×", width=2,
                       command=lambda i=i: self.vars[i].set("")
                       ).pack(side="left", padx=(2, 0))
            if self.is_colors and i == 1:
                self.swatch = tk.Label(line, width=2, bg=FIELD, bd=0)
                self.swatch.pack(side="left", padx=(4, 0))
                ttk.Button(line, text="…", width=2,
                           command=self.pick_colour).pack(side="left", padx=(2, 0))
                var.trace_add("write",
                              lambda *_a: self.update_swatch(self.vars[1].get()))
            var.trace_add("write", lambda *_a, i=i: self.apply_form(i))
            self.vars.append(var)

        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", padx=10, pady=(6, 10))
        actions = tk.Frame(buttons, bg=BG)
        actions.pack(fill="x")
        for text, cmd in (("Add", self.add), ("Remove", self.remove),
                          ("Clear row", self.clear_row),
                          ("Up", lambda: self.move(-1)), ("Down", lambda: self.move(1))):
            ttk.Button(actions, text=text, command=cmd).pack(side="left", padx=(0, 6))
        if not self.is_colors:
            ttk.Button(actions, text="Pick window…", command=self.pick_window
                       ).pack(side="left", padx=(12, 0))
        confirm = tk.Frame(buttons, bg=BG)
        confirm.pack(fill="x", pady=(6, 0))
        ttk.Button(confirm, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(confirm, text="OK", style="Accent.TButton",
                   command=self.ok).pack(side="right", padx=(0, 6))

        self.refresh()
        if self.rows:
            self.tree.selection_set(self.tree.get_children()[0])
            self.select_row()

    # -- data ---------------------------------------------------------
    def _parse(self, value: str) -> list[list[str]]:
        value = value or ""
        rows: list[list[str]] = []
        if self.rec_sep is None:
            # `cpu: orange` is a common YAML habit; the Rust parser glues such a
            # token back on, so do the same here instead of losing the colour.
            toks: list[str] = []
            for tok in value.replace(",", " ").split():
                if (toks and (toks[-1].endswith(":") or tok.startswith(":"))
                        and toks[-1].count(":") + tok.count(":") == 1):
                    toks[-1] += tok
                else:
                    toks.append(tok)
            for tok in toks:
                name, sep, colour = tok.partition(":")
                row = [name.strip(), colour.strip() if sep else ""]
                rows.append(row + [""] * (len(self.spec) - len(row)))
            return rows
        for record in value.split(self.rec_sep):
            record = record.strip()
            if not record:
                continue
            parts = [p.strip() for p in record.split("|" if "|" in record else ":")]
            parts += [""] * (len(self.spec) - len(parts))
            rows.append(parts[:len(self.spec)])
        return rows

    def render_value(self) -> str:
        if self.rec_sep is None:
            pairs = [f"{row[0].strip()}:{row[1].strip()}"
                     for row in self.rows if row[0].strip()]
            return " ".join(pairs)
        sep = "|" if "|" in "".join(self.spec) or len(self.spec) > 1 else ":"
        out = []
        for row in self.rows:
            if any(c.strip() for c in row):
                out.append(sep.join(c.strip() for c in row))
        return " ;; ".join(out)

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            self.tree.insert("", "end", values=row)
        self.current = None

    def select_row(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        self.current = idx
        for var, cell in zip(self.vars, self.rows[idx]):
            var.set(cell)

    def apply_form(self, i: int) -> None:
        if self.current is None or self.current >= len(self.rows):
            return
        self.rows[self.current][i] = self.vars[i].get()
        item = self.tree.get_children()[self.current]
        self.tree.item(item, values=self.rows[self.current])

    def update_swatch(self, value: str) -> None:
        """Show the colour being typed: #RRGGBB, a Tk colour name or a swatch."""
        swatch = getattr(self, "swatch", None)
        if swatch is None:
            return
        colour = FIELD
        text = value.strip()
        if text:
            try:
                r, g, b = self.winfo_rgb(text)
                colour = "#%02x%02x%02x" % (r >> 8, g >> 8, b >> 8)
            except tk.TclError:
                colour = FIELD
        swatch.configure(bg=colour)

    def pick_colour(self) -> None:
        """Pick the colour of the row being edited (widget_colors)."""
        if len(self.vars) < 2:
            return
        from tkinter import colorchooser
        start = self.vars[1].get().strip()
        if not start.startswith("#"):
            start = "#808080"
        _rgb, hexv = colorchooser.askcolor(color=start, parent=self,
                                           title="Widget colour")
        if hexv:
            self.vars[1].set(hexv.upper())

    def add(self) -> None:
        self.rows.append([""] * len(self.spec))
        self.refresh()
        item = self.tree.get_children()[-1]
        self.tree.selection_set(item)
        self.tree.see(item)
        self.select_row()

    def remove(self) -> None:
        if self.current is None:
            return
        del self.rows[self.current]
        self.refresh()

    def clear_row(self) -> None:
        """Blank the whole row being edited (e.g. after a pick filled too much)."""
        if self.current is None or self.current >= len(self.rows):
            return
        idx = self.current
        self.rows[idx] = [""] * len(self.spec)
        for var in self.vars:
            var.set("")
        self.refresh()
        item = self.tree.get_children()[idx]
        self.tree.selection_set(item)
        self.select_row()

    def pick_window(self) -> None:
        """Fill the exe / class / title columns from a window that is open now."""

        def fill(title: str, klass: str, exe: str) -> None:
            values = {"title": title, "class": klass, "exe": exe}
            for i, col in enumerate(self.spec):
                if col.lower() in values:
                    self.vars[i].set(values[col.lower()])

        WindowPicker(self, fill)

    def move(self, delta: int) -> None:
        if self.current is None:
            return
        target = self.current + delta
        if 0 <= target < len(self.rows):
            self.rows[self.current], self.rows[target] = (
                self.rows[target], self.rows[self.current])
            self.refresh()
            self.tree.selection_set(self.tree.get_children()[target])

    def ok(self) -> None:
        self.on_ok(self.render_value())
        self.destroy()


# --------------------------------------------------------------------------
# The settings form
# --------------------------------------------------------------------------

class App:
    def __init__(self, root: tk.Tk, paths: dict[str, Path]) -> None:
        self.root = root
        self.paths = paths
        self.files = {doc: ConfFile(doc, paths[doc]) for doc in DOCS}
        for doc, conf in self.files.items():
            try:
                conf.load()
            except OSError as exc:
                messagebox.showerror("Astur settings",
                                     f"Cannot read {conf.path}:\n{exc}")
                raise SystemExit(1)
        self.doc = "astur"
        self.section = FIELDS["astur"][0][0]
        self.vars: dict[tuple[str, str], tk.StringVar] = {}
        self.dirty: dict[tuple[str, str], str] = {}
        self.rows: dict[tuple[str, str], tk.Frame] = {}
        self.search_hits: list[tuple[str, str, str]] = []

        root.title("Astur settings")
        root.geometry("1040x780+70+40")
        root.minsize(820, 520)
        style_init(root)

        self.build_toolbar()
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True)
        self.build_sidebar(body)
        self.build_content(body)
        self.build_status()
        self.fill_nav()
        self.select_section(self.section)
        self.bind_keys()
        self.root.after(2000, self.watch_disk)

    # -- chrome -------------------------------------------------------
    def build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=PANEL, height=44)
        bar.pack(fill="x")
        tk.Label(bar, text="Astur settings", bg=PANEL, fg=FG,
                 font=FONT_TITLE, padx=14).pack(side="left")

        self.doc_var = tk.StringVar(value=DOC_TITLES[self.doc])
        picker = ttk.Combobox(bar, textvariable=self.doc_var, state="readonly",
                              values=[DOC_TITLES[d] for d in DOCS], width=12)
        picker.pack(side="left", padx=(4, 10))
        picker.bind("<<ComboboxSelected>>",
                    lambda e: self.switch_doc(
                        DOCS[[DOC_TITLES[d] for d in DOCS].index(self.doc_var.get())]))

        self.search_var = tk.StringVar()
        search = ttk.Entry(bar, textvariable=self.search_var, width=34)
        search.pack(side="left", padx=(0, 6), pady=8)
        search.insert(0, "")
        self.search_entry = search
        self.search_var.trace_add("write", lambda *_: self.update_search())

        ttk.Button(bar, text="Reload", command=self.reload).pack(side="right", padx=(6, 12))
        ttk.Button(bar, text="Save", style="Accent.TButton",
                   command=self.save).pack(side="right")

    def build_sidebar(self, parent: tk.Widget) -> None:
        side = tk.Frame(parent, bg=PANEL, width=250)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="SECTIONS", bg=PANEL, fg=DIM, font=("Segoe UI", 8, "bold"),
                 anchor="w", padx=14, pady=2).pack(fill="x", pady=(12, 6))
        self.nav = ttk.Treeview(side, show="tree", selectmode="browse")
        self.nav.pack(fill="both", expand=True, padx=(6, 6), pady=(0, 8))
        self.nav.bind("<<TreeviewSelect>>", lambda e: self.on_nav())
        self.nav.tag_configure("dim", foreground=DIM)

    def build_content(self, parent: tk.Widget) -> None:
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(side="left", fill="both", expand=True)
        self.canvas, self.inner = scrollable(wrap)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=None)
        bar = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        bar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=bar.set)
        self.section_title = tk.Label(self.inner, text="", bg=BG, fg=FG,
                                      font=FONT_TITLE, anchor="w")
        self.section_title.pack(fill="x", padx=18, pady=(14, 2))
        self.section_help = tk.Label(self.inner, text="", bg=BG, fg=DIM,
                                     anchor="w", justify="left")
        self.section_help.pack(fill="x", padx=18, pady=(0, 8))
        self.section_body = tk.Frame(self.inner, bg=BG)
        self.section_body.pack(fill="both", expand=True, padx=6)

    def build_status(self) -> None:
        bar = tk.Frame(self.root, bg=PANEL, height=26)
        bar.pack(fill="x", side="bottom")
        self.status = tk.Label(bar, text="", bg=PANEL, fg=DIM, anchor="w", padx=12)
        self.status.pack(side="left")
        self.path_label = tk.Label(bar, text="", bg=PANEL, fg=DIM, anchor="e", padx=12)
        self.path_label.pack(side="right")

    def bind_keys(self) -> None:
        self.root.bind("<Control-s>", lambda e: (self.save(), "break")[1])
        self.root.bind("<Control-f>", lambda e: (self.search_entry.focus_set(), "break")[1])
        self.root.bind("<F5>", lambda e: (self.reload(), "break")[1])
        self.root.bind("<Escape>", lambda e: self.close_search())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # The search popup never takes the keyboard: typing goes on in the box,
        # and these keys pick a hit from there.
        self.search_entry.bind("<Return>", lambda e: (self.jump(), "break")[1])
        self.search_entry.bind("<Down>", lambda e: (self.move_hit(1), "break")[1])
        self.search_entry.bind("<Up>", lambda e: (self.move_hit(-1), "break")[1])

    def on_close(self) -> None:
        if self.dirty:
            many = len(self.dirty) != 1
            answer = messagebox.askyesnocancel(
                "Astur settings",
                f"{len(self.dirty)} unsaved change{'s' if many else ''}. "
                "Save before closing?")
            if answer is None:
                return
            if answer:
                self.save()
        self.root.destroy()

    def grabbed(self) -> bool:
        """Is a dialog holding a grab? (A ttk popdown can make Tk raise here.)"""
        try:
            return bool(self.root.grab_current())
        except (tk.TclError, KeyError):
            return False

    def watch_disk(self) -> None:
        """Pick up edits made to the files by something else (an editor, Astur)."""
        try:
            if not self.dirty and not self.grabbed():
                if any(c.changed_on_disk() for c in self.files.values()):
                    for conf in self.files.values():
                        try:
                            conf.load()
                        except OSError:
                            return
                    self.select_section(self.section)
                    self.update_status(force="Reloaded — the file changed on disk")
        finally:
            self.root.after(2000, self.watch_disk)

    # -- navigation ---------------------------------------------------
    def fill_nav(self) -> None:
        self.nav.delete(*self.nav.get_children())
        for title, _fields in FIELDS[self.doc]:
            self.nav.insert("", "end", iid=title, text=title)
        first = FIELDS[self.doc][0][0]
        self.nav.selection_set(first)
        self.nav.focus(first)

    def on_nav(self) -> None:
        sel = self.nav.selection()
        if sel:
            self.select_section(sel[0])

    def switch_doc(self, doc: str) -> None:
        self.doc = doc
        self.doc_var.set(DOC_TITLES[doc])
        self.fill_nav()
        self.select_section(FIELDS[doc][0][0])

    def select_section(self, title: str) -> None:
        self.section = title
        for _, (name, _fields) in [(0, (title, None))]:
            pass
        sec = next((fs for t, fs in FIELDS[self.doc] if t == title), [])
        self.section_title.configure(text=title)
        self.section_help.configure(
            text=f"{len(sec)} settings in {DOC_TITLES[self.doc]}. "
                 "Astur applies a saved change within about a tenth of a second.")
        for child in self.section_body.winfo_children():
            child.destroy()
        self.rows.clear()
        self.vars.clear()
        for field in sec:
            self.render_field(field)
        self.canvas.yview_moveto(0)

    # -- one row ------------------------------------------------------
    def render_field(self, field: Field) -> None:
        holder = tk.Frame(self.section_body, bg=BG)
        holder.pack(fill="x", padx=12, pady=2)
        strip = tk.Frame(holder, bg=BG, width=3)
        strip.pack(side="left", fill="y")
        row = tk.Frame(holder, bg=BG)
        row.pack(side="left", fill="x", expand=True, padx=(9, 0), pady=6)

        left = tk.Frame(row, bg=BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=field.label, bg=BG, fg=FG, font=FONT_BOLD,
                 anchor="w").pack(fill="x")
        if field.help:
            tk.Label(left, text=field.help, bg=BG, fg=DIM, font=FONT,
                     anchor="w", justify="left", wraplength=520).pack(fill="x")

        right = tk.Frame(row, bg=BG)
        wide = field.kind in ("ws_layouts", "mon_layouts")
        if not wide:
            right.pack(side="right", padx=(12, 4))
        key = (field.doc, field.key)
        current = self.files[field.doc].get(field.key)
        value = field.default if current is None else current
        var = tk.StringVar(value=value)
        self.vars[key] = var
        var.trace_add("write", lambda *_a, f=field, v=var: self.mark(f, v.get()))

        if field.kind == "ws_layouts":
            self.render_ws_layouts(left, var)
        elif field.kind == "mon_layouts":
            self.render_mon_layouts(left, var)
        elif field.kind == "bool":
            ttk.Checkbutton(right, variable=var, onvalue="true",
                            offvalue="false", text="").pack()
        elif field.kind == "enum":
            combo = ttk.Combobox(right, textvariable=var, state="readonly",
                                 values=field.choices, width=18)
            combo.pack()
        elif field.kind == "colour":
            ColorField(right, value, lambda v, f=field: self.mark(f, v)).pack()
        elif field.kind == "number":
            ttk.Entry(right, textvariable=var, width=10).pack()
            if field.lo is not None:
                tk.Label(right, text=f"{field.lo:g} … {field.hi:g}", bg=BG, fg=DIM,
                         font=("Segoe UI", 8)).pack(anchor="e")
        elif field.kind == "records":
            count = len([r for r in (value or "").split(";;") if r.strip()])
            ttk.Button(right, text=f"Edit…  ({count})",
                       command=lambda f=field, v=var: self.edit_records(f, v)).pack()
        elif field.kind == "colors":
            pairs = value.replace(",", " ").split() if value else []
            ttk.Button(right, text=f"Edit…  ({len(pairs)})",
                       command=lambda f=field, v=var: self.edit_records(f, v)).pack()
        elif field.kind == "key":
            combo = ttk.Combobox(right, textvariable=var, width=12,
                                 values=KEY_NAMES)
            combo.pack()
        elif field.kind == "list":
            ttk.Entry(right, textvariable=var, width=26).pack()
            tk.Label(right, text="separated by space or comma", bg=BG, fg=DIM,
                     font=("Segoe UI", 8)).pack(anchor="e")
        else:
            ttk.Entry(right, textvariable=var, width=26).pack()

        if field.key == "workspaces":
            var.trace_add("write", lambda *_a: self.rebuild_ws_layouts())

        self.rows[key] = strip

    # -- layout pickers -----------------------------------------------
    def ws_count(self) -> int:
        """How many workspace dropdowns to show: the workspaces key, 1..20."""
        var = self.vars.get(("astur", "workspaces"))
        raw = (var.get() if var is not None else None) or \
              self.files["astur"].get("workspaces") or "6"
        try:
            n = int(float(raw.strip()))
        except ValueError:
            n = 6
        return max(1, min(20, n))

    def render_ws_layouts(self, parent: tk.Widget, var: tk.StringVar) -> None:
        self.ws_var = var
        self.ws_box = tk.Frame(parent, bg=BG)
        self.ws_box.pack(fill="x", pady=(6, 2))
        self.ws_combos: list[ttk.Combobox] = []
        self.rebuild_ws_layouts()

    def rebuild_ws_layouts(self) -> None:
        box = getattr(self, "ws_box", None)
        if box is None or not box.winfo_exists():
            return
        for child in box.winfo_children():
            child.destroy()
        self.ws_combos = []
        parts = [p.strip() for p in (self.ws_var.get() or "").split(",")]
        for i in range(self.ws_count()):
            cell = tk.Frame(box, bg=BG)
            cell.grid(row=i // 8, column=i % 8, sticky="w", padx=(0, 8), pady=(0, 4))
            tk.Label(cell, text=str(i + 1), bg=BG, fg=DIM,
                     font=("Segoe UI", 8)).pack()
            combo = ttk.Combobox(cell, state="readonly", width=9,
                                 values=[""] + LAYOUTS)
            combo.set(parts[i].strip() if i < len(parts) else "")
            if combo.get() not in [""] + LAYOUTS:
                combo.set("")
            combo.pack()
            combo.bind("<<ComboboxSelected>>",
                       lambda _e: self.sync_ws_layouts())
            self.ws_combos.append(combo)

    def sync_ws_layouts(self) -> None:
        parts = [c.get().strip() for c in self.ws_combos]
        while parts and not parts[-1]:
            parts.pop()
        self.ws_var.set(", ".join(parts))

    def render_mon_layouts(self, parent: tk.Widget, var: tk.StringVar) -> None:
        self.mon_var = var
        box = tk.Frame(parent, bg=BG)
        box.pack(fill="x", pady=(6, 2))
        ttk.Entry(box, textvariable=var, width=40).pack(anchor="w")
        row = tk.Frame(box, bg=BG)
        row.pack(anchor="w", pady=(4, 0))
        buttons = [(name, lambda n=name: self.add_mon_layout(n)) for name in LAYOUTS]
        buttons.append(("+ blank", lambda: self.add_mon_layout("")))
        for i, (text, cmd) in enumerate(buttons):
            ttk.Button(row, text=text, width=max(9, len(text) + 2),
                       command=cmd).grid(row=i // 4, column=i % 4,
                                         sticky="w", padx=(0, 4), pady=(0, 4))

    def add_mon_layout(self, name: str) -> None:
        parts = [p.strip() for p in (self.mon_var.get() or "").split(",")]
        while parts and not parts[-1]:
            parts.pop()
        parts.append(name)
        self.mon_var.set(", ".join(parts))

    # -- editing ------------------------------------------------------
    def mark(self, field: Field, raw: str) -> None:
        key = (field.doc, field.key)
        value = field.normalise(raw)
        if value == (self.files[field.doc].get(field.key) or field.default):
            self.dirty.pop(key, None)
        else:
            self.dirty[key] = value
        self.update_status()

    def edit_records(self, field: Field, var: tk.StringVar) -> None:
        colors = field.kind == "colors"
        RecordsDialog(self.root, field.label, field.spec, var.get(),
                      lambda text: var.set(text),
                      rec_sep=None if colors else ";;", is_colors=colors)

    # -- commands -----------------------------------------------------
    def save(self) -> None:
        changed = 0
        for (doc, key), value in list(self.dirty.items()):
            if self.files[doc].set(key, value):
                changed += 1
        for doc, conf in self.files.items():
            if conf.save():
                changed += 1
        self.dirty.clear()
        self.update_status(saved=True)

    def reload(self) -> None:
        for conf in self.files.values():
            if conf.changed_on_disk() and not self.confirm_discard():
                return
        for conf in self.files.values():
            conf.load()
        self.dirty.clear()
        self.select_section(self.section)
        self.update_status(force="Reloaded from disk")

    def confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Astur settings",
            "One of the files changed on disk. Reload and lose unsaved edits?")

    def update_status(self, saved: bool = False, force: str = "") -> None:
        if force:
            text = force
        elif self.dirty:
            text = f"{len(self.dirty)} unsaved change" + ("s" if len(self.dirty) != 1 else "")
        elif saved:
            text = "Saved — Astur picks it up in about 0.1 s"
        else:
            text = "No changes"
        self.status.configure(text=text,
                              fg=OK if saved else (WARN if self.dirty else DIM))
        self.path_label.configure(text=str(self.files[self.doc].path))

    # -- search -------------------------------------------------------
    def update_search(self) -> None:
        query = self.search_var.get().strip().lower()
        self.close_search()
        if len(query) < 2:
            return
        hits = []
        for doc in DOCS:
            for title, fields in FIELDS[doc]:
                for f in fields:
                    haystack = f"{f.key} {f.label} {f.help}".lower()
                    if query in haystack:
                        rank = 0 if f.key.lower().startswith(query) else 1
                        hits.append((rank, doc, title, f.key))
        hits.sort()
        self.search_hits = [(d, t, k) for _r, d, t, k in hits[:40]]
        if not self.search_hits:
            return
        self.show_hits()

    def show_hits(self) -> None:
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.configure(bg=BORDER)
        x = self.search_entry.winfo_rootx()
        y = self.search_entry.winfo_rooty() + self.search_entry.winfo_height()
        top.geometry(f"520x{min(320, 26 * len(self.search_hits) + 4)}+{x}+{y}")
        self.hits_box = tk.Listbox(top, bg=PANEL, fg=FG, selectbackground=ACCENT,
                                   selectforeground="#101216", bd=0,
                                   highlightthickness=0, activestyle="none",
                                   font=FONT)
        self.hits_box.pack(fill="both", expand=True, padx=1, pady=1)
        for doc, title, key in self.search_hits:
            value = self.files[doc].get(key)
            shown = value if value is not None else "(default)"
            self.hits_box.insert("end", f"  {key} = {shown[:40]}    — {DOC_TITLES[doc]} › {title}")
        self.hits_box.selection_set(0)
        self.hits_box.bind("<Return>", lambda e: self.jump())
        self.hits_box.bind("<Double-Button-1>", lambda e: self.jump())
        self.hits_box.bind("<ButtonRelease-1>", lambda e: self.jump())
        self.hits_box.bind("<Escape>", lambda e: self.close_search())
        self.hits_box.bind("<Up>", lambda e: self.move_hit(-1))
        self.hits_box.bind("<Down>", lambda e: self.move_hit(1))
        self.hits_popup = top

    def move_hit(self, delta: int) -> None:
        if not hasattr(self, "hits_box"):
            return
        idx = (self.hits_box.curselection() or (0,))[0] + delta
        idx = max(0, min(len(self.search_hits) - 1, idx))
        self.hits_box.selection_clear(0, "end")
        self.hits_box.selection_set(idx)
        self.hits_box.see(idx)

    def jump(self) -> None:
        if not hasattr(self, "hits_box") or not self.search_hits:
            return
        idx = (self.hits_box.curselection() or (0,))[0]
        doc, title, key = self.search_hits[idx]
        self.close_search()
        self.search_var.set("")
        if doc != self.doc:
            self.switch_doc(doc)
        self.nav.selection_set(title)
        self.select_section(title)
        self.root.update_idletasks()
        strip = self.rows.get((doc, key))
        if strip is not None:
            self.scroll_to(strip)
            self.flash(strip)
            strip.master.master.focus_set()

    def flash(self, strip: tk.Widget, ms: int = 1200) -> None:
        """Mark a row for a moment. The row may be gone by the time it ends
        (the section was rebuilt), so both ends have to survive that."""
        try:
            strip.configure(bg=ACCENT)
        except tk.TclError:
            return

        def off() -> None:
            try:
                if strip.winfo_exists():
                    strip.configure(bg=BG)
            except tk.TclError:
                pass

        self.root.after(ms, off)

    def scroll_to(self, widget: tk.Widget) -> None:
        self.canvas.update_idletasks()
        y = widget.winfo_rooty() - self.inner.winfo_rooty()
        height = self.inner.winfo_height() or 1
        self.canvas.yview_moveto(max(0.0, min(1.0, y / height - 0.1)))

    def close_search(self) -> None:
        if hasattr(self, "hits_popup"):
            try:
                self.hits_popup.destroy()
            except tk.TclError:
                pass
            del self.hits_popup
        if hasattr(self, "hits_box"):
            del self.hits_box


# --------------------------------------------------------------------------
# Round trip check
# --------------------------------------------------------------------------

def selftest(astur: Path, navbar: Path) -> int:
    """Load each file, write it back unchanged, and compare the bytes."""
    status = 0
    for doc, src in (("astur", astur), ("navbar", navbar)):
        if not src.exists():
            print(f"{doc:7} skip (no {src})")
            continue
        with tempfile.TemporaryDirectory(prefix="astur-selftest-") as tmp:
            copy = Path(tmp) / src.name
            copy.write_bytes(src.read_bytes())
            conf = ConfFile(doc, copy)
            conf.load()
            before = copy.read_bytes()
            conf.save()
            after = copy.read_bytes()
            if before == after:
                print(f"{doc:7} ok   {len(before):6} bytes, {len(conf.lines)} lines")
            else:
                status = 1
                print(f"{doc:7} FAIL {len(before)} -> {len(after)} bytes")
                _first_difference(before, after)
    return status


def _first_difference(a: bytes, b: bytes) -> None:
    al = a.splitlines()
    bl = b.splitlines()
    for i, (x, y) in enumerate(zip(al, bl), 1):
        if x != y:
            print(f"        line {i}: {x!r} -> {y!r}")
            return
    print(f"        length differs after line {min(len(al), len(bl))}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Edit astur.conf and navbar.conf.")
    ap.add_argument("--astur", type=Path, default=default_path("astur"))
    ap.add_argument("--navbar", type=Path, default=default_path("navbar"))
    ap.add_argument("--selftest", action="store_true",
                    help="read, write back unchanged, compare bytes")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest(args.astur, args.navbar)

    for path in (args.astur, args.navbar):
        if not path.exists():
            print(f"missing: {path}\nRun Astur once to create it.", file=sys.stderr)
            return 1

    root = tk.Tk()
    App(root, {"astur": args.astur, "navbar": args.navbar})
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
