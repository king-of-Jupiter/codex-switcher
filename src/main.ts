import "@fontsource/host-grotesk/400.css";
import "@fontsource/host-grotesk/500.css";
import "@fontsource/atkinson-hyperlegible-mono/400.css";
import "@fontsource/atkinson-hyperlegible-mono/500.css";
import "./styles/app.css";

import { open, save } from "@tauri-apps/plugin-dialog";
import { readText, writeText } from "@tauri-apps/plugin-clipboard-manager";
import { api, defaultName, EXISTS, type AppState, type AuthInfo } from "./api";
import { chooseOverwrites, confirm, promptText, toast } from "./dialogs";
import { fiveHour, parseUsage, weekly, type UsageResult, type UsageWindow } from "./usage";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

const ui = {
  checkBtn: $<HTMLButtonElement>("btn-check"),
  checkStatus: $("check-status"),
  body: $<HTMLTableSectionElement>("profiles-body"),
  empty: $("profiles-empty"),
  count: $("profiles-count"),
  activate: $<HTMLButtonElement>("btn-activate"),
  rename: $<HTMLButtonElement>("btn-rename"),
  remove: $<HTMLButtonElement>("btn-delete"),
  restart: $<HTMLInputElement>("opt-restart"),
  raw: $("raw-json"),
};

let state: AppState | null = null;
let selected: string | null = null;
let checking = false;
/** Last usage per saved profile; kept across refreshes so a reload never blanks the table. */
const usageByProfile = new Map<string, UsageResult>();
let activeUsage: UsageResult | null = null;

const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

// ---------- Settings ----------

try {
  const saved = localStorage.getItem("restart-on-switch");
  if (saved !== null) ui.restart.checked = saved === "1";
} catch {
  /* storage unavailable: keep the default */
}
ui.restart.addEventListener("change", () => {
  try {
    localStorage.setItem("restart-on-switch", ui.restart.checked ? "1" : "0");
  } catch {
    /* ignore */
  }
});

// ---------- Rendering ----------

function svgGrip(): SVGSVGElement {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 10 16");
  svg.setAttribute("width", "10");
  svg.setAttribute("height", "16");
  svg.setAttribute("aria-hidden", "true");
  for (const [cx, cy] of [[2, 3], [8, 3], [2, 8], [8, 8], [2, 13], [8, 13]]) {
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", String(cx));
    c.setAttribute("cy", String(cy));
    c.setAttribute("r", "1.4");
    svg.append(c);
  }
  return svg;
}

function quotaCell(w: UsageWindow | undefined, result: UsageResult | undefined, loading: boolean): HTMLTableCellElement {
  const td = document.createElement("td");
  td.className = "col-num";
  if (!result) {
    if (loading) {
      const s = document.createElement("span");
      s.className = "skeleton";
      s.setAttribute("aria-label", "Loading");
      td.append(s);
    } else td.textContent = "—";
    return td;
  }
  if (!result.ok || !w) {
    td.textContent = "—";
    return td;
  }
  const wrap = document.createElement("span");
  wrap.className = "quota";
  const val = document.createElement("span");
  val.className = "measured";
  val.textContent = `${Math.round(w.left)}%`;
  const bar = document.createElement("span");
  bar.className = "meter meter--sm";
  bar.dataset.level = level(w.left);
  const fill = document.createElement("span");
  fill.style.transform = `scaleX(${w.left / 100})`;
  bar.append(fill);
  wrap.append(val, bar);
  td.title = `Resets ${w.resetText}`;
  td.append(wrap);
  return td;
}

function level(left: number): string {
  if (left <= 10) return "low";
  if (left <= 30) return "mid";
  return "ok";
}

function renderTable() {
  if (!state) return;
  const rows = state.profiles;
  ui.count.textContent = rows.length ? String(rows.length) : "";
  ui.empty.hidden = rows.length > 0;
  ui.body.parentElement!.hidden = rows.length === 0;

  if (selected && !rows.some((r) => r.name === selected)) selected = null;

  const frag = document.createDocumentFragment();
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.dataset.name = row.name;
    tr.tabIndex = row.name === selected || (!selected && row === rows[0]) ? 0 : -1;
    tr.setAttribute("aria-selected", String(row.name === selected));
    if (row.active) tr.classList.add("is-active");

    const grip = document.createElement("td");
    grip.className = "col-grip";
    const handle = document.createElement("button");
    handle.type = "button";
    handle.className = "grip";
    handle.tabIndex = -1;
    handle.setAttribute("aria-label", `Drag to reorder ${row.name}`);
    handle.append(svgGrip());
    grip.append(handle);

    const name = document.createElement("td");
    name.className = "col-name";
    name.textContent = row.name;

    const email = document.createElement("td");
    email.className = "col-email";
    email.textContent = row.info.email;

    const result = usageByProfile.get(row.name);
    const plan = document.createElement("td");
    plan.textContent = result?.ok && result.usage.plan !== "—" ? result.usage.plan : row.info.plan;
    plan.className = "col-plan";

    const u = result?.ok ? result.usage : undefined;
    const q5 = quotaCell(u && fiveHour(u), result, checking);
    const q7 = quotaCell(u && weekly(u), result, checking);

    const tickets = document.createElement("td");
    tickets.className = "col-num measured";
    tickets.textContent = u ? String(u.resetTickets) : "—";

    const status = document.createElement("td");
    status.className = "col-status";
    if (row.active) {
      const chip = document.createElement("span");
      chip.className = "chip chip--accent";
      chip.textContent = "Active";
      status.append(chip);
    } else if (result && !result.ok) {
      const err = document.createElement("span");
      err.className = "row-error";
      err.textContent = "No data";
      err.title = result.error;
      status.append(err);
    }

    tr.append(grip, name, email, plan, q5, q7, tickets, status);
    frag.append(tr);
  }
  ui.body.replaceChildren(frag);
  syncSelectionButtons();
}

function setReading(cell: HTMLElement, w: UsageWindow | undefined, note: string) {
  const reading = cell.querySelector<HTMLElement>("[data-reading]")!;
  const meter = cell.querySelector<HTMLElement>("[data-meter]")!;
  const fill = meter.firstElementChild as HTMLElement;
  const noteEl = cell.querySelector<HTMLElement>("[data-note]")!;
  if (w) {
    reading.innerHTML = "";
    reading.append(String(Math.round(w.left)));
    const unit = document.createElement("span");
    unit.className = "unit";
    unit.textContent = "% left";
    reading.append(unit);
    meter.dataset.level = level(w.left);
    fill.style.transform = `scaleX(${w.left / 100})`;
    noteEl.textContent = `Resets ${w.resetText}`;
    cell.querySelector(".label")!.textContent = w.title.charAt(0).toUpperCase() + w.title.slice(1);
  } else {
    reading.textContent = "—";
    delete meter.dataset.level;
    fill.style.transform = "scaleX(0)";
    noteEl.textContent = note;
  }
}

function renderActive() {
  if (!state) return;
  const info: AuthInfo = state.active_info;
  const name = state.active_profile ?? (state.auth_exists ? "Unsaved account" : "Signed out");
  $("active-name").textContent = name;
  $("active-email").textContent = state.auth_exists
    ? info.email
    : "No auth.json. Sign in to ChatGPT/Codex, then save the account here.";
  $("active-expires").textContent = state.auth_exists ? info.expires : "—";

  const u = activeUsage?.ok ? activeUsage.usage : undefined;
  $("active-plan").textContent = state.auth_exists ? (u && u.plan !== "—" ? u.plan : info.plan) : "—";

  const pending = checking && !activeUsage ? "Checking…" : "Waiting for the first check";
  const note = activeUsage && !activeUsage.ok ? "Unavailable" : u ? "Not reported for this plan" : pending;
  setReading(document.querySelector<HTMLElement>('[data-window="5h"]')!, u && fiveHour(u), note);
  setReading(document.querySelector<HTMLElement>('[data-window="7d"]')!, u && weekly(u), note);

  $("active-tickets").textContent = u ? String(u.resetTickets) : "—";
  $("active-credits").textContent = u ? `$${u.credits}` : "—";

  const err = $("active-error");
  if (activeUsage && !activeUsage.ok && state.auth_exists) {
    err.textContent = `Could not read usage: ${activeUsage.error}`;
    err.hidden = false;
  } else err.hidden = true;

  renderRaw();
}

function escapeHtml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderRaw() {
  if (!activeUsage) return;
  const json = JSON.stringify(activeUsage.raw, null, 2) ?? "null";
  ui.raw.innerHTML = escapeHtml(json).replace(
    /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/g,
    (m, str: string | undefined, colon: string | undefined, lit: string | undefined) => {
      if (str) return colon ? `<span class="j-key">${str}</span>${colon}` : `<span class="j-str">${str}</span>`;
      if (lit) return `<span class="j-lit">${m}</span>`;
      return `<span class="j-num">${m}</span>`;
    },
  );
}

function syncSelectionButtons() {
  const has = selected !== null;
  ui.activate.disabled = !has;
  ui.rename.disabled = !has;
  ui.remove.disabled = !has;
  for (const tr of ui.body.rows) {
    const on = tr.dataset.name === selected;
    tr.setAttribute("aria-selected", String(on));
  }
}

async function refresh() {
  try {
    state = await api.state();
  } catch (e) {
    toast(errorText(e), "error");
    return;
  }
  renderTable();
  renderActive();
}

// ---------- Usage checks ----------

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });

async function checkActive() {
  activeUsage = parseUsage(await api.usage(null));
  renderActive();
}

async function checkAll() {
  if (checking || !state) return;
  checking = true;
  ui.checkBtn.disabled = true;
  ui.checkBtn.setAttribute("aria-busy", "true");
  ui.checkStatus.textContent = "Checking active account";
  renderTable();
  renderActive();
  try {
    await checkActive();
    const names = state.profiles.map((p) => p.name);
    for (const [i, name] of names.entries()) {
      ui.checkStatus.textContent = `Checking ${i + 1} of ${names.length}`;
      usageByProfile.set(name, parseUsage(await api.usage(name)));
      renderTable();
      await sleep(200);
    }
    ui.checkStatus.textContent = `Checked at ${timeFmt.format(new Date())}`;
  } catch (e) {
    ui.checkStatus.textContent = "Check failed";
    toast(errorText(e), "error");
  } finally {
    checking = false;
    ui.checkBtn.disabled = false;
    ui.checkBtn.removeAttribute("aria-busy");
    // A refresh may have rewritten token files; re-read which profile is active.
    await refresh();
  }
}

// ---------- Actions ----------

/** Runs a save command, asking once before overwriting an existing profile. */
async function saveWithOverwrite(name: string, run: (overwrite: boolean) => Promise<string>): Promise<string | null> {
  try {
    return await run(false);
  } catch (e) {
    if (errorText(e) !== EXISTS) throw e;
    const ok = await confirm({
      title: "Overwrite profile?",
      body: `A profile named "${name}" already exists. Replace it with this one?`,
      ok: "Overwrite",
    });
    return ok ? run(true) : null;
  }
}

async function afterProfileAdded(name: string) {
  selected = name;
  await refresh();
  toast(`Saved profile "${name}".`);
  const result = parseUsage(await api.usage(name));
  usageByProfile.set(name, result);
  renderTable();
}

async function activateSelected() {
  if (!selected) return;
  const name = selected;
  try {
    await api.activate(name, ui.restart.checked);
    activeUsage = usageByProfile.get(name) ?? null;
    await refresh();
    toast(ui.restart.checked ? `Switched to "${name}". Restarting ChatGPT/Codex.` : `Switched to "${name}".`);
    void checkActive();
  } catch (e) {
    toast(errorText(e), "error");
  }
}

async function saveActive() {
  if (!state?.auth_exists) {
    toast("auth.json does not exist. Sign in to ChatGPT/Codex first.", "error");
    return;
  }
  const name = await promptText({ title: "Save the active account", value: defaultName(state.active_info) });
  if (!name) return;
  try {
    const saved = await saveWithOverwrite(name, (o) => api.saveActive(name, o));
    if (saved) await afterProfileAdded(saved);
  } catch (e) {
    toast(errorText(e), "error");
  }
}

async function importFile() {
  const path = await open({ title: "Select an auth.json", multiple: false, directory: false, filters: [{ name: "JSON", extensions: ["json"] }] });
  if (typeof path !== "string") return;
  const info = await api.inspectFile(path);
  const stem = path.split(/[\\/]/).pop()?.replace(/\.json$/i, "") || "account";
  const name = await promptText({ title: "Import a profile", value: defaultName(info, stem) });
  if (!name) return;
  try {
    const saved = await saveWithOverwrite(name, (o) => api.importFile(path, name, o));
    if (saved) await afterProfileAdded(saved);
  } catch (e) {
    toast(errorText(e), "error");
  }
}

async function renameSelected() {
  if (!selected) return;
  const old = selected;
  const next = await promptText({ title: "Rename profile", label: "New name", value: old, ok: "Rename" });
  if (!next || next === old) return;
  try {
    const saved = await api.rename(old, next);
    const cached = usageByProfile.get(old);
    if (cached) {
      usageByProfile.delete(old);
      usageByProfile.set(saved, cached);
    }
    selected = saved;
    await refresh();
  } catch (e) {
    toast(errorText(e), "error");
  }
}

async function deleteSelected() {
  if (!selected) return;
  const name = selected;
  const ok = await confirm({ title: `Delete "${name}"?`, body: "The saved profile file is removed. The active auth.json is not touched.", ok: "Delete" });
  if (!ok) return;
  try {
    await api.remove(name);
    usageByProfile.delete(name);
    selected = null;
    await refresh();
  } catch (e) {
    toast(errorText(e), "error");
  }
}

async function newAccount() {
  const ok = await confirm({
    title: "Sign in to a new account?",
    body: "The current auth.json is deleted (a copy stays in auth.json.bak) and ChatGPT/Codex restarts so you can log in. Saved profiles are not touched. Afterwards, come back and choose Save active.",
    ok: "Reset and restart",
  });
  if (!ok) return;
  try {
    await api.newAccount();
    activeUsage = null;
    await refresh();
    toast("auth.json removed. Log in to the new account, then choose Save active.");
  } catch (e) {
    toast(errorText(e), "error");
  }
}

async function exportAll() {
  if (!state?.profiles.length) {
    toast("No saved profiles to export.", "error");
    return;
  }
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace("T", "_").slice(0, 15);
  const path = await save({
    title: "Export all profiles",
    defaultPath: `codex_profiles_${stamp}.zip`,
    filters: [
      { name: "ZIP archive", extensions: ["zip"] },
      { name: "JSON bundle", extensions: ["json"] },
    ],
  });
  if (!path) return;
  try {
    const n = await api.exportAll(path);
    toast(`Exported ${n} profiles to ${path}`);
  } catch (e) {
    toast(errorText(e), "error");
  }
}

async function importAll() {
  const path = await open({
    title: "Import all profiles",
    multiple: false,
    directory: false,
    filters: [{ name: "ZIP or JSON", extensions: ["zip", "json"] }],
  });
  if (typeof path !== "string") return;
  try {
    const entries = await api.importScan(path);
    const conflicts = entries.filter((e) => e.exists);
    const overwrite = conflicts.length ? await chooseOverwrites(conflicts) : [];
    if (overwrite === null) {
      toast("Import cancelled. Nothing was changed.");
      return;
    }
    const r = await api.importApply(path, overwrite);
    for (const name of overwrite) usageByProfile.delete(name);
    await refresh();
    toast(`Imported ${r.imported} (${r.overwritten} overwritten), skipped ${r.skipped}.`);
    void checkAll();
  } catch (e) {
    toast(errorText(e), "error");
  }
}

// ---------- Paste dialog ----------

const paste = {
  dlg: $<HTMLDialogElement>("dlg-paste"),
  text: $<HTMLTextAreaElement>("dlg-paste-text"),
  detect: $("dlg-paste-detect"),
  ok: $<HTMLButtonElement>("dlg-paste-ok"),
  info: null as AuthInfo | null,
};

let detectSeq = 0;
async function detectPasted() {
  const seq = ++detectSeq;
  const text = paste.text.value.trim();
  paste.info = null;
  paste.ok.disabled = true;
  delete paste.detect.dataset.tone;
  if (!text) {
    paste.detect.textContent = "Paste the JSON, and the account will be read from it.";
    return;
  }
  try {
    const info = await api.inspectText(text);
    if (seq !== detectSeq) return;
    paste.info = info;
    paste.ok.disabled = false;
    paste.detect.textContent = info.email !== "—" ? `Found ${info.email}, plan ${info.plan}.` : "Valid JSON, but no account email was found in it.";
  } catch (e) {
    if (seq !== detectSeq) return;
    paste.detect.dataset.tone = "error";
    paste.detect.textContent = errorText(e);
  }
}

paste.text.addEventListener("input", () => void detectPasted());
$("dlg-paste-clip").addEventListener("click", async () => {
  try {
    paste.text.value = await readText();
    void detectPasted();
  } catch {
    toast("The clipboard has no text.", "error");
  }
});

async function openPaste() {
  paste.text.value = "";
  paste.dlg.returnValue = "";
  void detectPasted();
  paste.dlg.showModal();
  paste.text.focus();
  await new Promise((r) => paste.dlg.addEventListener("close", r, { once: true }));
  if (paste.dlg.returnValue !== "ok" || !paste.info) return;
  const text = paste.text.value;
  const name = await promptText({ title: "Name the pasted profile", value: defaultName(paste.info) });
  if (!name) return;
  try {
    const saved = await saveWithOverwrite(name, (o) => api.saveText(name, text, o));
    if (saved) await afterProfileAdded(saved);
  } catch (e) {
    toast(errorText(e), "error");
  }
}

// ---------- Table interaction: select, keyboard, drag to reorder ----------

function select(name: string | null, focus = false) {
  selected = name;
  for (const tr of ui.body.rows) tr.tabIndex = tr.dataset.name === name ? 0 : -1;
  syncSelectionButtons();
  if (focus && name) ui.body.querySelector<HTMLElement>(`tr[data-name="${CSS.escape(name)}"]`)?.focus();
}

function currentOrder(): string[] {
  return [...ui.body.rows].map((tr) => tr.dataset.name!);
}

async function persistOrder() {
  const order = currentOrder();
  if (state) {
    const byName = new Map(state.profiles.map((p) => [p.name, p]));
    state.profiles = order.map((n) => byName.get(n)!).filter(Boolean);
  }
  try {
    await api.saveOrder(order);
  } catch (e) {
    toast(errorText(e), "error");
  }
}

ui.body.addEventListener("click", (e) => {
  const tr = (e.target as HTMLElement).closest("tr");
  if (tr?.dataset.name) select(tr.dataset.name);
});
ui.body.addEventListener("dblclick", (e) => {
  const tr = (e.target as HTMLElement).closest("tr");
  if (tr?.dataset.name && !(e.target as HTMLElement).closest(".grip")) {
    select(tr.dataset.name);
    void activateSelected();
  }
});

ui.body.addEventListener("keydown", (e) => {
  const tr = (e.target as HTMLElement).closest("tr");
  if (!tr?.dataset.name) return;
  const rows = [...ui.body.rows];
  const i = rows.indexOf(tr as HTMLTableRowElement);
  const move = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
  if (move && e.altKey) {
    const j = i + move;
    if (j < 0 || j >= rows.length) return;
    e.preventDefault();
    if (move > 0) rows[j].after(tr);
    else rows[j].before(tr);
    select(tr.dataset.name, true);
    void persistOrder();
  } else if (move) {
    e.preventDefault();
    const next = rows[Math.min(rows.length - 1, Math.max(0, i + move))];
    select(next.dataset.name!, true);
  } else if (e.key === "Home" || e.key === "End") {
    e.preventDefault();
    select((e.key === "Home" ? rows[0] : rows[rows.length - 1]).dataset.name!, true);
  } else if (e.key === "Enter") {
    e.preventDefault();
    select(tr.dataset.name);
    void activateSelected();
  } else if (e.key === " ") {
    e.preventDefault();
    select(tr.dataset.name);
  } else if (e.key === "F2") {
    e.preventDefault();
    select(tr.dataset.name);
    void renameSelected();
  } else if (e.key === "Delete") {
    e.preventDefault();
    select(tr.dataset.name);
    void deleteSelected();
  }
});

let dragRow: HTMLTableRowElement | null = null;

ui.body.addEventListener("pointerdown", (e) => {
  const handle = (e.target as HTMLElement).closest(".grip");
  if (!handle || e.button !== 0) return;
  dragRow = handle.closest("tr");
  if (!dragRow) return;
  e.preventDefault();
  handle.setPointerCapture(e.pointerId);
  dragRow.classList.add("is-dragging");
  select(dragRow.dataset.name!);
});

ui.body.addEventListener("pointermove", (e) => {
  if (!dragRow) return;
  for (const tr of ui.body.rows) {
    if (tr === dragRow) continue;
    const r = tr.getBoundingClientRect();
    if (e.clientY < r.top || e.clientY > r.bottom) continue;
    const below = e.clientY > r.top + r.height / 2;
    if (below && tr.nextElementSibling !== dragRow) tr.after(dragRow);
    else if (!below && tr.previousElementSibling !== dragRow) tr.before(dragRow);
    break;
  }
});

function endDrag() {
  if (!dragRow) return;
  dragRow.classList.remove("is-dragging");
  dragRow = null;
  void persistOrder();
}
ui.body.addEventListener("pointerup", endDrag);
ui.body.addEventListener("pointercancel", endDrag);

// ---------- Tabs ----------

const tabs = [...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
function showTab(tab: HTMLButtonElement, focus = false) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")!).hidden = !on;
  }
  if (focus) tab.focus();
}
for (const t of tabs) {
  t.addEventListener("click", () => showTab(t));
  t.addEventListener("keydown", (e) => {
    const i = tabs.indexOf(t);
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      showTab(tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length], true);
    }
  });
}

// ---------- Wiring ----------

ui.checkBtn.addEventListener("click", () => void checkAll());
ui.activate.addEventListener("click", () => void activateSelected());
ui.rename.addEventListener("click", () => void renameSelected());
ui.remove.addEventListener("click", () => void deleteSelected());
$("btn-save").addEventListener("click", () => void saveActive());
$("btn-empty-save").addEventListener("click", () => void saveActive());
$("btn-paste").addEventListener("click", () => void openPaste());
$("btn-import").addEventListener("click", () => void importFile());
$("btn-new").addEventListener("click", () => void newAccount());
$("btn-export-all").addEventListener("click", () => void exportAll());
$("btn-import-all").addEventListener("click", () => void importAll());
$("btn-copy-raw").addEventListener("click", async () => {
  if (!activeUsage) {
    toast("Nothing to copy yet.", "error");
    return;
  }
  await writeText(JSON.stringify(activeUsage.raw, null, 2));
  toast("JSON copied to the clipboard.");
});

if (import.meta.env.DEV && !("__TAURI_INTERNALS__" in window)) await import("./mock");
await refresh();
void checkAll();
