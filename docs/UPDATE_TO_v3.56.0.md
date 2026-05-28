# Обновление GhostVPN bot до upstream v3.56.0

Дата плана: 2026-05-28.
Текущий HEAD форка: `03a690d4` (после merge upstream v3.55.0).
Цель: `BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot@v3.56.0` (2026-05-16, коммит `d4ada356`).

---

## 1. Что нового в v3.56.0 (главное)

Из CHANGELOG релиза:

**Новые фичи**

- `antilopay`: `apay-tag` site-verification из кабинета.
- `deleted-users`: автоматическое восстановление пользователя по подписи Telegram, дружелюбный 403 в кабинете, мердж OAuth-аккаунтов.
- `devices`: per-user локальные алиасы для HWID-устройств (новые поля в БД → **новая alembic-миграция**).

**Bug fixes (затрагивающие платежи — внимание)**

- `payment`: дедуп пост-топап уведомлений + уважение `MAIN_MENU_MODE=cabinet`.
- `stars`: правильное начисление по сумме из payload (не stars × rate), дефолтный курс `1.3 → 1.0`, **новая миграция** удаляющая `TELEGRAM_STARS_RATE_RUB` из `system_settings`.
- `freekassa`: чтение client IP из `X-Forwarded-For`.
- `lava`: подпись через заголовок `Signature` (raw body HMAC).

**Bug fixes (кабинет/RBAC/уведомления/подписки)**

- `cabinet`: multi-kty OIDC JWKS (RSA + EC + OKP), tighten algorithm list, align PyJWT pin.
- `oauth`: 409 вместо 500 при неподтверждённом email.
- `notifications`: graceful shutdown, lifespan-миграция, redact bot token, fix race condition при бурсте webhook от RemnaWave.
- `subscription`: жёсткий лимит 36 символов username RemnaWave (в т.ч. в admin extend / sync / bulk-sync), фикс падения старта бота из-за повторного импорта `SubscriptionStates`.
- `referral`: 3 security gaps + дедуп race + lazy-create bot для cabinet attach.
- `admin`: разрешён custom device count при `MAX_DEVICES_LIMIT=0`.
- `devices`: harden alias upsert + multi-tariff hwid validation.
- `backup`: graceful skip пустых/битых файлов.

---

## 2. Анализ кастомизаций форка (mentyrop/ghostvpnbotfork)

Реальный (без CRLF) diff `main↔upstream/v3.55.0` — ~3.1k строк, ~28 файлов. Основные «острова»:

| Подсистема | Файлы | Риск конфликта в v3.56.0 |
|---|---|---|
| **Robokassa (новый платежный метод)** | `app/services/robokassa_service.py`, `app/services/payment/robokassa.py`, `app/database/crud/robokassa.py`, `app/handlers/balance/robokassa.py`, `migrations/.../0054_add_robokassa_payments.py`, `.env.example`, `app/config.py`, `app/services/payment_service.py`, `app/services/payment/__init__.py`, `app/services/payment_method_config_service.py`, `app/services/payment_search_service.py`, `app/services/payment_verification_service.py`, `app/utils/payment_utils.py`, `app/webserver/payments.py`, `app/keyboards/inline.py`, `app/handlers/balance/main.py`, `app/handlers/start.py`, `app/cabinet/routes/balance.py`, `app/cabinet/routes/admin_payments.py`, `app/database/models.py`, локали | **СРЕДНИЙ.** Upstream v3.56.0 правит `payment_*`, `stars`, `freekassa`, `lava` — может пересечься с твоими правками в `payment_service.py`, `payment_search_service.py`, `payment_verification_service.py`, `payment_utils.py`, `webserver/payments.py`. |
| **Remnawave external squads** | `app/services/remnawave_service.py` (метод `get_all_squads()` подмешивает external) | НИЗКИЙ — upstream не трогал этот метод. |
| **`payment_provider_table_guard.py`** | целый файл — гарантирует существование таблиц провайдеров на старте | НИЗКИЙ. |
| **Локальные ensure-миграции (`0083, 0087..0092`)** | защитные DDL-миграции для paypear/rollypay/aurapay/etoplatezhi/antilopay/jupiter/donut/lava/apple | **ВЫСОКИЙ для нумерации** — v3.56.0 добавит свои `0083+`, нужна перенумерация. |
| **Docker / инфра** | `docker-compose.yml`, `docker-compose.local.yml`, `vpn_logo.png` | НИЗКИЙ — upstream редко трогает. |
| **Документация** | `docs/FORK_CUSTOMIZATION_CHECKLIST.md` | НИЗКИЙ. |

---

## 3. Стратегия мерджа

### 3.1. Конфликтные файлы — что брать

| Категория | Действие |
|---|---|
| Чисто Robokassa-файлы (новые в форке) | **ours** (наша версия) — апстрим о них не знает |
| `app/services/payment_*.py`, `app/utils/payment_utils.py`, `app/webserver/payments.py` | **смерджить руками**: оставить Robokassa-блоки + принять upstream-патчи (stars/freekassa/lava/dedup) |
| `app/services/remnawave_service.py` | если конфликт — **ours** (но скорее всего конфликта не будет) |
| `docker-compose*.yml`, `vpn_logo.png` | **ours** |
| `app/database/models.py` (`PaymentMethod.ROBOKASSA`, модель `RobokassaPayment`) | **смерджить руками** — оставить Robokassa-enum + принять новые поля upstream (per-user device aliases, deleted-users fields) |
| `.env.example` | **смерджить руками**: добавить блок `ROBOKASSA_*` к новым переменным upstream |
| `app/config.py` | **смерджить руками**: оставить `ROBOKASSA_*` поля и методы |
| `migrations/alembic/versions/0083+` (новые upstream) | **theirs** для файлов, потом перенумеровать (см. §3.2) |
| Локальные `0083_ensure_paypear_payments_exists.py` … `0092_*` | **ours** |
| `app/localization/locales/*.json`, `app/localization/default_locales/*.yml` | смерджить, оставив наши ключи `PAYMENT_ROBOKASSA*` |

### 3.2. Цепочка alembic-миграций

Текущая локальная цепочка обрывается на:

```
… → 0091_ensure_rollypay_aurapay_etoplatezhi_payments → 0092_ensure_upstream_base_provider_tables (HEAD)
```

В upstream v3.56.0 после `0082_add_open_url_direct_to_payment_method_config` появятся новые миграции (минимум одна — `stars: drop TELEGRAM_STARS_RATE_RUB`, плюс возможно для `devices` и `deleted-users`). Их нумерация будет конфликтовать с нашими `0083, 0087..0092`.

**Алгоритм фикса (полу-ручной):**

1. После merge будут существовать обе цепочки.
2. Для каждого нового upstream-файла:
   - Переименовать `00XX_<upstream_name>.py` → следующий свободный номер после `0092`, например `0093_<upstream_name>.py`.
   - Внутри файла поправить:
     - `revision = "0093_<upstream_name>"`
     - `down_revision = "0092_ensure_upstream_base_provider_tables"` для первой;
     - для второй/третьей — указывать предыдущую переименованную.
3. Локально поднять копию БД и прогнать `alembic upgrade head` — не должно быть ошибок «multiple heads» или «can't locate revision».

> Скрипт `scripts/update_to_v3.56.0.sh` находит новые upstream-миграции и **только перечисляет их** — переименование сделай руками, чтобы не сломать DDL (риск опечатки в `revision`).

### 3.3. Что нужно сохранить из бизнес-настроек

Ничего из этого **не лежит в репозитории** — это переменные окружения на сервере:

- `ROBOKASSA_*` (merchant, password1/2, IP allowlist, receipt-параметры).
- `BOT_TOKEN`, `ADMIN_IDS`, `DATABASE_URL`, `REDIS_URL`.
- `PAL24_*`, `PLATEGA_*`, `WATA_*`, `YOOKASSA_*`, `CRYPTOBOT_*`, `TRIBUTE_*`, `STARS_*` и т.д.

Скрипт деплоя бэкапит `.env` перед `git pull` (см. §5).

---

## 4. Пошагово — локальный мердж

> Запускать в **git bash** (приходит вместе с Git for Windows) или WSL,
> из корня `C:\Users\Никита\Documents\GhostVPN\ghostvpnbot`.

```bash
# 1) убедиться что working tree чистый (CRLF-«modified» допустимы — они не настоящие)
git status

# 2) запустить скрипт обновления
bash scripts/update_to_v3.56.0.sh
```

Что делает скрипт:

1. Проверяет/добавляет remote `upstream`.
2. Включает `merge.renormalize true` (исключает ложные CRLF-конфликты).
3. Создаёт backup-ветку `backup/pre-v3.56.0-<timestamp>`.
4. `git fetch upstream --tags`.
5. `git merge --no-ff --no-commit v3.56.0`.
6. На критичных путях (Robokassa, docker-compose, ensure-миграции) принудительно делает `git checkout --ours`.
7. Перечисляет оставшиеся конфликты с подсказками.
8. После того как ты разрешишь конфликты руками и сделаешь `git add` → доделает коммит.
9. Прогоняет `python -m compileall app main.py migrations` для проверки синтаксиса.
10. Выводит инструкцию по push и деплою.

Если скрипт завершился с кодом `2` (есть конфликты вне OURS-листа) — разрешаешь конфликты, потом запускаешь `bash scripts/update_to_v3.56.0.sh` повторно (он подхватит merge state).

---

## 5. Push в свой GitHub

После того как скрипт зелёный и ты глазами просмотрел `git log --oneline backup/pre-v3.56.0-*..HEAD`:

```bash
# тэг для удобства
git tag -a fork-v3.56.0 -m "Merge upstream v3.56.0"

# push
git push origin main
git push origin fork-v3.56.0
```

---

## 6. Деплой на сервер (Docker Compose)

На сервере, из каталога с `docker-compose.yml`:

```bash
# 0) если scripts/ еще нет — скопируй сначала или сделай git pull
cd /opt/ghostvpnbot   # путь подставить свой
git pull origin main

# 1) выполнить деплой одной командой
bash scripts/server_deploy_v3.56.0.sh
```

Скрипт:

1. Делает `cp .env .env.backup.<ts>`.
2. Снимает `pg_dump` в `backup_db_<ts>.sql.gz`.
3. `git fetch && git pull --ff-only origin main` (со `stash` если на сервере есть локальные правки).
4. `docker compose build --pull bot`.
5. `docker compose up -d`.
6. Ждёт healthy + выводит последние 40 строк логов.

### Если скрипт нельзя использовать — вручную

```bash
cd /opt/ghostvpnbot
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# дамп БД
docker exec remnawave_bot_db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | gzip > backup_db_$(date +%Y%m%d_%H%M%S).sql.gz

# обновить код
git fetch origin
git pull --ff-only origin main

# пересобрать и поднять
docker compose pull
docker compose build --pull bot
docker compose up -d

# логи
docker compose logs -f --tail=100 bot

# проверить alembic
docker compose exec bot alembic current
docker compose exec bot alembic heads
```

---

## 7. Откат, если что-то пошло не так

**Локально (до push):**

```bash
git reset --hard backup/pre-v3.56.0-<timestamp>
```

**На сервере (после push и pull):**

```bash
cd /opt/ghostvpnbot
git reset --hard ORIG_HEAD            # вернуться к предыдущему HEAD до pull
docker compose build --pull bot
docker compose up -d

# восстановить БД (если миграции v3.56.0 успели применится)
gunzip -c backup_db_<ts>.sql.gz | docker exec -i remnawave_bot_db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

---

## 8. После деплоя — что проверить руками

- [ ] Бот стартует, отвечает в Telegram.
- [ ] `/start` для свежего пользователя.
- [ ] Покупка любой подписки через **Robokassa** (наша платёжка).
- [ ] Webhook Result URL Robokassa (`POST /robokassa/result`) возвращает `OK<InvId>`.
- [ ] Старая Stars-оплата корректно начисляет (изменился расчёт суммы).
- [ ] Кабинет открывается, OAuth-вход (если используешь) — без 500.
- [ ] `docker compose logs --tail=200 bot` без panic/SyntaxError/alembic errors.
- [ ] `docker compose exec bot alembic current` == последняя ваша миграция.
