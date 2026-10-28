// Turns the raw /usage response into the windows the UI shows.

export interface UsageWindow {
  key: "primary" | "secondary";
  title: string;
  seconds: number;
  used: number;
  left: number;
  resetAt: Date | null;
  resetText: string;
}

export interface Usage {
  plan: string;
  limitReached: boolean;
  credits: string;
  resetTickets: number;
  applicableTickets: number;
  windows: UsageWindow[];
}

export type UsageResult = { ok: true; usage: Usage; raw: unknown } | { ok: false; error: string; raw: unknown };

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown, d = 0) => (typeof v === "number" && Number.isFinite(v) ? v : d);

export function windowTitle(seconds: number): string {
  if (seconds <= 0) return "Limit";
  if (seconds <= 18000) {
    const h = Math.round((seconds / 3600) * 10) / 10;
    return `${h}-hour window`;
  }
  if (seconds <= 86400) return "24-hour window";
  return `${Math.round(seconds / 86400)}-day window`;
}

const dateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function formatReset(at: Date | null, afterSeconds: number | null): string {
  if (at) return dateFmt.format(at);
  if (afterSeconds !== null) {
    const h = Math.floor(afterSeconds / 3600);
    const m = Math.floor((afterSeconds % 3600) / 60);
    return `in ${h}h ${m}m`;
  }
  return "—";
}

function parseWindow(key: UsageWindow["key"], w: unknown): UsageWindow | null {
  if (!isObj(w)) return null;
  const seconds = num(w.limit_window_seconds);
  const used = num(w.used_percent);
  const resetAt = typeof w.reset_at === "number" ? new Date(w.reset_at * 1000) : null;
  const after = typeof w.reset_after_seconds === "number" ? w.reset_after_seconds : null;
  return {
    key,
    title: windowTitle(seconds),
    seconds,
    used,
    left: Math.max(0, 100 - used),
    resetAt,
    resetText: formatReset(resetAt, after),
  };
}

export function parseUsage(raw: unknown): UsageResult {
  if (!isObj(raw)) return { ok: false, error: "Empty response", raw };
  if ("error" in raw) return { ok: false, error: String(raw.error), raw };

  const usage: Usage = {
    plan: String(raw.plan_type ?? "—").toUpperCase(),
    limitReached: false,
    credits: isObj(raw.credits) ? String(raw.credits.balance ?? "0") : "0",
    resetTickets: 0,
    applicableTickets: 0,
    windows: [],
  };

  const resets = raw.rate_limit_reset_credits ?? raw.resets;
  if (isObj(resets)) {
    usage.resetTickets = num(resets.available_count);
    usage.applicableTickets = num(resets.applicable_available_count);
  } else if ("available_resets" in raw) {
    usage.resetTickets = num(raw.available_resets);
  }

  if (isObj(raw.rate_limit)) {
    usage.limitReached = raw.rate_limit.limit_reached === true;
    const primary = parseWindow("primary", raw.rate_limit.primary_window);
    const secondary = parseWindow("secondary", raw.rate_limit.secondary_window);
    for (const w of [primary, secondary]) if (w) usage.windows.push(w);
  }
  return { ok: true, usage, raw };
}

/** The five-hour window, by its length. */
export function fiveHour(u: Usage): UsageWindow | undefined {
  return u.windows.find((w) => w.seconds === 18000);
}

/** The weekly window: a 7-day window, else the primary one when it is not the five-hour one. */
export function weekly(u: Usage): UsageWindow | undefined {
  return u.windows.find((w) => w.seconds === 604800) ?? u.windows.find((w) => w.key === "primary" && w.seconds !== 18000);
}
