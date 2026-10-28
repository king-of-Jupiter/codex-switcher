// Dev-only stand-in for the Rust side, so the UI can be opened in a plain browser
// (`npm run dev`, then http://localhost:1420). Never bundled into the app.
import { mockIPC } from "@tauri-apps/api/mocks";

const info = (email: string, plan: string) => ({ email, name: "", plan, expires: "2026-12-01", account_id: "x", is_valid: true });
let profiles = ["work", "personal", "team-plus", "spare"];
const emails: Record<string, [string, string]> = {
  work: ["dev@example.com", "PRO"],
  personal: ["me@example.com", "PLUS"],
  "team-plus": ["team@example.com", "TEAM"],
  spare: ["spare@example.com", "FREE"],
};
const now = Math.floor(Date.now() / 1000);
const usage = (u5: number, u7: number) => ({
  plan_type: "pro",
  credits: { balance: "0" },
  rate_limit_reset_credits: { available_count: 2, applicable_available_count: 1 },
  rate_limit: {
    limit_reached: false,
    primary_window: { limit_window_seconds: 18000, used_percent: u5, reset_at: now + 7200 },
    secondary_window: { limit_window_seconds: 604800, used_percent: u7, reset_at: now + 3 * 86400 },
  },
});

mockIPC(async (cmd, args) => {
  const a = (args ?? {}) as Record<string, unknown>;
  await new Promise((r) => setTimeout(r, cmd === "fetch_usage" ? 300 : 10));
  switch (cmd) {
    case "get_state":
      return {
        auth_exists: true,
        active_profile: "work",
        active_info: info("dev@example.com", "PRO"),
        profiles_dir: "~/.codex/codex-switcher/profiles",
        profiles: profiles.map((n) => ({ name: n, info: info(...(emails[n] ?? ["—", "FREE"])), active: n === "work" })),
      };
    case "fetch_usage":
      if (a.name === "spare") return { error: "HTTP 401: token expired" };
      return usage(a.name === "personal" ? 92 : 38, a.name === "team-plus" ? 75 : 21);
    case "save_order":
      profiles = a.order as string[];
      return null;
    case "inspect_auth_text":
      return info("pasted@example.com", "PLUS");
    default:
      return null;
  }
});
