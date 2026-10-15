---
feature: activity-type
status: delivered
updated: 2026-10-16
branch: feat/activity-type-selector
commits: 00befa9..c7dd94a
---

# Activity Type Selector (Listening / Playing)

## Report

**What was built** — В окне «Настройки → Активность» добавлен выпадающий список «Тип активности» с вариантами «Слушает» (дефолт, LISTENING=2) и «Играет» (PLAYING=0). Выбор сохраняется в settings.ini (`activity_type`), корректно читается при старте (включая старые файлы без ключа и мусорные значения — fallback LISTENING) и попадает в Discord Rich Presence payload. Смена типа применяется на следующем цикле worker без переподключения.

**Verification** — `ruff check .` — PASS. Smoke: default LISTENING; save/load PLAYING roundtrip; missing key → LISTENING; garbage → LISTENING; `build_payload` отражает тип (0/2); `pypresence.ActivityType` принимает оба значения. Offscreen UI: combo «Слушает»/«Играет», dirty-check (isHidden True→False→True), save пишет PLAYING. Все — PASS.

**Journey log** —
1. Каркас `activity_type` уже был в Settings/config/presence, но enum был обрезан, load отсутствовал, payload хардкодил LISTENING — фича почти целиком про восстановление, а не про новый код.
2. `git worktree add` заблокирован изолированной сессией; работали веткой `feat/activity-type-selector` в текущем checkout (согласовано с пользователем).
3. `isVisible()` на save_button в offscreen-тесте врал из-за невидимого parent; заменили на `isHidden()`.
4. Здесь-строки PowerShell для smoke-тестов ломаются на f-string — временный скрипт файлом надёжнее.

## [S1] Problem

Issue #180: Discord-активность «Слушает» всегда стоит ниже игры, поэтому музыка перекрывается статусом запущенной игры. В до-3.0 версии можно было переключить тип активности на «Играет» (Playing) и получить тот же приоритет, что у игр. В v3.0 опцию удалили: `ActivityType` обрезан до `LISTENING`, `build_payload` жёстко шлёт `LISTENING`, значение `activity_type` пишется в settings.ini, но не читается, и в UI нет способа выбрать тип.

## [S2] Design

Поведение: в окне «Настройки → Активность» есть выпадающий список **«Тип активности»** с вариантами:

| Значение | Discord RPC `activity_type` | Как выглядит в профиле |
|---|---|---|
| Слушает (default) | `2` (LISTENING) | «Слушает …» — прежнее поведение |
| Играет | `0` (PLAYING) | «Играет в …» — приоритет как у игр |

Контракты:

1. **models.** `ActivityType` содержит `PLAYING = 0` и `LISTENING = 2`. Дефолт `Settings.activity_type` — `LISTENING`.
2. **config.** `ConfigStore._load` читает `activity_type` через `enum_value` (имя ключа `activity_type`, fallback `LISTENING` при отсутствии/мусоре). `save` пишет ключ. Старые settings.ini без ключа открываются с `LISTENING`.
3. **presence.** `build_payload` кладёт `settings.activity_type.value`. Остальные поля payload не зависят от типа.
4. **discord.** Слой конвертирует `activity_type` в `pypresence.ActivityType` и публикует. Смена типа меняет payload, `_equivalent` это видит и шлёт update без переподключения (client_id не зависит от activity_type).
5. **settings UI.** В странице «Активность» строка `_row(..., "Тип активности", ...)` с `Dropdown`-combo («Слушает» / «Играет»). Контрол участвует в `_form_settings`, `_update_dirty` и сохранении. Подписи на русском.
6. **Применение.** Worker читает `config.settings` каждый цикл; при смене сбрасывает `PresenceGrace`, следующий `build_payload` уходит с новым `activity_type`. Явный reconnect не требуется.

## [S3] Out of Scope

- Другие типы Discord-активности (WATCHING, COMPETING, CUSTOM, STREAMING).
- Смена Discord application / client_id под тип активности.
- Локализация UI настроек (подписи Discord-статуса уже локализованы через `Language`).
- Изменение `display_format` / `status_name` в зависимости от типа.
- Приоритет относительно конкретных игр Discord (клиентская сортировка, RPC её не контролирует).

## Tasks

- [x] T1: Вернуть `ActivityType.PLAYING = 0` в `ymrpc/models.py` — acceptance: enum содержит PLAYING=0 и LISTENING=2, дефолт Settings.activity_type == LISTENING (covers: S2)
- [x] T2: Загружать `activity_type` в `ConfigStore._load` — acceptance: settings.ini с activity_type=PLAYING открывается как PLAYING; файла без ключа — LISTENING; мусор — LISTENING (covers: S2; depends: T1)
- [x] T3: Передавать `settings.activity_type.value` из `build_payload` — acceptance: payload при PLAYING содержит activity_type=0, при LISTENING — 2 (covers: S2; depends: T1)
- [x] T4: Dropdown «Тип активности» в `SettingsDialog` (строка «Активность», dirty-check, `_form_settings`) — acceptance: выбор «Играет»/«Слушает» попадает в сохраняемый Settings и валидируется save (covers: S2; depends: T1)
- [x] T5: Smoke-проверка load/save/payload и `ruff check` — acceptance: roundtrip PLAYING/LISTENING, payload отражает тип, ruff без ошибок (covers: S2; depends: T2, T3, T4)
