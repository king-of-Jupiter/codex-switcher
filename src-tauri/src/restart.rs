//! Restarting ChatGPT / Codex so it picks up the new auth.json.

#[cfg(windows)]
use crate::net::hidden;
use std::process::Command;

#[cfg(windows)]
pub fn restart_codex() {
    for image in [
        "ChatGPT.exe",
        "Codex.exe",
        "OpenAI.Codex.exe",
        "OpenAI.Codex",
    ] {
        let _ = hidden(Command::new("taskkill").args(["/F", "/IM", image])).output();
    }
    std::thread::sleep(std::time::Duration::from_millis(800));

    let script = "$app = Get-StartApps | Where-Object { \
        $_.AppID -like '*OpenAI.Codex*' -or $_.AppID -like '*2p2nqsd0c76g0*' -or $_.AppID -like '*ChatGPT*' \
        } | Select-Object -First 1; \
        if ($app) { Start-Process ('shell:AppsFolder\\' + $app.AppID) } \
        else { Start-Process 'shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App' }";
    let launched = hidden(Command::new("powershell").args([
        "-NoProfile",
        "-WindowStyle",
        "Hidden",
        "-Command",
        script,
    ]))
    .spawn();
    if launched.is_err() {
        let _ = Command::new("explorer.exe")
            .arg("shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App")
            .spawn();
    }
}

#[cfg(not(windows))]
fn is_running(app: &str) -> bool {
    Command::new("pgrep")
        .args(["-x", app])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Polls until `app` has exited or `timeout` passes; true when it is gone.
#[cfg(not(windows))]
fn wait_for_exit(app: &str, timeout: std::time::Duration) -> bool {
    let deadline = std::time::Instant::now() + timeout;
    while is_running(app) {
        if std::time::Instant::now() >= deadline {
            return false;
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    true
}

/// Matches process names exactly (`-x`) so this app, "Codex Switcher", is never caught.
/// Each app is asked to quit, given up to 5 s, then killed; on macOS the ones that were
/// running are reopened only once they are really gone, so `open` never lands on a
/// window that is still closing.
#[cfg(not(windows))]
pub fn restart_codex() {
    use std::time::Duration;

    let running: Vec<&str> = ["ChatGPT", "Codex"]
        .into_iter()
        .filter(|app| is_running(app))
        .collect();
    for app in &running {
        let _ = Command::new("pkill").args(["-x", app]).status();
    }
    for app in &running {
        if !wait_for_exit(app, Duration::from_secs(5)) {
            let _ = Command::new("pkill").args(["-9", "-x", app]).status();
            wait_for_exit(app, Duration::from_secs(2));
        }
    }

    #[cfg(target_os = "macos")]
    for app in &running {
        let _ = Command::new("open").args(["-a", app]).spawn();
    }
}
