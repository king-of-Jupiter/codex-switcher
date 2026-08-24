import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from api import extract_auth_info_from_dict
from theme import THEME, apply_dark_titlebar

# ================= КАСТОМНЫЕ VERCEL КОМПОНЕНТЫ =================
class VercelProgressBar(tk.Canvas):

    def __init__(
        self, parent, width=160, height=6, bg=THEME["bg_subtle"], **kwargs
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            **kwargs,
        )
        self.w = width
        self.h = height
        self.val = 0

    def set_value(self, percent: float, color=THEME["accent_green"]):
        self.val = max(0.0, min(100.0, percent))
        self.delete("all")
        self.create_rectangle(
            0,
            0,
            self.w,
            self.h,
            fill=THEME["bg_hover"],
            outline="",
        )
        fill_w = int((self.val / 100.0) * self.w)
        if fill_w > 0:
            self.create_rectangle(
                0, 0, fill_w, self.h, fill=color, outline=""
            )


# ================= ТЕМНЫЙ ДИАЛОГ ВВОДА ИМЕНИ =================
class VercelPromptDialog(tk.Toplevel):

    def __init__(
        self,
        parent,
        title: str,
        prompt: str,
        initial_value: str = "",
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry("380x170")
        self.resizable(False, False)
        self.configure(bg=THEME["bg_root"])
        self.transient(parent)
        self.grab_set()

        self.result = None
        apply_dark_titlebar(self)

        container = tk.Frame(self, bg=THEME["bg_root"], padx=18, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            container,
            text=prompt,
            font=("Segoe UI", 9, "bold"),
            bg=THEME["bg_root"],
            fg=THEME["text_primary"],
        ).pack(anchor="w", pady=(0, 10))

        border_ent = tk.Frame(
            container, bg=THEME["border_subtle"], padx=1, pady=1
        )
        border_ent.pack(fill=tk.X, pady=(0, 16))

        self.entry = tk.Entry(
            border_ent,
            font=("Segoe UI", 10),
            bg=THEME["bg_surface"],
            fg=THEME["text_primary"],
            insertbackground=THEME["accent_white"],
            bd=0,
        )
        self.entry.pack(fill=tk.X, ipady=5, padx=6)
        self.entry.insert(0, initial_value)
        self.entry.select_range(0, tk.END)
        self.entry.focus_set()

        btn_row = tk.Frame(container, bg=THEME["bg_root"])
        btn_row.pack(fill=tk.X)

        tk.Button(
            btn_row,
            text="OK",
            command=self._on_ok,
            bg=THEME["accent_white"],
            fg="#000000",
            activebackground="#d4d4d4",
            activeforeground="#000000",
            font=("Segoe UI", 8, "bold"),
            bd=0,
            padx=14,
            pady=4,
            relief="flat",
            cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(6, 0))

        tk.Button(
            btn_row,
            text="Cancel",
            command=self.destroy,
            bg=THEME["bg_subtle"],
            fg=THEME["text_secondary"],
            activebackground=THEME["bg_hover"],
            activeforeground=THEME["accent_white"],
            font=("Segoe UI", 8),
            bd=0,
            padx=12,
            pady=4,
            relief="flat",
            cursor="hand2",
        ).pack(side=tk.RIGHT)

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())

        self.wait_window(self)

    def _on_ok(self):
        val = self.entry.get().strip()
        if val:
            self.result = val
            self.destroy()


# ================= МОДАЛЬНОЕ ОКНО ВСТАВКИ JSON =================
class PasteJsonDialog(tk.Toplevel):

    def __init__(self, parent, profiles_dir: Path, on_success_callback):
        super().__init__(parent)
        self.title("Paste auth.json")
        self.geometry("620x480")
        self.resizable(False, False)
        self.configure(bg=THEME["bg_root"])
        self.transient(parent)
        self.grab_set()

        self.profiles_dir = profiles_dir
        self.on_success = on_success_callback
        self.detected_default_name = ""

        apply_dark_titlebar(self)
        self._build_ui()
        self._bind_keyboard_shortcuts()

        self.after(50, lambda: self.txt_json.focus_set())

    def _build_ui(self):
        container = tk.Frame(self, bg=THEME["bg_root"], padx=18, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        top_row = tk.Frame(container, bg=THEME["bg_root"])
        top_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))

        tk.Label(
            top_row,
            text="Paste auth.json content (Ctrl+V):",
            font=("Segoe UI", 10, "bold"),
            bg=THEME["bg_root"],
            fg=THEME["text_primary"],
        ).pack(side=tk.LEFT)

        btn_paste_clip = tk.Button(
            top_row,
            text="📋 Paste from Clipboard",
            command=self._paste_from_clipboard,
            bg=THEME["bg_subtle"],
            fg=THEME["accent_white"],
            activebackground=THEME["bg_hover"],
            activeforeground=THEME["accent_white"],
            font=("Segoe UI", 8),
            bd=0,
            padx=10,
            pady=4,
            relief="flat",
            cursor="hand2",
        )
        btn_paste_clip.pack(side=tk.RIGHT)

        bot_row = tk.Frame(container, bg=THEME["bg_root"])
        bot_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(12, 0))

        btn_save = tk.Button(
            bot_row,
            text="▲  Save Profile",
            command=self._save_profile_flow,
            bg=THEME["accent_white"],
            fg="#000000",
            activebackground="#d4d4d4",
            activeforeground="#000000",
            font=("Segoe UI", 9, "bold"),
            bd=0,
            padx=18,
            pady=7,
            relief="flat",
            cursor="hand2",
        )
        btn_save.pack(side=tk.RIGHT, padx=(8, 0))

        btn_cancel = tk.Button(
            bot_row,
            text="Cancel",
            command=self.destroy,
            bg=THEME["bg_subtle"],
            fg=THEME["text_secondary"],
            activebackground=THEME["bg_hover"],
            activeforeground=THEME["accent_white"],
            font=("Segoe UI", 8),
            bd=0,
            padx=14,
            pady=7,
            relief="flat",
            cursor="hand2",
        )
        btn_cancel.pack(side=tk.RIGHT)

        self.lbl_detect_status = tk.Label(
            container,
            text="Waiting for input... (Press Ctrl+V to paste)",
            font=("Segoe UI", 8),
            bg=THEME["bg_root"],
            fg=THEME["text_muted"],
        )
        self.lbl_detect_status.pack(side=tk.BOTTOM, anchor="w", pady=(8, 0))

        border_txt = tk.Frame(
            container, bg=THEME["border_subtle"], padx=1, pady=1
        )
        border_txt.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.txt_json = tk.Text(
            border_txt,
            font=("Consolas", 9),
            bg=THEME["bg_surface"],
            fg=THEME["text_primary"],
            insertbackground=THEME["accent_white"],
            bd=0,
            padx=10,
            pady=10,
            wrap=tk.WORD,
        )
        self.txt_json.pack(fill=tk.BOTH, expand=True)

    def _bind_keyboard_shortcuts(self):
        self.txt_json.bind("<KeyRelease>", self._on_text_change)
        self.txt_json.bind("<<Paste>>", lambda e: self.after(10, self._on_text_change))
        self.bind("<Control-v>", lambda e: self._on_hotkey_paste())
        self.bind("<Control-V>", lambda e: self._on_hotkey_paste())
        self.bind("<Control-a>", lambda e: self._select_all())
        self.bind("<Control-A>", lambda e: self._select_all())
        self.bind("<Control-KeyPress>", self._on_ctrl_keypress)

    def _on_ctrl_keypress(self, event):
        if event.keycode == 86 or event.keysym.lower() in ("v", "cyrillic_em"):
            self._on_hotkey_paste()
            return "break"
        elif event.keycode == 65 or event.keysym.lower() in ("a", "cyrillic_ef"):
            self._select_all()
            return "break"

    def _select_all(self):
        self.txt_json.tag_add(tk.SEL, "1.0", tk.END)
        self.txt_json.mark_set(tk.INSERT, "1.0")
        self.txt_json.see(tk.INSERT)
        return "break"

    def _on_hotkey_paste(self):
        self._paste_from_clipboard()
        return "break"

    def _paste_from_clipboard(self):
        try:
            content = self.clipboard_get().strip()
            if content:
                self.txt_json.delete("1.0", tk.END)
                self.txt_json.insert(tk.END, content)
                self._on_text_change()
        except Exception:
            messagebox.showwarning(
                "Clipboard", "Clipboard is empty or does not contain text."
            )

    def _on_text_change(self, event=None):
        raw = self.txt_json.get("1.0", tk.END).strip()
        if not raw:
            self.lbl_detect_status.config(
                text="Waiting for input... (Press Ctrl+V to paste)",
                fg=THEME["text_muted"],
            )
            return

        try:
            data = json.loads(raw)
            info = extract_auth_info_from_dict(data)

            email_str = info["email"]
            plan_str = info["plan"]

            if email_str != "—":
                self.lbl_detect_status.config(
                    text=f"✓ Detected: {email_str} [{plan_str}]",
                    fg=THEME["badge_plus_fg"],
                )
                self.detected_default_name = email_str.split("@")[0]
            else:
                self.lbl_detect_status.config(
                    text="✓ Valid JSON format", fg=THEME["text_secondary"]
                )
                self.detected_default_name = "custom_account"
        except Exception:
            self.lbl_detect_status.config(
                text="✕ Invalid JSON format", fg=THEME["accent_red"]
            )

    def _save_profile_flow(self):
        raw = self.txt_json.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showerror("Error", "Please paste JSON content first.")
            return

        try:
            data = json.loads(raw)
        except Exception as e:
            messagebox.showerror(
                "Invalid JSON", f"Could not parse JSON content:\n{e}"
            )
            return

        prompt = VercelPromptDialog(
            self,
            title="Profile Name",
            prompt="Enter name for this profile:",
            initial_value=self.detected_default_name or "account",
        )

        name = prompt.result
        if not name:
            return

        name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        dest = self.profiles_dir / f"{name}.json"

        if dest.exists():
            if not messagebox.askyesno(
                "Overwrite", f"Profile '{name}' already exists. Overwrite?"
            ):
                return

        try:
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            self.on_success(name)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save profile:\n{e}")
