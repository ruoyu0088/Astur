// Embed the Windows resource script (the app icon) into astur.exe.
// See astur.rc / assets/astur.ico. No-op on non-Windows targets.
//
// Also drops the settings editor next to the binary (target/<profile>/
// astur_settings.py): astur.exe looks for it beside itself first, and a plain
// `cargo build --release` should produce something the tray's "Astur Settings"
// can actually start.
fn main() {
    embed_resource::compile("astur.rc", embed_resource::NONE);
    copy_settings_editor();
}

fn copy_settings_editor() {
    let manifest = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let script = manifest.join("../../tools/astur_settings.py");
    println!("cargo:rerun-if-changed={}", script.display());
    let Ok(out) = std::env::var("OUT_DIR") else {
        return;
    };
    // OUT_DIR is target/<profile>/build/astur-<hash>/out.
    let out = std::path::PathBuf::from(out);
    let Some(profile) = out.ancestors().nth(3) else {
        return;
    };
    let dest = profile.join("astur_settings.py");
    if script.is_file() {
        let _ = std::fs::copy(&script, &dest);
    }
}
