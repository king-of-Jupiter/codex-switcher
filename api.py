import base64
import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ API И JWT =================
def decode_jwt_payload(token_str: str) -> dict:
    try:
        parts = token_str.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(
            base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode(
                "utf-8"
            )
        )
    except Exception:
        return {}


def extract_auth_info_from_dict(data: dict) -> dict:
    info = {
        "email": "—",
        "name": "",
        "plan": "FREE",
        "expires": "—",
        "account_id": "",
        "is_valid": True,
    }
    info["account_id"] = data.get("account_id") or data.get(
        "tokens", {}
    ).get("account_id", "")

    meta = data.get("_meta", {})
    if isinstance(meta, dict):
        if meta.get("email"):
            info["email"] = meta["email"]
        if meta.get("plan_type"):
            info["plan"] = meta["plan_type"].upper()

    tokens = data.get("tokens", {})
    jwt_payload = {}
    if isinstance(tokens, dict):
        if tokens.get("id_token"):
            jwt_payload.update(decode_jwt_payload(tokens["id_token"]))
        if tokens.get("access_token"):
            acc_jwt = decode_jwt_payload(tokens["access_token"])
            for k, v in acc_jwt.items():
                if k not in jwt_payload or not jwt_payload[k]:
                    jwt_payload[k] = v

    if not info["account_id"]:
        auth_claim = jwt_payload.get("https://api.openai.com/auth", {})
        if isinstance(auth_claim, dict):
            info["account_id"] = auth_claim.get("chatgpt_account_id", "")

    if info["email"] == "—":
        info["email"] = (
            jwt_payload.get("email")
            or jwt_payload.get("https://api.openai.com/profile", {}).get(
                "email"
            )
            or "—"
        )

    info["name"] = (
        jwt_payload.get("name")
        or jwt_payload.get("https://api.openai.com/profile", {}).get("name")
        or ""
    )

    auth_data = jwt_payload.get("https://api.openai.com/auth", {})
    if isinstance(auth_data, dict):
        plan = auth_data.get("chatgpt_plan_type")
        if plan:
            info["plan"] = plan.upper()
        until = auth_data.get("chatgpt_subscription_active_until")
        if until:
            info["expires"] = until.split("T")[0]

    return info


def extract_auth_info(filepath: Path) -> dict:
    if not filepath.exists():
        return {
            "email": "—",
            "name": "",
            "plan": "FREE",
            "expires": "—",
            "account_id": "",
            "is_valid": False,
        }
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return extract_auth_info_from_dict(data)
    except Exception:
        return {
            "email": "—",
            "name": "",
            "plan": "FREE",
            "expires": "—",
            "account_id": "",
            "is_valid": False,
        }


def refresh_openai_token(auth_filepath: Path) -> bool:
    try:
        with open(auth_filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        refresh_token = data.get("tokens", {}).get("refresh_token")
        if not refresh_token:
            return False

        payload = json.dumps(
            {
                "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        ).encode("utf-8")

        cmd = [
            "curl.exe",
            "-s",
            "-X",
            "POST",
            "https://auth.openai.com/oauth/token",
            "-H",
            "Content-Type: application/json",
            "-H",
            "User-Agent: Codex Desktop",
            "-d",
            payload.decode("utf-8"),
        ]
        startupinfo = (
            subprocess.STARTUPINFO() if sys.platform == "win32" else None
        )
        if startupinfo:
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            timeout=10,
        )
        res_data = json.loads(r.stdout.strip())

        if "access_token" in res_data:
            data["tokens"]["access_token"] = res_data["access_token"]
            if "refresh_token" in res_data:
                data["tokens"]["refresh_token"] = res_data["refresh_token"]
            if "id_token" in res_data:
                data["tokens"]["id_token"] = res_data["id_token"]
            data["last_refresh"] = datetime.utcnow().isoformat() + "Z"

            with open(auth_filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
    except Exception:
        pass
    return False


def _curl_get(url: str, token: str, account_id: str) -> dict:
    cmd = [
        "curl.exe",
        "-s",
        "-X",
        "GET",
        url,
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "-H",
        "Accept: application/json",
        "-H",
        "Origin: https://chatgpt.com",
        "-H",
        "Referer: https://chatgpt.com/",
    ]
    if account_id:
        cmd.extend(["-H", f"chatgpt-account-id: {account_id}"])

    startupinfo = subprocess.STARTUPINFO() if sys.platform == "win32" else None
    if startupinfo:
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        startupinfo=startupinfo,
        timeout=10,
    )
    raw = res.stdout.strip()
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return {"error": raw[:250]}
    return {"error": res.stderr.strip() or "Empty response"}


def fetch_api_usage_raw(auth_filepath: Path) -> dict:
    if not auth_filepath.exists():
        return {"error": "Файл auth.json не найден"}

    try:
        with open(auth_filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        tokens = data.get("tokens", {})
        access_token = tokens.get("access_token")

        info = extract_auth_info(auth_filepath)
        account_id = info.get("account_id", "")

        if not access_token:
            return {"error": "Отсутствует access_token"}

        endpoints = [
            "https://chatgpt.com/backend-api/wham/usage",
            "https://chatgpt.com/backend-api/codex/usage",
        ]

        def _try_request(tok: str):
            if sys.platform == "win32" or shutil.which("curl"):
                for url in endpoints:
                    res = _curl_get(url, tok, account_id)
                    if (
                        "error" not in res
                        and ("rate_limit" in res or "plan_type" in res)
                    ):
                        return res

            headers = {
                "Authorization": f"Bearer {tok}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Origin": "https://chatgpt.com",
                "Referer": "https://chatgpt.com/",
            }
            if account_id:
                headers["chatgpt-account-id"] = account_id

            for url in endpoints:
                try:
                    req_obj = urllib.request.Request(
                        url, headers=headers, method="GET"
                    )
                    with urllib.request.urlopen(req_obj, timeout=8) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                except Exception:
                    continue

            return {"error": "HTTP 403: Forbidden (Cloudflare WAF / Token Expired)"}

        res_data = _try_request(access_token)

        if "error" in res_data and (
            "403" in str(res_data["error"]) or "401" in str(res_data["error"])
        ):
            if refresh_openai_token(auth_filepath):
                with open(auth_filepath, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                new_token = new_data.get("tokens", {}).get("access_token")
                return _try_request(new_token)

        return res_data

    except Exception as e:
        return {"error": str(e)}


def parse_dynamic_usage(raw_data: dict) -> dict:
    if "error" in raw_data:
        return {"error": raw_data["error"], "raw": raw_data}

    parsed = {
        "email": raw_data.get("email", ""),
        "plan_type": raw_data.get("plan_type", "—").upper(),
        "limit_reached": False,
        "credits": raw_data.get("credits", {}).get("balance", "0"),
        "reset_tickets": 0,
        "applicable_tickets": 0,
        "windows": [],
        "raw": raw_data,
    }

    reset_block = raw_data.get("rate_limit_reset_credits") or raw_data.get(
        "resets"
    )
    if isinstance(reset_block, dict):
        parsed["reset_tickets"] = reset_block.get("available_count", 0)
        parsed["applicable_tickets"] = reset_block.get(
            "applicable_available_count", 0
        )
    elif "available_resets" in raw_data:
        parsed["reset_tickets"] = raw_data["available_resets"]

    def _parse_window_obj(w_dict, default_title="Лимит"):
        if not isinstance(w_dict, dict):
            return None
        sec = w_dict.get("limit_window_seconds", 0)
        used = w_dict.get("used_percent", 0)
        left = max(0, 100 - used)
        reset_at = w_dict.get("reset_at")
        reset_after = w_dict.get("reset_after_seconds")

        if sec <= 0:
            title = default_title
        elif sec <= 18000:
            title = f"{default_title} (Сессия {round(sec/3600, 1)}ч)"
        elif sec <= 86400:
            title = f"{default_title} (24ч)"
        elif sec == 604800:
            title = f"{default_title} (7д)"
        else:
            title = f"{default_title} ({round(sec/86400)}д)"

        reset_str = "—"
        if reset_at:
            try:
                reset_str = datetime.fromtimestamp(reset_at).strftime(
                    "%d.%m %H:%M"
                )
            except Exception:
                pass
        elif reset_after is not None:
            hrs = reset_after // 3600
            mins = (reset_after % 3600) // 60
            reset_str = f"через {hrs}ч {mins}м"

        return {
            "title": title,
            "used": used,
            "left": left,
            "reset_str": reset_str,
        }

    rate_limit = raw_data.get("rate_limit", {})
    if isinstance(rate_limit, dict):
        parsed["limit_reached"] = rate_limit.get("limit_reached", False)
        for key in ["primary_window", "secondary_window"]:
            w_obj = rate_limit.get(key)
            if w_obj:
                res = _parse_window_obj(
                    w_obj,
                    (
                        "Основной лимит"
                        if key == "primary_window"
                        else "Доп. окно"
                    ),
                )
                if res:
                    parsed["windows"].append(res)

    return parsed
