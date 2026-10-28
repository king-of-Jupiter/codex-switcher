mod auth;
mod bundle;
mod net;
mod restart;
mod storage;

use auth::AuthInfo;
use serde::Serialize;
use serde_json::Value;
use std::path::PathBuf;
use storage::{sanitize_name, Paths};

/// Error a command returns when the target profile exists and `overwrite` was false.
const EXISTS: &str = "EXISTS";

type CmdResult<T> = Result<T, String>;

#[derive(Serialize)]
struct ProfileRow {
    name: String,
    info: AuthInfo,
    active: bool,
}

#[derive(Serialize)]
struct AppState {
    auth_exists: bool,
    active_profile: Option<String>,
    active_info: AuthInfo,
    profiles: Vec<ProfileRow>,
    profiles_dir: String,
}

fn paths() -> Paths {
    Paths::new()
}

#[tauri::command]
fn get_state() -> AppState {
    let p = paths();
    let auth_bytes = std::fs::read(&p.auth_file).ok();
    let mut active_profile = None;

    let profiles = p
        .ordered_profiles()
        .into_iter()
        .map(|name| {
            let file = p.profile(&name);
            let active = auth_bytes.is_some() && std::fs::read(&file).ok() == auth_bytes;
            if active && active_profile.is_none() {
                active_profile = Some(name.clone());
            }
            ProfileRow {
                info: auth::extract_from_file(&file),
                name,
                active,
            }
        })
        .collect();

    AppState {
        auth_exists: auth_bytes.is_some(),
        active_profile,
        active_info: auth::extract_from_file(&p.auth_file),
        profiles,
        profiles_dir: p.profiles_dir.display().to_string(),
    }
}

#[tauri::command]
fn inspect_auth_text(text: String) -> CmdResult<AuthInfo> {
    let v: Value = serde_json::from_str(text.trim()).map_err(|e| format!("Not valid JSON: {e}"))?;
    if !v.is_object() {
        return Err("Expected a JSON object.".into());
    }
    Ok(auth::extract_from_value(&v))
}

#[tauri::command]
fn inspect_auth_file(path: PathBuf) -> AuthInfo {
    auth::extract_from_file(&path)
}

fn target_for(name: &str, overwrite: bool) -> CmdResult<(String, PathBuf)> {
    let p = paths();
    let name = sanitize_name(name)?;
    let dest = p.profile(&name);
    if dest.exists() && !overwrite {
        return Err(EXISTS.into());
    }
    Ok((name, dest))
}

#[tauri::command]
fn save_active(name: String, overwrite: bool) -> CmdResult<String> {
    let p = paths();
    if !p.auth_file.exists() {
        return Err("auth.json does not exist. Log in to ChatGPT/Codex first.".into());
    }
    let (name, dest) = target_for(&name, overwrite)?;
    std::fs::copy(&p.auth_file, &dest).map_err(|e| e.to_string())?;
    p.sync_order()?;
    Ok(name)
}

#[tauri::command]
fn import_profile_file(path: PathBuf, name: String, overwrite: bool) -> CmdResult<String> {
    let (name, dest) = target_for(&name, overwrite)?;
    std::fs::copy(&path, &dest).map_err(|e| e.to_string())?;
    paths().sync_order()?;
    Ok(name)
}

#[tauri::command]
fn save_profile_text(name: String, text: String, overwrite: bool) -> CmdResult<String> {
    let v: Value = serde_json::from_str(text.trim()).map_err(|e| format!("Not valid JSON: {e}"))?;
    if !v.is_object() {
        return Err("Expected a JSON object.".into());
    }
    let (name, dest) = target_for(&name, overwrite)?;
    storage::write_json(&dest, &v)?;
    paths().sync_order()?;
    Ok(name)
}

#[tauri::command]
fn rename_profile(old: String, new: String) -> CmdResult<String> {
    let p = paths();
    let new = sanitize_name(&new)?;
    if new == old {
        return Ok(new);
    }
    let dest = p.profile(&new);
    // A case-only rename on a case-insensitive disk points at the same file.
    if dest.exists() && !new.eq_ignore_ascii_case(&old) {
        return Err(format!("A profile named \"{new}\" already exists."));
    }
    let mut order = p.ordered_profiles();
    std::fs::rename(p.profile(&old), &dest).map_err(|e| e.to_string())?;
    for n in order.iter_mut().filter(|n| **n == old) {
        *n = new.clone();
    }
    p.write_order(&order)?;
    Ok(new)
}

#[tauri::command]
fn delete_profile(name: String) -> CmdResult<()> {
    let p = paths();
    std::fs::remove_file(p.profile(&name)).map_err(|e| e.to_string())?;
    p.sync_order()
}

#[tauri::command]
fn save_order(order: Vec<String>) -> CmdResult<()> {
    let p = paths();
    p.write_order(&order)?;
    p.sync_order()
}

#[tauri::command]
async fn activate_profile(name: String, restart: bool) -> CmdResult<()> {
    let p = paths();
    let src = p.profile(&name);
    if !src.exists() {
        return Err(format!("Profile {name}.json not found."));
    }
    if p.auth_file.exists() {
        std::fs::copy(&p.auth_file, p.backup_file()).map_err(|e| e.to_string())?;
    }
    std::fs::copy(&src, &p.auth_file).map_err(|e| e.to_string())?;
    if restart {
        std::thread::spawn(restart::restart_codex);
    }
    Ok(())
}

#[tauri::command]
async fn new_account() -> CmdResult<()> {
    let p = paths();
    if p.auth_file.exists() {
        std::fs::copy(&p.auth_file, p.backup_file()).map_err(|e| e.to_string())?;
        std::fs::remove_file(&p.auth_file)
            .map_err(|e| format!("Failed to reset auth.json: {e}"))?;
    }
    std::thread::spawn(restart::restart_codex);
    Ok(())
}

/// Usage for the active auth.json (`name` = null) or for a saved profile.
#[tauri::command]
async fn fetch_usage(name: Option<String>) -> Value {
    tauri::async_runtime::spawn_blocking(move || {
        let p = paths();
        let file = match &name {
            Some(n) => p.profile(n),
            None => p.auth_file.clone(),
        };
        net::fetch_usage(&file, &p)
    })
    .await
    .unwrap_or_else(|e| serde_json::json!({ "error": e.to_string() }))
}

#[tauri::command]
fn export_all(path: PathBuf) -> CmdResult<usize> {
    bundle::export_all(&paths(), &path)
}

#[tauri::command]
fn import_scan(path: PathBuf) -> CmdResult<Vec<bundle::ScanEntry>> {
    bundle::scan(&paths(), &path)
}

#[tauri::command]
fn import_apply(path: PathBuf, overwrite: Vec<String>) -> CmdResult<bundle::ImportResult> {
    bundle::apply(&paths(), &path, &overwrite)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let p = paths();
    p.ensure();
    p.migrate_legacy();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .invoke_handler(tauri::generate_handler![
            get_state,
            inspect_auth_text,
            inspect_auth_file,
            save_active,
            import_profile_file,
            save_profile_text,
            rename_profile,
            delete_profile,
            save_order,
            activate_profile,
            new_account,
            fetch_usage,
            export_all,
            import_scan,
            import_apply,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Codex Switcher");
}
