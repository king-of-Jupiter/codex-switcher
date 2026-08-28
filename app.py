import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from api import extract_auth_info, fetch_api_usage_raw, parse_dynamic_usage
from theme import THEME, apply_app_icon, apply_dark_titlebar
from widgets import PasteJsonDialog, VercelProgressBar, VercelPromptDialog

# ================= ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ =================
class CodexVercelSwitcher(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title("Codex / ChatGPT Profile Manager")
        self.geometry("880x740")
        self.minsize(800, 640)
        self.configure(bg=THEME["bg_root"])

        apply_dark_titlebar(self)
        apply_app_icon(self)

        self.codex_dir = Path.home() / ".codex"
        self.auth_file = self.codex_dir / "auth.json"
        self.profiles_dir = self.codex_dir / "profiles"
        self.order_file = self.codex_dir / "profiles_order.json"

        self.codex_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        self._dnd_item = None

        self._setup_styles()
        self._build_ui()
        self.refresh_profiles()

        # Автоматический запуск опроса всех квот при старте приложения
        self.after(150, self.fetch_all_accounts_async)

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(
            "Treeview",
            background=THEME["bg_surface"],
            foreground=THEME["text_primary"],
            fieldbackground=THEME["bg_surface"],
            borderwidth=0,
            font=("Segoe UI", 9),
            rowheight=32,
        )
        style.map(
            "Treeview",
            background=[("selected", THEME["bg_hover"])],
            foreground=[("selected", THEME["accent_white"])],
        )

        style.configure(
            "Treeview.Heading",
            background=THEME["bg_subtle"],
            foreground=THEME["text_secondary"],
            borderwidth=0,
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padding=(6, 4),
        )
        style.map("Treeview.Heading", background=[("active", THEME["bg_hover"])])

        style.configure(
            "Vertical.TScrollbar",
            background=THEME["bg_subtle"],
            troughcolor=THEME["bg_root"],
            borderwidth=0,
            arrowsize=10,
        )

    def _build_ui(self):
        container = tk.Frame(self, bg=THEME["bg_root"], padx=20, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        # 1. HEADER
        header = tk.Frame(container, bg=THEME["bg_root"])
        header.pack(fill=tk.X, pady=(0, 16))

        logo_box = tk.Frame(header, bg=THEME["bg_root"])
        logo_box.pack(side=tk.LEFT)

        tk.Label(
            logo_box,
            text="▲",
            font=("Segoe UI", 14, "bold"),
            bg=THEME["bg_root"],
            fg=THEME["accent_white"],
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(
            logo_box,
            text="CODEX",
            font=("Segoe UI", 12, "bold"),
            bg=THEME["bg_root"],
            fg=THEME["accent_white"],
        ).pack(side=tk.LEFT)

        tk.Label(
            logo_box,
            text=" / ACCOUNT SWITCHER",
            font=("Segoe UI", 11),
            bg=THEME["bg_root"],
            fg=THEME["text_muted"],
        ).pack(side=tk.LEFT)

        tab_box = tk.Frame(header, bg=THEME["bg_subtle"], padx=3, pady=3)
        tab_box.pack(side=tk.RIGHT)

        self.btn_tab_manage = tk.Button(
            tab_box,
            text="Overview",
            command=lambda: self._set_active_tab(0),
            bg=THEME["bg_hover"],
            fg=THEME["text_primary"],
            activebackground=THEME["bg_hover"],
            activeforeground=THEME["accent_white"],
            font=("Segoe UI", 8, "bold"),
            bd=0,
            padx=12,
            pady=4,
            relief="flat",
            cursor="hand2",
        )
        self.btn_tab_manage.pack(side=tk.LEFT)

        self.btn_tab_raw = tk.Button(
            tab_box,
            text="Live API JSON",
            command=lambda: self._set_active_tab(1),
            bg=THEME["bg_subtle"],
            fg=THEME["text_secondary"],
            activebackground=THEME["bg_hover"],
            activeforeground=THEME["accent_white"],
            font=("Segoe UI", 8, "bold"),
            bd=0,
            padx=12,
            pady=4,
            relief="flat",
            cursor="hand2",
        )
        self.btn_tab_raw.pack(side=tk.LEFT)

        # 2. TAB CONTAINER
        self.frames_container = tk.Frame(container, bg=THEME["bg_root"])
        self.frames_container.pack(fill=tk.BOTH, expand=True)

        self.frame_overview = tk.Frame(
            self.frames_container, bg=THEME["bg_root"]
        )
        self.frame_raw = tk.Frame(
            self.frames_container, bg=THEME["bg_root"]
        )

        self.frame_overview.pack(fill=tk.BOTH, expand=True)

        self._build_overview_tab()
        self._build_raw_tab()

    def _set_active_tab(self, idx: int):
        if idx == 0:
            self.frame_raw.pack_forget()
            self.frame_overview.pack(fill=tk.BOTH, expand=True)
            self.btn_tab_manage.configure(
                bg=THEME["bg_hover"], fg=THEME["text_primary"]
            )
            self.btn_tab_raw.configure(
                bg=THEME["bg_subtle"], fg=THEME["text_secondary"]
            )
        else:
            self.frame_overview.pack_forget()
            self.frame_raw.pack(fill=tk.BOTH, expand=True)
            self.btn_tab_raw.configure(
                bg=THEME["bg_hover"], fg=THEME["text_primary"]
            )
            self.btn_tab_manage.configure(
                bg=THEME["bg_subtle"], fg=THEME["text_secondary"]
            )

    def _build_overview_tab(self):
        card_border = tk.Frame(
            self.frame_overview, bg=THEME["border_subtle"], padx=1, pady=1
        )
        card_border.pack(fill=tk.X, pady=(0, 14))

        self.card = tk.Frame(card_border, bg=THEME["bg_surface"], padx=16, pady=14)
        self.card.pack(fill=tk.X)

        # 1-я строка
        r1 = tk.Frame(self.card, bg=THEME["bg_surface"])
        r1.pack(fill=tk.X, pady=(0, 4))

        self.lbl_active_name = tk.Label(
            r1,
            text="Active Profile: —",
            font=("Segoe UI", 12, "bold"),
            bg=THEME["bg_surface"],
            fg=THEME["text_primary"],
        )
        self.lbl_active_name.pack(side=tk.LEFT)

        self.badge_box = tk.Frame(r1, bg=THEME["bg_surface"])
        self.badge_box.pack(side=tk.RIGHT)

        self.lbl_badge_plan = tk.Label(
            self.badge_box,
            text="PLUS",
            font=("Segoe UI", 8, "bold"),
            bg=THEME["badge_plus_bg"],
            fg=THEME["badge_plus_fg"],
            padx=8,
            pady=2,
        )
        self.lbl_badge_plan.pack(side=tk.LEFT, padx=3)

        self.lbl_badge_ticket = tk.Label(
            self.badge_box,
            text="🎟️ RESETS: —",
            font=("Segoe UI", 8, "bold"),
            bg=THEME["badge_ticket_bg"],
            fg=THEME["badge_ticket_fg"],
            padx=8,
            pady=2,
        )
        self.lbl_badge_ticket.pack(side=tk.LEFT, padx=3)

        # 2-я строка
        self.lbl_email_sub = tk.Label(
            self.card,
            text="email@example.com  •  Valid until: —",
            font=("Segoe UI", 9),
            bg=THEME["bg_surface"],
            fg=THEME["text_secondary"],
        )
        self.lbl_email_sub.pack(anchor="w", pady=(0, 10))

        # 3-я строка: Dynamic Progress Bars
        self.limits_container = tk.Frame(self.card, bg=THEME["bg_surface"])
        self.limits_container.pack(fill=tk.X, pady=(0, 6))

        self.lbl_initial_notice = tk.Label(
            self.limits_container,
            text="Fetching live quotas from OpenAI...",
            font=("Segoe UI", 9),
            bg=THEME["bg_surface"],
            fg=THEME["text_muted"],
        )
        self.lbl_initial_notice.pack(anchor="w")

        # 4-я строка
        r4 = tk.Frame(self.card, bg=THEME["bg_surface"])
        r4.pack(fill=tk.X, pady=(4, 0))

        self.lbl_credits_info = tk.Label(
            r4,
            text="Credits: $0.00",
            font=("Segoe UI", 8),
            bg=THEME["bg_surface"],
            fg=THEME["text_muted"],
        )
        self.lbl_credits_info.pack(side=tk.LEFT)

        # ТАБЛИЦА ВСЕХ ПРОФИЛЕЙ
        tbl_border = tk.Frame(
            self.frame_overview, bg=THEME["border_subtle"], padx=1, pady=1
        )
        tbl_border.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        tbl_bg = tk.Frame(tbl_border, bg=THEME["bg_surface"])
        tbl_bg.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "email", "plan", "quota", "tickets", "status")
        self.tree = ttk.Treeview(
            tbl_bg, columns=cols, show="headings", selectmode="browse"
        )

        self.tree.heading("name", text="PROFILE")
        self.tree.heading("email", text="EMAIL / USER")
        self.tree.heading("plan", text="PLAN")
        self.tree.heading("quota", text="7D QUOTA")
        self.tree.heading("tickets", text="RESETS")
        self.tree.heading("status", text="STATUS")

        self.tree.column("name", width=120, anchor="w")
        self.tree.column("email", width=240, anchor="w")
        self.tree.column("plan", width=75, anchor="center")
        self.tree.column("quota", width=110, anchor="center")
        self.tree.column("tickets", width=85, anchor="center")
        self.tree.column("status", width=90, anchor="center")

        scroll = ttk.Scrollbar(
            tbl_bg,
            orient=tk.VERTICAL,
            command=self.tree.yview,
            style="Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=scroll.set)

        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Привязка перетаскивания (Drag-and-Drop) строк
        self.tree.bind("<ButtonPress-1>", self._on_dnd_start)
        self.tree.bind("<B1-Motion>", self._on_dnd_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_dnd_stop)
        self.tree.bind("<Double-Button-1>", lambda e: self.switch_profile())

        # ПАНЕЛЬ УПРАВЛЕНИЯ
        actions_bar = tk.Frame(self.frame_overview, bg=THEME["bg_root"])
        actions_bar.pack(fill=tk.X)

        self.var_restart = tk.BooleanVar(value=True)
        cb = tk.Checkbutton(
            actions_bar,
            text="Auto-restart ChatGPT.exe on switch",
            variable=self.var_restart,
            bg=THEME["bg_root"],
            fg=THEME["text_secondary"],
            activebackground=THEME["bg_root"],
            activeforeground=THEME["text_primary"],
            selectcolor=THEME["bg_surface"],
            font=("Segoe UI", 8),
            bd=0,
            highlightthickness=0,
        )
        cb.pack(anchor="w", pady=(0, 8))

        btns_row = tk.Frame(actions_bar, bg=THEME["bg_root"])
        btns_row.pack(fill=tk.X)

        self.btn_activate = tk.Button(
            btns_row,
            text="▲  Activate Account",
            command=self.switch_profile,
            bg=THEME["accent_white"],
            fg="#000000",
            activebackground="#d4d4d4",
            activeforeground="#000000",
            font=("Segoe UI", 9, "bold"),
            bd=0,
            padx=15,
            pady=7,
            relief="flat",
            cursor="hand2",
        )
        self.btn_activate.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_check_all = tk.Button(
            btns_row,
            text="🔄  Check All Quotas",
            command=self.fetch_all_accounts_async,
            bg=THEME["bg_hover"],
            fg=THEME["accent_white"],
            activebackground=THEME["border_active"],
            activeforeground=THEME["accent_white"],
            font=("Segoe UI", 8, "bold"),
            bd=0,
            padx=12,
            pady=7,
            relief="flat",
            cursor="hand2",
        )
        self.btn_check_all.pack(side=tk.LEFT, padx=3)

        btn_paste = tk.Button(
            btns_row,
            text="+ Paste JSON",
            command=self.open_paste_dialog,
            bg=THEME["bg_subtle"],
            fg=THEME["badge_plus_fg"],
            activebackground=THEME["bg_hover"],
            activeforeground=THEME["accent_white"],
            font=("Segoe UI", 8, "bold"),
            bd=0,
            padx=11,
            pady=7,
            relief="flat",
            cursor="hand2",
        )
        btn_paste.pack(side=tk.LEFT, padx=3)

        sec_btns = [
            ("Save Active", self.save_current_auth),
            ("Import File", self.import_profile),
            ("Rename", self.rename_profile),
            ("Delete", self.delete_profile),
        ]

        for text, cmd in sec_btns:
            b = tk.Button(
                btns_row,
                text=text,
                command=cmd,
                bg=THEME["bg_subtle"],
                fg=THEME["text_primary"],
                activebackground=THEME["bg_hover"],
                activeforeground=THEME["accent_white"],
                font=("Segoe UI", 8),
                bd=0,
                padx=9,
                pady=7,
                relief="flat",
                cursor="hand2",
            )
            b.pack(side=tk.LEFT, padx=3)

        # --- Bulk Export / Import row ---
        bulk_row = tk.Frame(actions_bar, bg=THEME["bg_root"])
        bulk_row.pack(fill=tk.X, pady=(8, 0))

        tk.Label(
            bulk_row,
            text="Bulk:",
            font=("Segoe UI", 8, "bold"),
            bg=THEME["bg_root"],
            fg=THEME["text_muted"],
        ).pack(side=tk.LEFT, padx=(0, 6))

        for text, cmd in [
            ("⬇ Export All", self.export_all_profiles),
            ("⬆ Import All", self.import_all_profiles),
        ]:
            b = tk.Button(
                bulk_row,
                text=text,
                command=cmd,
                bg="#1a1a1a",
                fg=THEME["text_primary"],
                activebackground=THEME["bg_hover"],
                activeforeground=THEME["accent_white"],
                font=("Segoe UI", 8, "bold"),
                bd=0,
                padx=10,
                pady=6,
                relief="flat",
                cursor="hand2",
                highlightthickness=1,
                highlightbackground=THEME["border_subtle"],
            )
            b.pack(side=tk.LEFT, padx=3)

    def _build_raw_tab(self):
        border = tk.Frame(
            self.frame_raw, bg=THEME["border_subtle"], padx=1, pady=1
        )
        border.pack(fill=tk.BOTH, expand=True)

        box = tk.Frame(border, bg=THEME["bg_surface"], padx=12, pady=12)
        box.pack(fill=tk.BOTH, expand=True)

        top_r = tk.Frame(box, bg=THEME["bg_surface"])
        top_r.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            top_r,
            text="ENDPOINT: https://chatgpt.com/backend-api/wham/usage",
            font=("Consolas", 9),
            bg=THEME["bg_surface"],
            fg=THEME["text_muted"],
        ).pack(side=tk.LEFT)

        tk.Button(
            top_r,
            text="Copy JSON",
            command=self._copy_raw_json,
            bg=THEME["bg_subtle"],
            fg=THEME["text_primary"],
            activebackground=THEME["bg_hover"],
            activeforeground=THEME["accent_white"],
            font=("Segoe UI", 8),
            bd=0,
            padx=10,
            pady=3,
            relief="flat",
            cursor="hand2",
        ).pack(side=tk.RIGHT)

        txt_frame = tk.Frame(box, bg=THEME["bg_surface"])
        txt_frame.pack(fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(
            txt_frame, orient=tk.VERTICAL, style="Vertical.TScrollbar"
        )
        self.txt_raw = tk.Text(
            txt_frame,
            font=("Consolas", 10),
            wrap=tk.NONE,
            yscrollcommand=scroll.set,
            bg=THEME["bg_root"],
            fg=THEME["text_primary"],
            insertbackground=THEME["accent_white"],
            bd=0,
            padx=10,
            pady=10,
        )
        scroll.config(command=self.txt_raw.yview)

        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_raw.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.txt_raw.tag_config("key", foreground="#93c5fd")
        self.txt_raw.tag_config("str", foreground="#86efac")
        self.txt_raw.tag_config("num", foreground="#fca5a5")
        self.txt_raw.tag_config("bool", foreground="#c084fc")

    def _copy_raw_json(self):
        text = self.txt_raw.get("1.0", tk.END).strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", "JSON response copied to clipboard!")

    def _apply_json_highlight(self, json_str: str):
        self.txt_raw.delete("1.0", tk.END)
        self.txt_raw.insert(tk.END, json_str)

        content = json_str
        for match in re.finditer(r'"(.*?)"(?=\s*:)', content):
            start = f"1.0 + {match.start()} chars"
            end = f"1.0 + {match.end()} chars"
            self.txt_raw.tag_add("key", start, end)

        for match in re.finditer(r':\s*"([^"]*)"', content):
            start = f"1.0 + {match.start() + 2} chars"
            end = f"1.0 + {match.end()} chars"
            self.txt_raw.tag_add("str", start, end)

        for match in re.finditer(r'\b(true|false|null)\b', content):
            start = f"1.0 + {match.start()} chars"
            end = f"1.0 + {match.end()} chars"
            self.txt_raw.tag_add("bool", start, end)

        for match in re.finditer(r'\b\d+(\.\d+)?\b', content):
            start = f"1.0 + {match.start()} chars"
            end = f"1.0 + {match.end()} chars"
            self.txt_raw.tag_add("num", start, end)

    def _get_file_hash(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""

    # ================= УПРАВЛЕНИЕ ПОРЯДКОМ И DRAG-AND-DROP =================
    def _load_ordered_profiles(self) -> list:
        disk_files = {p.stem: p for p in self.profiles_dir.glob("*.json")}
        ordered = []

        if self.order_file.exists():
            try:
                with open(self.order_file, "r", encoding="utf-8") as f:
                    saved_order = json.load(f)
                for name in saved_order:
                    if name in disk_files:
                        ordered.append(disk_files.pop(name))
            except Exception:
                pass

        for p in disk_files.values():
            ordered.append(p)

        return ordered

    def _save_profiles_order(self):
        current_order = list(self.tree.get_children(""))
        try:
            with open(self.order_file, "w", encoding="utf-8") as f:
                json.dump(current_order, f, indent=2)
        except Exception:
            pass

    def _on_dnd_start(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self._dnd_item = item

    def _on_dnd_motion(self, event):
        if not self._dnd_item:
            return
        target = self.tree.identify_row(event.y)
        if target and target != self._dnd_item:
            target_idx = self.tree.index(target)
            self.tree.move(self._dnd_item, "", target_idx)

    def _on_dnd_stop(self, event):
        if self._dnd_item:
            self._save_profiles_order()
            self._dnd_item = None

    def refresh_profiles(self):
        # Сохраняем уже загруженные значения квот в памяти, чтобы они не сбрасывались
        existing_values = {}
        for item in self.tree.get_children():
            existing_values[item] = self.tree.item(item, "values")

        for item in self.tree.get_children():
            self.tree.delete(item)

        current_hash = self._get_file_hash(self.auth_file)
        current_info = extract_auth_info(self.auth_file)

        matched_profile = None
        ordered_files = self._load_ordered_profiles()

        for p_file in ordered_files:
            p_name = p_file.stem
            p_hash = self._get_file_hash(p_file)
            p_info = extract_auth_info(p_file)

            is_active = current_hash and p_hash == current_hash
            status_text = "● ACTIVE" if is_active else "—"
            if is_active:
                matched_profile = p_name

            # Подставляем сохраненные квоты, если они уже были получены
            prev = existing_values.get(p_name)
            quota_val = prev[3] if prev and len(prev) > 3 else "—"
            ticket_val = prev[4] if prev and len(prev) > 4 else "—"

            self.tree.insert(
                "",
                tk.END,
                iid=p_name,
                values=(
                    p_name,
                    p_info["email"],
                    p_info["plan"],
                    quota_val,
                    ticket_val,
                    status_text,
                ),
            )

        if matched_profile:
            self.lbl_active_name.config(text=f"Active Profile: {matched_profile}")
        elif self.auth_file.exists():
            self.lbl_active_name.config(text="Active Profile: Custom / Unsaved")
        else:
            self.lbl_active_name.config(text="Active Profile: No auth.json")

        self.lbl_badge_plan.config(text=current_info.get("plan", "FREE"))
        self.lbl_email_sub.config(
            text=f"{current_info['email']}  •  Expires: {current_info['expires']}"
        )

    def open_paste_dialog(self):
        PasteJsonDialog(self, self.profiles_dir, self._on_pasted_profile_saved)

    def _on_pasted_profile_saved(self, profile_name: str):
        self.refresh_profiles()
        self._save_profiles_order()
        self.fetch_all_accounts_async()

    # ================= ОПРОС ВСЕХ АККАУНТОВ =================
    def fetch_all_accounts_async(self):
        self.btn_check_all.config(state=tk.DISABLED, text="⏳ Updating...")

        def _worker():
            raw_active = fetch_api_usage_raw(self.auth_file)
            parsed_active = parse_dynamic_usage(raw_active)
            self.after(
                0, lambda: self._apply_active_limits_ui(raw_active, parsed_active)
            )

            ordered_files = self._load_ordered_profiles()
            total = len(ordered_files)

            for idx, p_file in enumerate(ordered_files, start=1):
                self.after(
                    0,
                    lambda i=idx, t=total: self.btn_check_all.config(
                        text=f"⏳ {i}/{t}..."
                    ),
                )
                p_name = p_file.stem
                raw = fetch_api_usage_raw(p_file)
                parsed = parse_dynamic_usage(raw)

                quota_7d = "—"
                tickets_str = "—"

                if "error" not in parsed:
                    tickets_str = str(parsed.get("reset_tickets", 0))
                    for w in parsed["windows"]:
                        if "7д" in w["title"] or "Основной" in w["title"]:
                            quota_7d = f"{w['left']}%"

                def _upd_row(n=p_name, q=quota_7d, t=tickets_str):
                    if self.tree.exists(n):
                        vals = list(self.tree.item(n, "values"))
                        vals[3] = q
                        vals[4] = t
                        self.tree.item(n, values=vals)

                self.after(0, _upd_row)
                time.sleep(0.2)

            self.after(
                0,
                lambda: self.btn_check_all.config(
                    state=tk.NORMAL, text="🔄  Check All Quotas"
                ),
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_active_limits_ui(self, raw_data: dict, parsed: dict):
        formatted_json = json.dumps(raw_data, indent=2, ensure_ascii=False)
        self._apply_json_highlight(formatted_json)

        for widget in self.limits_container.winfo_children():
            widget.destroy()

        if "error" in parsed:
            tk.Label(
                self.limits_container,
                text=f"API Status: {parsed['error']}",
                font=("Segoe UI", 9),
                bg=THEME["bg_surface"],
                fg=THEME["accent_red"],
            ).pack(anchor="w")
            return

        if parsed["windows"]:
            for w in parsed["windows"]:
                row = tk.Frame(self.limits_container, bg=THEME["bg_surface"])
                row.pack(fill=tk.X, pady=3)

                info_text = f"{w['title']}: {w['left']}% remaining  (Resets {w['reset_str']})"
                tk.Label(
                    row,
                    text=info_text,
                    font=("Segoe UI", 9),
                    bg=THEME["bg_surface"],
                    fg=THEME["text_primary"],
                ).pack(side=tk.LEFT)

                pb = VercelProgressBar(row, width=140, height=6)
                pb.pack(side=tk.RIGHT, padx=4)
                pb.set_value(w["left"], color=THEME["accent_green"])
        else:
            tk.Label(
                self.limits_container,
                text="No active limits reported by server",
                font=("Segoe UI", 9),
                bg=THEME["bg_surface"],
                fg=THEME["text_muted"],
            ).pack(anchor="w")

        tickets = parsed.get("reset_tickets", 0)
        self.lbl_badge_ticket.config(text=f"🎟️ {tickets} RESETS")
        if tickets > 0:
            self.lbl_badge_ticket.config(
                bg=THEME["badge_ticket_bg"], fg=THEME["badge_ticket_fg"]
            )
        else:
            self.lbl_badge_ticket.config(
                bg=THEME["bg_subtle"], fg=THEME["text_secondary"]
            )

        cr = parsed.get("credits", "0")
        self.lbl_credits_info.config(text=f"Additional Credits: ${cr}")

    # ================= ПЕРЕКЛЮЧЕНИЕ АККАУНТОВ =================
    def _restart_codex_app(self):
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            for proc in [
                "ChatGPT.exe",
                "Codex.exe",
                "OpenAI.Codex.exe",
                "OpenAI.Codex",
            ]:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/IM", proc],
                        startupinfo=startupinfo,
                        capture_output=True,
                    )
                except Exception:
                    pass

            time.sleep(0.8)

            ps_script = (
                "$app = Get-StartApps | Where-Object { "
                "$_.AppID -like '*OpenAI.Codex*' -or $_.AppID -like '*2p2nqsd0c76g0*' -or $_.AppID -like '*ChatGPT*' "
                "} | Select-Object -First 1; "
                "if ($app) { Start-Process ('shell:AppsFolder\\' + $app.AppID) } "
                "else { Start-Process 'shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App' }"
            )

            try:
                subprocess.Popen(
                    [
                        "powershell",
                        "-NoProfile",
                        "-WindowStyle",
                        "Hidden",
                        "-Command",
                        ps_script,
                    ],
                    creationflags=getattr(
                        subprocess, "CREATE_NO_WINDOW", 0x08000000
                    ),
                )
            except Exception:
                os.system(
                    'explorer.exe "shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App"'
                )
        else:
            subprocess.run(["pkill", "-f", "ChatGPT"], capture_output=True)
            subprocess.run(["pkill", "-f", "Codex"], capture_output=True)

    def switch_profile(self):
        """Мгновенное локальное переключение профиля без лишних повторных сетевых запросов."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Notice", "Select a profile from the table.")
            return

        profile_name = selected[0]
        src = self.profiles_dir / f"{profile_name}.json"

        if not src.exists():
            messagebox.showerror("Error", f"Profile {src.name} not found.")
            return

        try:
            if self.auth_file.exists():
                shutil.copy2(self.auth_file, self.codex_dir / "auth.json.bak")

            shutil.copy2(src, self.auth_file)
            self.refresh_profiles()

            if self.var_restart.get():
                self._restart_codex_app()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def save_current_auth(self):
        if not self.auth_file.exists():
            messagebox.showerror("Error", "auth.json does not exist.")
            return

        info = extract_auth_info(self.auth_file)
        default_name = (
            info["email"].split("@")[0] if info["email"] != "—" else "account"
        )

        prompt = VercelPromptDialog(
            self,
            title="Save Profile",
            prompt="Enter profile name:",
            initial_value=default_name,
        )

        name = prompt.result
        if not name:
            return

        name = name.strip().replace("/", "_").replace("\\", "_")
        dest = self.profiles_dir / f"{name}.json"

        if dest.exists() and not messagebox.askyesno(
            "Overwrite", f"Profile '{name}' already exists. Overwrite?"
        ):
            return

        try:
            shutil.copy2(self.auth_file, dest)
            self.refresh_profiles()
            self._save_profiles_order()
            self.fetch_all_accounts_async()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def import_profile(self):
        file_path = filedialog.askopenfilename(
            title="Select auth.json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not file_path:
            return

        info = extract_auth_info(Path(file_path))
        default_name = (
            info["email"].split("@")[0]
            if info["email"] != "—"
            else Path(file_path).stem
        )

        prompt = VercelPromptDialog(
            self,
            title="Import Profile",
            prompt="Enter profile name:",
            initial_value=default_name,
        )

        name = prompt.result
        if not name:
            return

        name = name.strip().replace("/", "_").replace("\\", "_")
        dest = self.profiles_dir / f"{name}.json"

        try:
            shutil.copy2(file_path, dest)
            self.refresh_profiles()
            self._save_profiles_order()
            self.fetch_all_accounts_async()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def rename_profile(self):
        selected = self.tree.selection()
        if not selected:
            return
        old_name = selected[0]

        prompt = VercelPromptDialog(
            self,
            title="Rename",
            prompt="New name:",
            initial_value=old_name,
        )

        new_name = prompt.result
        if not new_name or new_name == old_name:
            return

        new_name = new_name.strip().replace("/", "_").replace("\\", "_")
        try:
            (self.profiles_dir / f"{old_name}.json").rename(
                self.profiles_dir / f"{new_name}.json"
            )
            self.refresh_profiles()
            self._save_profiles_order()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def delete_profile(self):
        selected = self.tree.selection()
        if not selected:
            return
        name = selected[0]
        if messagebox.askyesno("Delete", f"Delete profile '{name}'?"):
            try:
                (self.profiles_dir / f"{name}.json").unlink()
                self.refresh_profiles()
                self._save_profiles_order()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    # ================= ЭКСПОРТ / ИМПОРТ ВСЕХ АККАУНТОВ =================
    def export_all_profiles(self):
        profiles = list(self.profiles_dir.glob("*.json"))
        if not profiles:
            messagebox.showwarning("Export", "Нет сохранённых профилей для экспорта.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Export all profiles",
            defaultextension=".zip",
            filetypes=[
                ("ZIP archive", "*.zip"),
                ("JSON bundle", "*.json"),
                ("All Files", "*.*"),
            ],
            initialfile=f"codex_profiles_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
        )
        if not file_path:
            return

        try:
            dest = Path(file_path)
            if dest.suffix.lower() == ".json":
                # JSON bundle: {profiles: {name: data}, order: [...], exported_at: ...}
                bundle = {
                    "export_version": 1,
                    "exported_at": datetime.datetime.now().isoformat(),
                    "profiles": {},
                    "order": [],
                }
                # порядок берём из Treeview (актуальный DnD) или из файла
                order = list(self.tree.get_children("")) if self.tree.get_children("") else []
                # fallback: собрать из файлов
                if not order:
                    order = [p.stem for p in self._load_ordered_profiles()]
                bundle["order"] = order
                for p_file in profiles:
                    try:
                        with open(p_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        bundle["profiles"][p_file.stem] = data
                    except Exception:
                        continue
                with open(dest, "w", encoding="utf-8") as f:
                    json.dump(bundle, f, indent=2, ensure_ascii=False)
            else:
                # ZIP archive — каждый профиль отдельным .json + profiles_order.json
                with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p_file in profiles:
                        zf.write(p_file, arcname=f"{p_file.name}")
                    # сохраняем порядок
                    order = list(self.tree.get_children("")) if self.tree.get_children("") else []
                    if order:
                        zf.writestr("profiles_order.json", json.dumps(order, indent=2, ensure_ascii=False))
                    elif self.order_file.exists():
                        zf.write(self.order_file, arcname="profiles_order.json")
            messagebox.showinfo("Export", f"Экспортировано {len(profiles)} профилей:\n{dest}")
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def import_all_profiles(self):
        file_path = filedialog.askopenfilename(
            title="Import all profiles",
            filetypes=[
                ("ZIP or JSON", "*.zip *.json"),
                ("ZIP archive", "*.zip"),
                ("JSON bundle", "*.json"),
                ("All Files", "*.*"),
            ],
        )
        if not file_path:
            return

        src = Path(file_path)
        imported = 0
        skipped = 0
        overwritten = 0
        new_order = None

        # спрашиваем один раз про перезапись, если найдём конфликты
        overwrite_mode = None  # None=спросить, True=перезаписывать, False=пропускать

        def _should_overwrite(name: str) -> bool:
            nonlocal overwrite_mode
            dest = self.profiles_dir / f"{name}.json"
            if not dest.exists():
                return True
            if overwrite_mode is not None:
                return overwrite_mode
            ans = messagebox.askyesnocancel(
                "Conflict",
                f"Профиль '{name}' уже существует.\n\n"
                "Yes — перезаписать\n"
                "No — пропустить\n"
                "Cancel — прервать импорт",
            )
            if ans is None:
                raise InterruptedError("cancelled")
            # если профилей много — спросить "применить ко всем"
            if ans is True or ans is False:
                # запоминаем выбор? Для простоты — применяем ко всем оставшимся
                # пользователь может отменить и запустить заново для гранулярности
                pass
            return ans

        def _save_profile(name: str, data: dict):
            nonlocal imported, skipped, overwritten
            safe_name = name.strip().replace("/", "_").replace("\\", "_").replace(":", "_")
            if not safe_name:
                skipped += 1
                return
            dest = self.profiles_dir / f"{safe_name}.json"
            exists = dest.exists()
            try:
                if exists:
                    try:
                        do_write = _should_overwrite(safe_name)
                    except InterruptedError:
                        raise
                    if not do_write:
                        skipped += 1
                        return
                    overwritten += 1 if exists else 0
                else:
                    pass
                with open(dest, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                imported += 1
            except InterruptedError:
                raise
            except Exception:
                skipped += 1

        try:
            if src.suffix.lower() == ".zip":
                with zipfile.ZipFile(src, "r") as zf:
                    # защита от ZipSlip — игнорируем пути с директориями
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        raw_name = Path(info.filename).name
                        if not raw_name:
                            continue
                        if raw_name == "profiles_order.json":
                            try:
                                new_order = json.loads(zf.read(info).decode("utf-8"))
                            except Exception:
                                pass
                            continue
                        if not raw_name.lower().endswith(".json"):
                            continue
                        stem = Path(raw_name).stem
                        try:
                            data = json.loads(zf.read(info).decode("utf-8"))
                        except Exception:
                            skipped += 1
                            continue
                        # валидация: похоже ли на auth.json (должен содержать tokens или account_id)
                        if not isinstance(data, dict):
                            skipped += 1
                            continue
                        _save_profile(stem, data)
            elif src.suffix.lower() == ".json":
                with open(src, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if isinstance(payload, dict) and "profiles" in payload and isinstance(payload["profiles"], dict):
                    # bundle формат
                    new_order = payload.get("order")
                    for name, data in payload["profiles"].items():
                        if not isinstance(data, dict):
                            skipped += 1
                            continue
                        _save_profile(name, data)
                elif isinstance(payload, dict) and "tokens" in payload:
                    # одиночный auth.json, импортируем как один профиль
                    default_name = src.stem
                    try:
                        info = extract_auth_info(src)
                        if info.get("email") and info["email"] != "—":
                            default_name = info["email"].split("@")[0]
                    except Exception:
                        pass
                    _save_profile(default_name, payload)
                else:
                    messagebox.showerror("Import", "Неизвестный формат JSON. Ожидается bundle с ключом 'profiles' или одиночный auth.json с 'tokens'.")
                    return
            else:
                messagebox.showerror("Import", "Поддерживаются только .zip и .json файлы.")
                return

            if new_order and isinstance(new_order, list):
                # фильтруем порядок — оставляем только реально существующие профили
                existing = {p.stem for p in self.profiles_dir.glob("*.json")}
                filtered = [n for n in new_order if n in existing]
                # добавляем новые профили которых не было в порядке в конец
                for p in self.profiles_dir.glob("*.json"):
                    if p.stem not in filtered:
                        filtered.append(p.stem)
                try:
                    with open(self.order_file, "w", encoding="utf-8") as f:
                        json.dump(filtered, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            self.refresh_profiles()
            # если порядок импортирован — сохраняем отображение
            if new_order:
                self._save_profiles_order()
            self.fetch_all_accounts_async()
            messagebox.showinfo(
                "Import",
                f"Импорт завершён:\n"
                f"Добавлено/обновлено: {imported}\n"
                f"Перезаписано: {overwritten}\n"
                f"Пропущено: {skipped}",
            )
        except InterruptedError:
            self.refresh_profiles()
            messagebox.showwarning("Import", f"Импорт прерван.\nИмпортировано: {imported}, пропущено: {skipped}")
        except zipfile.BadZipFile:
            messagebox.showerror("Import", "Повреждённый ZIP-архив.")
        except Exception as e:
            messagebox.showerror("Import error", str(e))
