[English](README_EN.md) | **Русский**

# Codex Switcher

GUI-менеджер профилей Codex / ChatGPT: переключение аккаунтов через `~/.codex/auth.json`, просмотр email/плана из JWT, импорт профиля вставкой или файлом, drag-and-drop сортировка, массовый экспорт/импорт всех аккаунтов (ZIP или JSON bundle). Все данные приложения хранятся в единой папке `~/.codex/codex-switcher/` (автоматическая миграция из `~/.codex/profiles`). Python 3 + Tkinter, без сторонних зависимостей.

![Интерфейс приложения](docs/screen.png)

## Установка

Скачайте установщик со страницы [Releases](../../releases):

| Файл | Платформа |
|---|---|
| `CodexSwitcher-x.y.z-setup-x64.exe` | Windows 10/11 (установщик) |
| `CodexSwitcher-x.y.z-macos-arm64.dmg` | macOS Apple Silicon |
| `CodexSwitcher-x.y.z-macos-intel.dmg` | macOS Intel |

**macOS:** сборка подписана ad-hoc (без нотаризации). При первом запуске: правый клик по приложению → «Открыть», либо
`xattr -cr "/Applications/Codex Switcher.app"`.

## Возможности

- Таблица всех профилей с live-квотами (7-day quota, reset tickets)
- Переключение активного `auth.json` в один клик + авто-рестарт ChatGPT/Codex
- Импорт: Paste JSON, Import File (один профиль)
- **Bulk Export / Import All**: экспорт всех профилей в `ZIP` (по файлу на профиль + `profiles_order.json`) или в `JSON bundle`; импорт из ZIP/JSON с сохранением порядка и опцией перезаписи
- Drag-and-drop сортировка и сохранение порядка

## Запуск из исходников

```bash
python main.py   # Python 3.10+ с tkinter (входит в стандартные сборки)
```
