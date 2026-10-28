// Typed wrappers over the Rust commands in src-tauri/src/lib.rs.
import { invoke } from "@tauri-apps/api/core";

export interface AuthInfo {
  email: string;
  name: string;
  plan: string;
  expires: string;
  account_id: string;
  is_valid: boolean;
}

export interface ProfileRow {
  name: string;
  info: AuthInfo;
  active: boolean;
}

export interface AppState {
  auth_exists: boolean;
  active_profile: string | null;
  active_info: AuthInfo;
  profiles: ProfileRow[];
  profiles_dir: string;
}

export interface ScanEntry {
  name: string;
  exists: boolean;
}

export interface ImportResult {
  imported: number;
  overwritten: number;
  skipped: number;
}

/** Rejection a save command gives when the profile exists and overwrite was false. */
export const EXISTS = "EXISTS";

export const api = {
  state: () => invoke<AppState>("get_state"),
  inspectText: (text: string) => invoke<AuthInfo>("inspect_auth_text", { text }),
  inspectFile: (path: string) => invoke<AuthInfo>("inspect_auth_file", { path }),
  saveActive: (name: string, overwrite: boolean) => invoke<string>("save_active", { name, overwrite }),
  importFile: (path: string, name: string, overwrite: boolean) => invoke<string>("import_profile_file", { path, name, overwrite }),
  saveText: (name: string, text: string, overwrite: boolean) => invoke<string>("save_profile_text", { name, text, overwrite }),
  rename: (old: string, next: string) => invoke<string>("rename_profile", { old, new: next }),
  remove: (name: string) => invoke<void>("delete_profile", { name }),
  saveOrder: (order: string[]) => invoke<void>("save_order", { order }),
  activate: (name: string, restart: boolean) => invoke<void>("activate_profile", { name, restart }),
  newAccount: () => invoke<void>("new_account"),
  usage: (name: string | null) => invoke<unknown>("fetch_usage", { name }),
  exportAll: (path: string) => invoke<number>("export_all", { path }),
  importScan: (path: string) => invoke<ScanEntry[]>("import_scan", { path }),
  importApply: (path: string, overwrite: string[]) => invoke<ImportResult>("import_apply", { path, overwrite }),
};

export function defaultName(info: AuthInfo, fallback = "account"): string {
  return info.email && info.email !== "—" ? info.email.split("@")[0] : fallback;
}
