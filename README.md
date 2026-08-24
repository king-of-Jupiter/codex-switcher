# Codex Switcher

GUI-менеджер профилей Codex / ChatGPT: переключение аккаунтов через `~/.codex/auth.json`, просмотр email/плана из JWT, импорт профиля вставкой или файлом, drag-and-drop сортировка. Python 3 + Tkinter, без сторонних зависимостей.

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

## Запуск из исходников

```bash
python main.py   # Python 3.10+ с tkinter (входит в стандартные сборки)
```
