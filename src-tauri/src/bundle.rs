//! Export and import of every profile at once: a ZIP (one file per profile plus
//! profiles_order.json) or a JSON bundle `{export_version, exported_at, profiles, order}`.

use crate::auth;
use crate::storage::{self, Paths};
use serde::Serialize;
use serde_json::{json, Map, Value};
use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;

fn is_json_path(path: &Path) -> bool {
    path.extension()
        .and_then(|e| e.to_str())
        .map(|e| e.eq_ignore_ascii_case("json"))
        .unwrap_or(false)
}

fn is_zip_path(path: &Path) -> bool {
    path.extension()
        .and_then(|e| e.to_str())
        .map(|e| e.eq_ignore_ascii_case("zip"))
        .unwrap_or(false)
}

pub fn export_all(paths: &Paths, dest: &Path) -> Result<usize, String> {
    let order = paths.ordered_profiles();
    if order.is_empty() {
        return Err("No saved profiles to export.".into());
    }

    if is_json_path(dest) {
        let mut profiles = Map::new();
        for name in &order {
            if let Ok(v) = storage::read_json(&paths.profile(name)) {
                profiles.insert(name.clone(), v);
            }
        }
        let count = profiles.len();
        let bundle = json!({
            "export_version": 1,
            "exported_at": chrono::Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string(),
            "profiles": profiles,
            "order": order,
        });
        storage::write_json(dest, &bundle)?;
        return Ok(count);
    }

    let file =
        File::create(dest).map_err(|e| format!("Could not create {}: {e}", dest.display()))?;
    let mut zip = zip::ZipWriter::new(file);
    let opts = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    let mut count = 0;
    for name in &order {
        let Ok(bytes) = std::fs::read(paths.profile(name)) else {
            continue;
        };
        zip.start_file(format!("{name}.json"), opts)
            .map_err(|e| e.to_string())?;
        zip.write_all(&bytes).map_err(|e| e.to_string())?;
        count += 1;
    }
    zip.start_file("profiles_order.json", opts)
        .map_err(|e| e.to_string())?;
    zip.write_all(
        serde_json::to_string_pretty(&order)
            .unwrap_or_default()
            .as_bytes(),
    )
    .map_err(|e| e.to_string())?;
    zip.finish().map_err(|e| e.to_string())?;
    Ok(count)
}

struct Parsed {
    profiles: Vec<(String, Value)>,
    order: Option<Vec<String>>,
    skipped: usize,
}

fn parse_source(src: &Path) -> Result<Parsed, String> {
    let mut parsed = Parsed {
        profiles: Vec::new(),
        order: None,
        skipped: 0,
    };

    if is_zip_path(src) {
        let file = File::open(src).map_err(|e| e.to_string())?;
        let mut archive =
            zip::ZipArchive::new(file).map_err(|_| "The ZIP archive is damaged.".to_string())?;
        for i in 0..archive.len() {
            let mut entry = archive.by_index(i).map_err(|e| e.to_string())?;
            if entry.is_dir() {
                continue;
            }
            // Only the file name is used, so paths inside the archive can never escape.
            let Some(file_name) = Path::new(entry.name())
                .file_name()
                .and_then(|n| n.to_str())
                .map(str::to_string)
            else {
                continue;
            };
            let mut text = String::new();
            if entry.read_to_string(&mut text).is_err() {
                parsed.skipped += 1;
                continue;
            }
            if file_name == "profiles_order.json" {
                parsed.order = serde_json::from_str(&text).ok();
                continue;
            }
            if !file_name.to_lowercase().ends_with(".json") {
                continue;
            }
            match serde_json::from_str::<Value>(&text) {
                Ok(v) if v.is_object() => {
                    let stem = file_name[..file_name.len() - 5].to_string();
                    parsed.profiles.push((stem, v));
                }
                _ => parsed.skipped += 1,
            }
        }
        return Ok(parsed);
    }

    if is_json_path(src) {
        let payload = storage::read_json(src)?;
        if let Some(profiles) = payload.get("profiles").and_then(Value::as_object) {
            parsed.order = payload
                .get("order")
                .and_then(|o| serde_json::from_value(o.clone()).ok());
            for (name, data) in profiles {
                if data.is_object() {
                    parsed.profiles.push((name.clone(), data.clone()));
                } else {
                    parsed.skipped += 1;
                }
            }
        } else if payload.get("tokens").is_some() {
            let name = auth::extract_from_value(&payload)
                .default_name()
                .or_else(|| src.file_stem().and_then(|s| s.to_str()).map(str::to_string))
                .unwrap_or_else(|| "account".into());
            parsed.profiles.push((name, payload));
        } else {
            return Err("Unknown JSON format. Expected a bundle with a \"profiles\" key or a single auth.json with \"tokens\".".into());
        }
        return Ok(parsed);
    }

    Err("Only .zip and .json files can be imported.".into())
}

#[derive(Serialize)]
pub struct ScanEntry {
    name: String,
    exists: bool,
}

/// Lists what an import would write, so the caller can ask about conflicts first.
pub fn scan(paths: &Paths, src: &Path) -> Result<Vec<ScanEntry>, String> {
    let parsed = parse_source(src)?;
    Ok(parsed
        .profiles
        .into_iter()
        .filter_map(|(name, _)| storage::sanitize_name(&name).ok())
        .map(|name| ScanEntry {
            exists: paths.profile(&name).exists(),
            name,
        })
        .collect())
}

#[derive(Serialize, Default)]
pub struct ImportResult {
    imported: usize,
    overwritten: usize,
    skipped: usize,
}

/// Writes every profile in `src`; existing ones only when listed in `overwrite`.
pub fn apply(paths: &Paths, src: &Path, overwrite: &[String]) -> Result<ImportResult, String> {
    let parsed = parse_source(src)?;
    let mut res = ImportResult {
        skipped: parsed.skipped,
        ..Default::default()
    };

    for (raw_name, data) in parsed.profiles {
        let Ok(name) = storage::sanitize_name(&raw_name) else {
            res.skipped += 1;
            continue;
        };
        let dest = paths.profile(&name);
        let exists = dest.exists();
        if exists && !overwrite.contains(&name) {
            res.skipped += 1;
            continue;
        }
        if storage::write_json(&dest, &data).is_err() {
            res.skipped += 1;
            continue;
        }
        res.imported += 1;
        if exists {
            res.overwritten += 1;
        }
    }

    match parsed.order {
        Some(order) => {
            let existing = paths.ordered_profiles();
            let mut merged: Vec<String> =
                order.into_iter().filter(|n| existing.contains(n)).collect();
            merged.extend(
                existing
                    .into_iter()
                    .filter(|n| !merged.contains(n))
                    .collect::<Vec<_>>(),
            );
            paths.write_order(&merged)?;
        }
        None => paths.sync_order()?,
    }
    Ok(res)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zip_and_json_round_trip() {
        let root = std::env::temp_dir().join(format!("cs-bundle-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let a = Paths::under(root.join("a"));
        a.ensure();
        for n in ["one", "two"] {
            storage::write_json(&a.profile(n), &json!({ "tokens": { "access_token": n } }))
                .unwrap();
        }
        a.write_order(&["two".into(), "one".into()]).unwrap();

        for ext in ["zip", "json"] {
            let file = root.join(format!("out.{ext}"));
            assert_eq!(export_all(&a, &file).unwrap(), 2);

            let b = Paths::under(root.join(format!("b-{ext}")));
            b.ensure();
            storage::write_json(&b.profile("one"), &json!({})).unwrap();
            let scanned = scan(&b, &file).unwrap();
            assert_eq!(scanned.iter().filter(|e| e.exists).count(), 1);

            let r = apply(&b, &file, &[]).unwrap();
            assert_eq!((r.imported, r.skipped), (1, 1));
            assert_eq!(b.ordered_profiles(), vec!["two", "one"]);

            let r = apply(&b, &file, &["one".into()]).unwrap();
            assert_eq!(r.overwritten, 1);
        }
        let _ = std::fs::remove_dir_all(&root);
    }
}
