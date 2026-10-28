//! Files on disk: ~/.codex/auth.json and ~/.codex/codex-switcher/{profiles/, profiles_order.json}.

use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct Paths {
    pub codex_dir: PathBuf,
    pub auth_file: PathBuf,
    pub profiles_dir: PathBuf,
    pub order_file: PathBuf,
}

impl Paths {
    pub fn new() -> Self {
        let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
        Self::under(home.join(".codex"))
    }

    pub fn under(codex_dir: PathBuf) -> Self {
        let app_dir = codex_dir.join("codex-switcher");
        Self {
            auth_file: codex_dir.join("auth.json"),
            profiles_dir: app_dir.join("profiles"),
            order_file: app_dir.join("profiles_order.json"),
            codex_dir,
        }
    }

    pub fn ensure(&self) {
        let _ = fs::create_dir_all(&self.profiles_dir);
    }

    pub fn profile(&self, name: &str) -> PathBuf {
        self.profiles_dir.join(format!("{name}.json"))
    }

    pub fn backup_file(&self) -> PathBuf {
        self.codex_dir.join("auth.json.bak")
    }

    /// One-time move from ~/.codex/profiles and ~/.codex/profiles_order.json.
    pub fn migrate_legacy(&self) {
        let old_profiles = self.codex_dir.join("profiles");
        let old_order = self.codex_dir.join("profiles_order.json");

        if old_profiles.is_dir() && !same_path(&old_profiles, &self.profiles_dir) {
            if let Ok(entries) = fs::read_dir(&old_profiles) {
                for entry in entries.flatten() {
                    let src = entry.path();
                    if src.extension().and_then(|e| e.to_str()) != Some("json") {
                        continue;
                    }
                    let Some(file_name) = src.file_name() else {
                        continue;
                    };
                    let dest = self.profiles_dir.join(file_name);
                    if dest.exists() {
                        continue;
                    }
                    if fs::rename(&src, &dest).is_err() {
                        let _ = fs::copy(&src, &dest);
                    }
                }
            }
            // Only removes the folder when it is empty.
            let _ = fs::remove_dir(&old_profiles);
        }

        if old_order.exists()
            && !self.order_file.exists()
            && !same_path(&old_order, &self.order_file)
            && fs::rename(&old_order, &self.order_file).is_err()
        {
            let _ = fs::copy(&old_order, &self.order_file);
        }
    }

    fn profile_names_on_disk(&self) -> Vec<String> {
        let mut names: Vec<String> = fs::read_dir(&self.profiles_dir)
            .map(|rd| {
                rd.flatten()
                    .map(|e| e.path())
                    .filter(|p| {
                        p.is_file() && p.extension().and_then(|e| e.to_str()) == Some("json")
                    })
                    .filter_map(|p| p.file_stem().and_then(|s| s.to_str()).map(str::to_string))
                    .collect()
            })
            .unwrap_or_default();
        names.sort_by_key(|n| n.to_lowercase());
        names
    }

    pub fn read_order(&self) -> Vec<String> {
        fs::read(&self.order_file)
            .ok()
            .and_then(|b| serde_json::from_slice::<Vec<String>>(&b).ok())
            .unwrap_or_default()
    }

    pub fn write_order(&self, order: &[String]) -> Result<(), String> {
        write_json(&self.order_file, &serde_json::json!(order))
    }

    /// Saved order first, then any profile the order file does not know yet.
    pub fn ordered_profiles(&self) -> Vec<String> {
        let mut on_disk = self.profile_names_on_disk();
        let mut ordered = Vec::with_capacity(on_disk.len());
        for name in self.read_order() {
            if let Some(i) = on_disk.iter().position(|n| *n == name) {
                ordered.push(on_disk.remove(i));
            }
        }
        ordered.extend(on_disk);
        ordered
    }

    /// Persists the saved order with any new profiles appended and missing ones dropped.
    pub fn sync_order(&self) -> Result<(), String> {
        self.write_order(&self.ordered_profiles())
    }
}

fn same_path(a: &Path, b: &Path) -> bool {
    match (a.canonicalize(), b.canonicalize()) {
        (Ok(a), Ok(b)) => a == b,
        _ => a == b,
    }
}

/// Turns user input into a file stem that is valid on every platform.
pub fn sanitize_name(raw: &str) -> Result<String, String> {
    let cleaned: String = raw
        .trim()
        .chars()
        .map(|c| match c {
            '/' | '\\' | ':' | '*' | '?' | '"' | '<' | '>' | '|' => '_',
            c if c.is_control() => '_',
            c => c,
        })
        .collect();
    let cleaned = cleaned.trim_end_matches(['.', ' ']).to_string();
    if cleaned.is_empty() || cleaned == "." || cleaned == ".." {
        return Err("Profile name is empty.".into());
    }
    Ok(cleaned)
}

pub fn write_json(path: &Path, value: &Value) -> Result<(), String> {
    let text = serde_json::to_string_pretty(value).map_err(|e| e.to_string())?;
    fs::write(path, text).map_err(|e| format!("Could not write {}: {e}", path.display()))
}

pub fn read_json(path: &Path) -> Result<Value, String> {
    let bytes = fs::read(path).map_err(|e| format!("Could not read {}: {e}", path.display()))?;
    serde_json::from_slice(&bytes).map_err(|e| format!("{} is not valid JSON: {e}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitizes_names() {
        assert_eq!(sanitize_name(" a/b:c ").unwrap(), "a_b_c");
        assert_eq!(sanitize_name("work.").unwrap(), "work");
        assert!(sanitize_name("  ").is_err());
        assert!(sanitize_name("..").is_err());
    }

    #[test]
    fn order_keeps_saved_then_appends() {
        let dir = std::env::temp_dir().join(format!("cs-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        let paths = Paths::under(dir.clone());
        paths.ensure();
        for n in ["b", "a", "c"] {
            fs::write(paths.profile(n), "{}").unwrap();
        }
        paths
            .write_order(&["c".into(), "gone".into(), "b".into()])
            .unwrap();
        assert_eq!(paths.ordered_profiles(), vec!["c", "b", "a"]);
        let _ = fs::remove_dir_all(&dir);
    }
}
