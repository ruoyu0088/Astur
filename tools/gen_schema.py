#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate the SCHEMA table inside astur_settings.py.

The editor is one self-contained file, but its schema is not hand written: the
two config templates in `crates/astur-config/src/lib.rs` (DEFAULT_CONFIG and
DEFAULT_NAVBAR) already say, key by key, what the value is, what it defaults to
and -- in the comments above it -- what it means. This script reads them and
rewrites the block between `# @@SCHEMA-BEGIN@@` and `# @@SCHEMA-END@@`.

So adding a key to Astur stays a two step job:

    1. add the key and its comment to the template in lib.rs
    2. python tools/gen_schema.py

Only the standard library is used.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "crates" / "astur-config" / "src" / "lib.rs"
TARGET = HERE / "astur_settings.py"
BEGIN = "# @@SCHEMA-BEGIN@@"
END = "# @@SCHEMA-END@@"

# Keys whose type the comments do not spell out, or spell out wrongly.
OVERRIDES = {
    ("navbar", "shape"): ("enum", "|strip|islands|pills"),
    ("navbar", "workspace_style"): ("enum", "box|pill|underline|dot"),
    ("navbar", "separator_style"): ("enum", "line|dot|powerline"),
    ("navbar", "icon_mode"): ("enum", "icon|text|both|glyph|glyph_only"),
    ("navbar", "palette"): (
        "enum", "classic|catppuccin|nord|gruvbox|rosepine|mono|system"),
    ("navbar", "left"): ("list", "widget"),
    ("navbar", "center"): ("list", "widget"),
    ("navbar", "right"): ("list", "widget"),
    ("navbar", "widget_colors"): ("colors", "widget:colour"),
    ("astur", "extra_hotkeys"): ("records", "chord|action|argument"),
    ("astur", "launcher_entries"): ("records", "label|target|icon"),
    ("astur", "system_actions"): ("records", "category|label|command"),
    ("astur", "window_rules"): (
        "records", "action|exe|class|title|workspace|monitor"),
}

# The single-key binds: one key name each, whether it is `J` or `[`.
KEY_BLINDS = (
    "key_focus_next", "key_focus_prev", "key_shrink_master", "key_grow_master",
    "key_promote_master", "key_toggle_tiling", "key_toggle_float",
    "key_close_window", "key_cycle_width", "key_center_column",
    "key_consume_left", "key_consume_right", "key_fill_desktop",
    "key_system_menu", "key_switch_ws_1", "key_switch_ws_2", "key_switch_ws_3",
)
for _key in KEY_BLINDS:
    OVERRIDES[("astur", _key)] = ("key", "")

# Help written here rather than read from the template. The key_* block shares
# one comment for all of them, so the template cannot say what a single key does.
HELP_OVERRIDES = {
    ("astur", "main_key"):
        "The key held down for every Astur shortcut (Mod in this file): lalt, "
        "ralt, win, alt, ctrl+win or capslock. Left Alt is reserved, so apps "
        "never see it; with ralt the right Alt is reserved instead.",
    ("astur", "key_focus_next"):
        "Focus the window to the right (Mod + this key). One key name.",
    ("astur", "key_focus_prev"):
        "Focus the window to the left (Mod + this key).",
    ("astur", "key_shrink_master"):
        "Make the main window smaller; in scrolling, step the column narrower.",
    ("astur", "key_grow_master"):
        "Make the main window bigger; in scrolling, step the column wider.",
    ("astur", "key_promote_master"):
        "Make the focused window the main one.",
    ("astur", "key_toggle_tiling"):
        "Turn tiling on or off. Off leaves every window floating.",
    ("astur", "key_toggle_float"):
        "Float the focused window, or put it back into the layout.",
    ("astur", "key_close_window"):
        "Close the focused window.",
    ("astur", "key_cycle_width"):
        "Step the scrolling column through scroll_width_presets; with Shift, "
        "the window height.",
    ("astur", "key_center_column"):
        "Scroll the focused column to the middle of the screen.",
    ("astur", "key_consume_left"):
        "Stack the window on the left into the focused column.",
    ("astur", "key_consume_right"):
        "Push the focused window into the column on the right.",
    ("astur", "key_fill_desktop"):
        "Fill the whole work area with the focused window, or put everything "
        "back (the same key toggles).",
    ("astur", "key_system_menu"):
        "Open the power menu: lock, sleep, restart and Astur's own actions.",
    ("astur", "key_switch_ws_1"):
        "Go to workspace 1; with Shift, move the focused window there.",
    ("astur", "key_switch_ws_2"):
        "Go to workspace 2; with Shift, move the focused window there.",
    ("astur", "key_switch_ws_3"):
        "Go to workspace 3; with Shift, move the focused window there.",
}


def extract(name: str) -> list[str]:
    """The lines of one `const NAME: &str = "\\` template in lib.rs."""
    text = SRC.read_text(encoding="utf-8")
    start = text.index(f'const {name}: &str = "\\\n')
    start = text.index("\n", start) + 1
    end = text.index('\n";', start)
    out = []
    for line in text[start:end].split("\n"):
        line = line.replace("\\\\", "\x00").replace('\\"', '"')
        out.append(line.replace("\x00", "\\"))
    return out


RULE = re.compile(r"^#\s*(?:-{5,}|={5,})\s*$")


def compact(comment: list[str]) -> str:
    lines = list(comment)
    # A banner (`# ====`, a heading, `# ====`) introduces the section, not the
    # key: main_key's help used to start with a row of '=' and a cut heading.
    while len(lines) >= 2 and RULE.match(lines[0]):
        lines.pop(0)
        if lines and not RULE.match(lines[0]):
            lines.pop(0)
            if lines and RULE.match(lines[0]):
                lines.pop(0)
    parts = [c.lstrip("#").strip() for c in lines]
    text = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
    return text if len(text) <= 240 else text[:237].rstrip() + "..."


NUM = re.compile(r"\b(int|float)\s+(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)")
VAL = re.compile(r"values:\s*([a-z0-9_+\- ]+(?:\s*\|\s*[a-z0-9_+\- ]+)+)", re.I)


def options_from_comment(comment: list[str]) -> list[str]:
    """The indented `name  description` lines the templates use for enums."""
    names = []
    for line in comment:
        m = re.match(r"^#\s{2,}([a-z_0-9]{2,})\s{2,}\S", line)
        if m:
            names.append(m.group(1))
    return names


def kind_of(doc: str, key: str, comment: list[str], value: str) -> tuple[str, str]:
    if (doc, key) in OVERRIDES:
        return OVERRIDES[(doc, key)]
    joined = " ".join(c.lstrip("#") for c in comment)
    m = VAL.search(joined)
    if m:
        return "enum", re.sub(r"\s+", "", m.group(1))
    m = NUM.search(joined)
    if m:
        return "number", f"{m.group(2)}..{m.group(3)}"
    low = joined.lower()
    if re.search(r"\bbool(ean)?\b", low):
        return "bool", ""
    if re.search(r"\bcolou?r\b|\bhex\b", low):
        return "colour", ""
    if re.search(r"\bcolou?rs\b", low) or "palette" in low:
        if ";;" in value:
            return "records", ""
        return "colour", ""
    if re.search(r"\bkeys?\b", low) and re.match(r"^[A-Za-z0-9_ ]*$", value):
        return "key", ""
    v = value.strip()
    if v in ("true", "false"):
        return "bool", ""
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
        return "colour", ""
    if ";;" in v:
        return "records", ""
    if re.fullmatch(r"-?\d+", v) or re.fullmatch(r"-?\d*\.\d+", v):
        return "number", ""
    if "," in v:
        return "list", ""
    if v and re.fullmatch(r"[a-z0-9_]+(?: [a-z0-9_]+)+", v):
        return "list", ""
    names = options_from_comment(comment)
    if len(names) >= 2 and (not v or v in names):
        return "enum", "|".join([""] + names if not v else names)
    return "text", ""


HEAD = re.compile(r"^#\s*(?:-{10,}|={10,})\s*$")


def parse(doc: str, lines: list[str]) -> list[tuple[str, list[tuple]]]:
    sections: list[tuple[str, list[tuple]]] = []
    title = "General"
    comment: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if HEAD.match(line):
            if (i + 2 < len(lines) and lines[i + 1].startswith("#")
                    and HEAD.match(lines[i + 2])):
                title = lines[i + 1].lstrip("#").strip()
                # The templates explain in a bracket after the name; a nav
                # entry reads better without it.
                title = re.sub(r"\s*\(.*\)$", "", title).strip() or title
                if title in ("Astur navbar configuration", "Astur configuration"):
                    title = "General"
                i += 3
                comment = []
                continue
        if line.startswith("#"):
            comment.append(line)
            i += 1
            continue
        m = re.match(r"^([a-z0-9_]+)\s*=\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).rstrip()
            kind, extra = kind_of(doc, key, comment, value)
            help_text = HELP_OVERRIDES.get((doc, key)) or compact(comment)
            if not sections or sections[-1][0] != title:
                sections.append((title, []))
            sections[-1][1].append(
                (key, kind, value, extra, help_text))
            comment = []
            i += 1
            continue
        if not line.strip():
            comment = []
        i += 1
    return sections


def q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def schema_source() -> str:
    astur = parse("astur", extract("DEFAULT_CONFIG"))
    navbar = parse("navbar", extract("DEFAULT_NAVBAR"))
    lines = ["SCHEMA_DATA = {"]
    for doc, sections in (("astur", astur), ("navbar", navbar)):
        lines.append(f'    "{doc}": [')
        for title, fields in sections:
            lines.append(f"        ({q(title)}, [")
            for key, kind, value, extra, help_ in fields:
                lines.append(
                    f"            ({q(key)}, {q(kind)}, {q(value)}, "
                    f"{q(extra)}, {q(help_)}),")
            lines.append("        ]),")
        lines.append("    ],")
    lines.append("}")
    counts = {d: sum(len(f) for _, f in s) for d, s in (("astur", astur), ("navbar", navbar))}
    print(f"astur: {len(astur)} sections, {counts['astur']} keys")
    print(f"navbar: {len(navbar)} sections, {counts['navbar']} keys")
    return "\n".join(lines)


def main() -> int:
    if not SRC.exists():
        print(f"cannot find {SRC}")
        return 1
    text = TARGET.read_text(encoding="utf-8")
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < i:
        print(f"markers not found in {TARGET}")
        return 1
    body = schema_source()
    new = text[:i + len(BEGIN)] + "\n" + body + "\n" + text[j:]
    if new == text:
        print("schema unchanged")
        return 0
    TARGET.write_text(new, encoding="utf-8")
    print(f"updated {TARGET} ({len(new) - len(text):+d} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
