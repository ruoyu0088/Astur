# CLAUDE.md — Astur

`AGENTS.md` is the manual. Read it first: it has the project map, the goals (the
bar to hold), the thread model, the conventions, the build and quit notes, and
the documentation rules. If the two files ever disagree, `AGENTS.md` is right —
then fix this one.

Three rules worth repeating here, because they are the ones a session gets wrong:

1. **The docs are part of the change.** A behaviour, key or config change is not
   done until `README.md` (user-facing, ask first), the template comments in
   `crates/astur-config/src/lib.rs`, and `python tools/gen_schema.py` all agree
   with the code. Details in `AGENTS.md` → "Who keeps these docs".
2. **Verify before reporting.** `cargo build`, `cargo test --workspace`,
   `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets --
   -D warnings`. CI runs all four with `-D warnings`, so a warning is a failure.
3. **Read before writing.** `crates/astur/src/main.rs` is ~30k lines: `grep` for
   the symbol and `read` the window you need instead of guessing at line
   numbers, and re-read a file after it changes.
