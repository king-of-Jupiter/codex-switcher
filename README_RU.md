[English](README.md) | **Русский**

# Codex Switcher

Десктопный менеджер профилей Codex / ChatGPT: переключение аккаунтов через `~/.codex/auth.json`, живые квоты каждого аккаунта (5-часовое и 7-дневное окно, reset tickets, кредиты), импорт профиля вставкой или файлом, сортировка перетаскиванием, экспорт и импорт всех аккаунтов разом (ZIP или JSON bundle). Все данные приложения лежат в одной папке `~/.codex/codex-switcher/` (старая `~/.codex/profiles` мигрирует автоматически).

Сделано на [Tauri 2](https://tauri.app): бэкенд на Rust, интерфейс на TypeScript + Vite. Работает на Windows, macOS и Linux.

![Интерфейс приложения](docs/screen.png)

## Установка

Скачайте сборку со страницы [Releases](../../releases):

| Файл | Платформа |
|---|---|
| `Codex Switcher_x.y.z_x64-setup.exe` / `.msi` | Windows 10/11 |
| `Codex Switcher_x.y.z_aarch64.dmg` | macOS Apple Silicon |
| `Codex Switcher_x.y.z_x64.dmg` | macOS Intel |
| `.AppImage` / `.deb` / `.rpm` | Linux x64 |

**macOS:** сборка подписана ad-hoc (без нотаризации). При первом запуске: правый клик по приложению, затем «Открыть», либо
`xattr -cr "/Applications/Codex Switcher.app"`.

## Возможности

- Активный аккаунт наверху: 5-часовое и 7-дневное окна крупными цифрами, время сброса, план, reset tickets и кредиты
- Таблица профилей с живыми квотами для каждого сохранённого аккаунта; проверка при запуске и по кнопке **Check quotas**
- **Activate** (или двойной клик / Enter по строке) копирует профиль в `auth.json` (старый уходит в `auth.json.bak`) и по желанию перезапускает ChatGPT/Codex
- **New account**: удаляет активный `auth.json` и перезапускает ChatGPT/Codex для входа; затем **Save active** сохраняет его как профиль
- Импорт одного профиля: **Paste JSON** (аккаунт определяется прямо при вставке) или **Import file**
- **Export all / Import all**: ZIP (по файлу на профиль + `profiles_order.json`) или JSON bundle; при импорте можно выбрать, какие существующие профили перезаписать
- Сортировка перетаскиванием за ручку или Alt+↑ / Alt+↓; F2 переименовывает, Delete удаляет
- Вкладка **Raw response** с последним JSON квот активного аккаунта
- Истёкшие access-токены обновляются автоматически; новые токены пишутся и в `auth.json`, и в его сохранённый профиль, чтобы они не расходились

## Хранение

- `~/.codex/auth.json`: активный аккаунт (общий с Codex CLI)
- `~/.codex/codex-switcher/profiles/*.json`: сохранённые профили
- `~/.codex/codex-switcher/profiles_order.json`: пользовательский порядок

## Запуск из исходников

Нужны [Node.js](https://nodejs.org) 20+, [Rust](https://rustup.rs) stable и [зависимости Tauri](https://tauri.app/start/prerequisites/) для вашей ОС (WebView2 на Windows, Xcode CLT на macOS, `libwebkit2gtk-4.1-dev` на Linux).

```bash
npm install
npm run tauri dev     # запустить приложение
npm run tauri build   # собрать установщики в src-tauri/target/release/bundle
```

`npm run dev` без Tauri поднимает интерфейс на http://localhost:1420 с мок-данными, чтобы верстать в браузере.

## CI / CD

`.github/workflows/build.yml` запускается на каждый push и pull request: линт (rustfmt, clippy), Rust-тесты и проверка типов UI, затем сборка под Windows, macOS (arm64 и Intel) и Linux с загрузкой артефактов. Пуш тега `v*` выставляет версию из тега и публикует GitHub Release со всеми установщиками:

```bash
git tag v0.2.0 && git push origin v0.2.0
```
