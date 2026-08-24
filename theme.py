import sys

# ================= VERCEL DESIGN TOKENS =================
THEME = {
    "bg_root": "#000000",
    "bg_surface": "#0a0a0a",
    "bg_subtle": "#141414",
    "bg_hover": "#1f1f1f",
    "border_subtle": "#222222",
    "border_active": "#383838",
    "text_primary": "#ededed",
    "text_secondary": "#888888",
    "text_muted": "#555555",
    "accent_white": "#ffffff",
    "accent_blue": "#0070f3",
    "accent_green": "#10b981",
    "accent_purple": "#a855f7",
    "accent_cyan": "#06b6d4",
    "accent_red": "#f43f5e",
    "badge_plus_bg": "#052e16",
    "badge_plus_fg": "#4ade80",
    "badge_ticket_bg": "#2e1065",
    "badge_ticket_fg": "#c084fc",
}


def apply_dark_titlebar(window):
    """Включение темного заголовка на Windows 10/11."""
    if sys.platform == "win32":
        try:
            from ctypes import byref, c_int, sizeof, windll

            HWND = windll.user32.GetParent(window.winfo_id())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            windll.dwmapi.DwmSetWindowAttribute(
                HWND,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                byref(c_int(1)),
                sizeof(c_int),
            )
        except Exception:
            pass
