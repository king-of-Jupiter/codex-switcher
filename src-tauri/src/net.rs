//! Usage requests against chatgpt.com and token refresh against auth.openai.com.
//!
//! The system `curl` is tried first: its TLS handshake gets through Cloudflare where
//! other clients are sometimes challenged. `ureq` is the fallback when curl is absent
//! or every endpoint failed through it.

use crate::auth;
use crate::storage::{self, Paths};
use serde_json::{json, Value};
use std::path::Path;
use std::process::Command;
use std::sync::OnceLock;
use std::time::Duration;

const USAGE_ENDPOINTS: [&str; 2] = [
    "https://chatgpt.com/backend-api/wham/usage",
    "https://chatgpt.com/backend-api/codex/usage",
];
const TOKEN_URL: &str = "https://auth.openai.com/oauth/token";
const CLIENT_ID: &str = "app_EMoamEEZ73f0CkXaXp7hrann";
const BROWSER_UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";
const TIMEOUT: Duration = Duration::from_secs(10);

fn curl_bin() -> Option<&'static str> {
    static CURL: OnceLock<Option<&'static str>> = OnceLock::new();
    *CURL.get_or_init(|| {
        let bin = if cfg!(windows) { "curl.exe" } else { "curl" };
        hidden(Command::new(bin).arg("--version"))
            .output()
            .ok()
            .filter(|o| o.status.success())
            .map(|_| bin)
    })
}

/// Keeps child processes from flashing a console window on Windows.
pub fn hidden(cmd: &mut Command) -> &mut Command {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

struct Request<'a> {
    method: &'a str,
    url: &'a str,
    headers: Vec<(&'a str, String)>,
    body: Option<String>,
}

fn parse_body(status: u16, body: &str) -> Result<Value, String> {
    let snippet: String = body.trim().chars().take(250).collect();
    if !(200..300).contains(&status) {
        return Err(format!("HTTP {status}: {snippet}"));
    }
    serde_json::from_str(body.trim())
        .map_err(|_| format!("HTTP {status}: unexpected response {snippet}"))
}

fn send_curl(bin: &str, req: &Request) -> Result<Value, String> {
    let mut cmd = Command::new(bin);
    cmd.args([
        "-s",
        "-m",
        "10",
        "-X",
        req.method,
        req.url,
        "-w",
        "\n%{http_code}",
    ]);
    for (k, v) in &req.headers {
        cmd.arg("-H").arg(format!("{k}: {v}"));
    }
    if let Some(body) = &req.body {
        cmd.arg("-d").arg(body);
    }
    let out = hidden(&mut cmd).output().map_err(|e| e.to_string())?;
    let text = String::from_utf8_lossy(&out.stdout);
    let (body, code) = text.rsplit_once('\n').unwrap_or(("", text.as_ref()));
    let status: u16 = code.trim().parse().unwrap_or(0);
    if status == 0 {
        let err = String::from_utf8_lossy(&out.stderr).trim().to_string();
        return Err(if err.is_empty() {
            "No response (network error)".into()
        } else {
            err
        });
    }
    parse_body(status, body)
}

fn send_ureq(req: &Request) -> Result<Value, String> {
    let agent = ureq::AgentBuilder::new().timeout(TIMEOUT).build();
    let mut r = agent.request(req.method, req.url);
    for (k, v) in &req.headers {
        r = r.set(k, v);
    }
    let result = match &req.body {
        Some(body) => r.send_string(body),
        None => r.call(),
    };
    match result {
        Ok(resp) => {
            let status = resp.status();
            let body = resp.into_string().map_err(|e| e.to_string())?;
            parse_body(status, &body)
        }
        Err(ureq::Error::Status(status, resp)) => {
            parse_body(status, &resp.into_string().unwrap_or_default())
        }
        Err(e) => Err(e.to_string()),
    }
}

fn usage_request<'a>(url: &'a str, token: &str, account_id: &str) -> Request<'a> {
    let mut headers = vec![
        ("Authorization", format!("Bearer {token}")),
        ("User-Agent", BROWSER_UA.to_string()),
        ("Accept", "application/json".to_string()),
        ("Origin", "https://chatgpt.com".to_string()),
        ("Referer", "https://chatgpt.com/".to_string()),
    ];
    if !account_id.is_empty() {
        headers.push(("chatgpt-account-id", account_id.to_string()));
    }
    Request {
        method: "GET",
        url,
        headers,
        body: None,
    }
}

fn looks_like_usage(v: &Value) -> bool {
    v.get("rate_limit").is_some() || v.get("plan_type").is_some()
}

type Sender = Box<dyn Fn(&Request) -> Result<Value, String>>;

fn try_usage(token: &str, account_id: &str) -> Result<Value, String> {
    let mut last_err = String::from("No usage endpoint answered");
    let mut senders: Vec<Sender> = Vec::new();
    if let Some(bin) = curl_bin() {
        senders.push(Box::new(move |r| send_curl(bin, r)));
    }
    senders.push(Box::new(send_ureq));

    for send in &senders {
        for url in USAGE_ENDPOINTS {
            match send(&usage_request(url, token, account_id)) {
                Ok(v) if looks_like_usage(&v) => return Ok(v),
                Ok(_) => last_err = format!("{url} answered without usage data"),
                Err(e) => last_err = e,
            }
        }
    }
    Err(last_err)
}

/// Exchanges the refresh token in `path` for new tokens and writes them back.
/// Every other auth file that held the same bytes (auth.json and its saved
/// profile copy) gets the new tokens too, since the old refresh token stops working.
fn refresh_token(path: &Path, paths: &Paths) -> bool {
    let Ok(old_bytes) = std::fs::read(path) else {
        return false;
    };
    let Ok(mut data) = serde_json::from_slice::<Value>(&old_bytes) else {
        return false;
    };
    let Some(refresh) = data
        .pointer("/tokens/refresh_token")
        .and_then(Value::as_str)
        .map(str::to_string)
    else {
        return false;
    };

    let req = Request {
        method: "POST",
        url: TOKEN_URL,
        headers: vec![
            ("Content-Type", "application/json".into()),
            ("User-Agent", "Codex Desktop".into()),
        ],
        body: Some(
            json!({ "client_id": CLIENT_ID, "grant_type": "refresh_token", "refresh_token": refresh }).to_string(),
        ),
    };
    let res = match curl_bin() {
        Some(bin) => send_curl(bin, &req).or_else(|_| send_ureq(&req)),
        None => send_ureq(&req),
    };
    let Ok(res) = res else { return false };
    let Some(access) = res.get("access_token") else {
        return false;
    };

    let Some(tokens) = data.get_mut("tokens").and_then(Value::as_object_mut) else {
        return false;
    };
    tokens.insert("access_token".into(), access.clone());
    for key in ["refresh_token", "id_token"] {
        if let Some(v) = res.get(key) {
            tokens.insert(key.into(), v.clone());
        }
    }
    if let Some(obj) = data.as_object_mut() {
        let now = chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Micros, true);
        obj.insert("last_refresh".into(), Value::String(now));
    }

    let mut twins = vec![paths.auth_file.clone()];
    twins.extend(paths.ordered_profiles().iter().map(|n| paths.profile(n)));
    for twin in twins.iter().filter(|p| p.as_path() != path) {
        if std::fs::read(twin).map(|b| b == old_bytes).unwrap_or(false) {
            let _ = storage::write_json(twin, &data);
        }
    }
    storage::write_json(path, &data).is_ok()
}

/// Raw usage JSON for one auth file, or `{"error": "..."}`.
pub fn fetch_usage(path: &Path, paths: &Paths) -> Value {
    if !path.exists() {
        return json!({ "error": "auth.json not found" });
    }
    let data = match storage::read_json(path) {
        Ok(d) => d,
        Err(e) => return json!({ "error": e }),
    };
    let Some(token) = data.pointer("/tokens/access_token").and_then(Value::as_str) else {
        return json!({ "error": "No access_token in this file" });
    };
    let account_id = auth::extract_from_value(&data).account_id;

    match try_usage(token, &account_id) {
        Ok(v) => v,
        Err(e) if e.contains("401") || e.contains("403") => {
            if refresh_token(path, paths) {
                let fresh = storage::read_json(path).ok();
                if let Some(tok) = fresh
                    .as_ref()
                    .and_then(|d| d.pointer("/tokens/access_token"))
                    .and_then(Value::as_str)
                {
                    return try_usage(tok, &account_id).unwrap_or_else(|e| json!({ "error": e }));
                }
            }
            json!({ "error": e })
        }
        Err(e) => json!({ "error": e }),
    }
}
