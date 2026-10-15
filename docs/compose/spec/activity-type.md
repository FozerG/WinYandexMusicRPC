---
feature: activity-type
status: in-progress
updated: 2026-10-16
branch: feat/activity-type-selector
commits: 
---

# Activity Type Selector (Listening / Playing)

## Report

## [S1] Problem

Issue #180: Discord-активность «Слушает» всегда стоит ниже игры, поэтому музыка перекрывается статусом запущенной игры. В до-3.0 версии можно было переключить тип активности на «Играет» (Playing) и получить тот же приоритет, что у игр. В v3.0 опцию удалили: `ActivityType` обрезан до `LISTENING`, `build_payload` жёстко шлёт `LISTENING`, значение `activity_type` пишется в settings.ini, но не читается, и в UI нет способа выбрать тип.

## [S2] Design

Поведение: в окне «Настройки → Активность» появляется выпадающий список **«Тип активности»** с вариантами:

| Значение | Discord RPC `activity_type` | Как выглядит в профиле |
|---|---|---|
| Слушает (default) | `2` (LISTENING) | «Слушает …» — текущее поведение |
| Играет | `0` (PLAYING) | «Играет в …» — приоритет как у игр |

Контракты:

1. **models.** `ActivityType` снова содержит `PLAYING = 0` и `LISTENING = 2`. Дефолт `Settings.activity_type` — `LISTENING` (текущее поведение не меняется без действия пользователя).
2. **config.** `ConfigStore._load` читает `activity_type` через существующий `enum_value` (имя ключа `activity_type`, fallback `LISTENING` при отсутствии/мусоре). `save` уже пишет ключ — менять не нужно. Старые settings.ini без ключа продолжают открываться с `LISTENING`.
3. **presence.** `build_payload` кладёт `settings.activity_type.value` вместо хардкода. Остальные поля payload (details/state/name/buttons/timestamps) не зависят от типа.
4. **discord.** Слой уже конвертирует `activity_type` в `pypresence.ActivityType` и публикует — менять не нужно. Смена типа меняет payload, `_equivalent` это увидит и пришлёт update без переподключения (client_id не зависит от activity_type).
5. **settings UI.** В странице «Активность» строка `_row(activity, "Тип активности", "Слушает — под именем Discord; Играет — приоритет как у игр", self.activity_type)` с `Dropdown`-combo, как у «Язык статуса». Контрол участвует в `_form_settings`, `_update_dirty` (подключение `currentIndexChanged`) и сохранении. Подписи только на русском — UI приложения везде русский.
6. **Применение.** Worker читает `config.settings` каждый цикл; при смене сбрасывает `PresenceGrace` и в следующем `build_payload` уходит новый `activity_type`. Явный reconnect не требуется.

## [S3] Out of Scope

- Другие типы Discord-активности (WATCHING, COMPETING, CUSTOM, STREAMING).
- Смена Discord application / client_id под тип активности.
- Локализация UI настроек (только подписи Discord-статуса уже локализованы через `Language`).
- Изменение `display_format` / `status_name` в зависимости от типа.
- Приоритет относительно конкретных игр Discord (это клиентская сортировка, RPC её не контролирует).

## Tasks

- [ ] T1: Вернуть `ActivityType.PLAYING = 0` в `ymrpc/models.py` — acceptance: enum содержит PLAYING=0 и LISTENING=2, дефолт Settings.activity_type == LISTENING (covers: S2)
- [ ] T2: Загружать `activity_type` в `ConfigStore._load` — acceptance: settings.ini с activity_type=PLAYING открывается как PLAYING; файла без ключа — LISTENING; мусор — LISTENING (covers: S2; depends: T1)
- [ ] T3: Передавать `settings.activity_type.value` из `build_payload` — acceptance: payload при PLAYING содержит activity_type=0, при LISTENING — 2 (covers: S2; depends: T1)
- [ ] T4: Dropdown «Тип активности» в `SettingsDialog` (строка «Активность», dirty-check, `_form_settings`) — acceptance: выбор «Играет»/«Слушает» попадает в сохраняемый Settings и валидируется save (covers: S2; depends: T1)
- [ ] T5: Smoke-проверка load/save/payload и `ruff check` — acceptance: roundtrip PLAYING/LISTENING, payload отражает тип, ruff без ошибок (covers: S2; depends: T2, T3, T4)
