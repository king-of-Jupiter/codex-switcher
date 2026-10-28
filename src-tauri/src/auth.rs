//! Reading account details out of an auth.json: `_meta`, the id/access JWTs.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::Serialize;
use serde_json::{Map, Value};
use std::path::Path;

#[derive(Debug, Clone, Serialize)]
pub struct AuthInfo {
    pub email: String,
    pub name: String,
    pub plan: String,
    pub expires: String,
    pub account_id: String,
    pub is_valid: bool,
}

impl AuthInfo {
    fn empty(is_valid: bool) -> Self {
        Self {
            email: "—".into(),
            name: String::new(),
            plan: "FREE".into(),
            expires: "—".into(),
            account_id: String::new(),
            is_valid,
        }
    }

    /// The part of the email before `@`, used as a default profile name.
    pub fn default_name(&self) -> Option<String> {
        if self.email == "—" {
            return None;
        }
        self.email.split('@').next().map(str::to_string)
    }
}

pub fn decode_jwt_payload(token: &str) -> Map<String, Value> {
    let Some(part) = token.split('.').nth(1) else {
        return Map::new();
    };
    URL_SAFE_NO_PAD
        .decode(part.trim_end_matches('='))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
        .and_then(|v| match v {
            Value::Object(m) => Some(m),
            _ => None,
        })
        .unwrap_or_default()
}

fn str_at<'a>(v: &'a Value, keys: &[&str]) -> Option<&'a str> {
    let mut cur = v;
    for k in keys {
        cur = cur.get(k)?;
    }
    cur.as_str().filter(|s| !s.is_empty())
}

fn is_truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
        Value::Number(n) => n.as_f64() != Some(0.0),
    }
}

pub fn extract_from_value(data: &Value) -> AuthInfo {
    let mut info = AuthInfo::empty(true);

    if let Some(id) =
        str_at(data, &["account_id"]).or_else(|| str_at(data, &["tokens", "account_id"]))
    {
        info.account_id = id.to_string();
    }

    if let Some(email) = str_at(data, &["_meta", "email"]) {
        info.email = email.to_string();
    }
    if let Some(plan) = str_at(data, &["_meta", "plan_type"]) {
        info.plan = plan.to_uppercase();
    }

    // id_token claims win; access_token fills the gaps.
    let mut jwt = Map::new();
    if let Some(tok) = str_at(data, &["tokens", "id_token"]) {
        jwt.extend(decode_jwt_payload(tok));
    }
    if let Some(tok) = str_at(data, &["tokens", "access_token"]) {
        for (k, v) in decode_jwt_payload(tok) {
            if !jwt.get(&k).map(is_truthy).unwrap_or(false) {
                jwt.insert(k, v);
            }
        }
    }
    let jwt = Value::Object(jwt);

    if info.account_id.is_empty() {
        if let Some(id) = str_at(&jwt, &["https://api.openai.com/auth", "chatgpt_account_id"]) {
            info.account_id = id.to_string();
        }
    }

    if info.email == "—" {
        if let Some(email) = str_at(&jwt, &["email"])
            .or_else(|| str_at(&jwt, &["https://api.openai.com/profile", "email"]))
        {
            info.email = email.to_string();
        }
    }

    info.name = str_at(&jwt, &["name"])
        .or_else(|| str_at(&jwt, &["https://api.openai.com/profile", "name"]))
        .unwrap_or_default()
        .to_string();

    if let Some(plan) = str_at(&jwt, &["https://api.openai.com/auth", "chatgpt_plan_type"]) {
        info.plan = plan.to_uppercase();
    }
    if let Some(until) = str_at(
        &jwt,
        &[
            "https://api.openai.com/auth",
            "chatgpt_subscription_active_until",
        ],
    ) {
        info.expires = until.split('T').next().unwrap_or(until).to_string();
    }

    info
}

pub fn extract_from_file(path: &Path) -> AuthInfo {
    std::fs::read(path)
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
        .map(|v| extract_from_value(&v))
        .unwrap_or_else(|| AuthInfo::empty(false))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn jwt(claims: Value) -> String {
        format!("x.{}.y", URL_SAFE_NO_PAD.encode(claims.to_string()))
    }

    #[test]
    fn reads_claims_from_tokens() {
        let data = serde_json::json!({
            "tokens": {
                "id_token": jwt(serde_json::json!({
                    "email": "a@b.c",
                    "https://api.openai.com/auth": {
                        "chatgpt_plan_type": "plus",
                        "chatgpt_account_id": "acc-1",
                        "chatgpt_subscription_active_until": "2026-12-01T00:00:00Z"
                    }
                }))
            }
        });
        let info = extract_from_value(&data);
        assert_eq!(info.email, "a@b.c");
        assert_eq!(info.plan, "PLUS");
        assert_eq!(info.account_id, "acc-1");
        assert_eq!(info.expires, "2026-12-01");
        assert_eq!(info.default_name().as_deref(), Some("a"));
    }

    #[test]
    fn bad_token_is_empty() {
        assert!(decode_jwt_payload("nope").is_empty());
        assert!(decode_jwt_payload("a.!!!.b").is_empty());
    }
}
