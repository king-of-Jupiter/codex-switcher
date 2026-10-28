// In-app dialogs built on <dialog>, each resolving to the user's answer.
import type { ScanEntry } from "./api";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

function waitForClose(dlg: HTMLDialogElement): Promise<string> {
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue), { once: true });
  });
}

export async function promptText(opts: {
  title: string;
  label?: string;
  value: string;
  ok?: string;
  hint?: string;
}): Promise<string | null> {
  const dlg = $<HTMLDialogElement>("dlg-prompt");
  const input = $<HTMLInputElement>("dlg-prompt-input");
  $("dlg-prompt-title").textContent = opts.title;
  $("dlg-prompt-label").textContent = opts.label ?? "Profile name";
  $("dlg-prompt-ok").textContent = opts.ok ?? "Save";
  $("dlg-prompt-hint").textContent = opts.hint ?? "";
  input.value = opts.value;
  dlg.returnValue = "";
  dlg.showModal();
  input.select();
  const answer = await waitForClose(dlg);
  const value = input.value.trim();
  return answer === "ok" && value ? value : null;
}

export async function confirm(opts: { title: string; body: string; ok?: string; cancel?: string }): Promise<boolean> {
  const dlg = $<HTMLDialogElement>("dlg-confirm");
  $("dlg-confirm-title").textContent = opts.title;
  $("dlg-confirm-body").textContent = opts.body;
  $("dlg-confirm-ok").textContent = opts.ok ?? "Continue";
  $("dlg-confirm-cancel").textContent = opts.cancel ?? "Cancel";
  dlg.returnValue = "";
  dlg.showModal();
  $<HTMLButtonElement>("dlg-confirm-cancel").focus();
  return (await waitForClose(dlg)) === "ok";
}

/** Asks which existing profiles to overwrite; null when the import is cancelled. */
export async function chooseOverwrites(conflicts: ScanEntry[]): Promise<string[] | null> {
  const dlg = $<HTMLDialogElement>("dlg-conflicts");
  const list = $<HTMLFieldSetElement>("dlg-conflicts-list");
  list.querySelectorAll("label").forEach((el) => el.remove());
  for (const c of conflicts) {
    const label = document.createElement("label");
    label.className = "check";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = c.name;
    const text = document.createElement("span");
    text.textContent = c.name;
    label.append(box, text);
    list.append(label);
  }
  dlg.returnValue = "";
  dlg.showModal();
  if ((await waitForClose(dlg)) !== "ok") return null;
  return [...list.querySelectorAll<HTMLInputElement>("input:checked")].map((b) => b.value);
}

let toastTimer: number | undefined;

export function toast(message: string, tone: "info" | "error" = "info") {
  const el = $("toast");
  el.textContent = message;
  el.dataset.tone = tone;
  el.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (el.hidden = true), tone === "error" ? 7000 : 4000);
}
