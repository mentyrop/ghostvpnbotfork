# Чеклист кастомизаций GhostVPN / mentyrop относительно Bedolaga upstream

Используй после **чистого форка** [BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot](https://github.com/BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot): сравни эти пути и перенеси diff (или `git checkout OLD_BRANCH -- <path>` со старого клона).

**Явно не переносить по запросу:** правки в `app/handlers/admin/backup.py` (загрузка `.tar` / колбэки `backup_restore_uploaded_*`) — считаются ненужными.

---

## 1. Robokassa (платёжка + вебхук + БД)

| Файл | Назначение |
|------|------------|
| `app/services/robokassa_service.py` | Подписи, URL оплаты, Receipt (ФЗ-54), проверка IP Result URL |
| `app/services/payment/robokassa.py` | `RobokassaPaymentMixin`: создание платежа, `process_robokassa_webhook`, финализация |
| `app/database/crud/robokassa.py` | CRUD по таблице `robokassa_payments` |
| `app/database/models.py` | `PaymentMethod.ROBOKASSA`, модель `RobokassaPayment` |
| `app/config.py` | Поля `ROBOKASSA_*`, методы `is_robokassa_enabled()`, `get_robokassa_display_name()` |
| `app/services/payment_service.py` | Наследование от `RobokassaPaymentMixin` |
| `app/services/payment/__init__.py` | Экспорт `RobokassaPaymentMixin` |
| `app/handlers/balance/robokassa.py` | Хендлеры пополнения |
| `app/handlers/balance/main.py` | Регистрация callback `topup_robokassa`, маршрут суммы |
| `app/keyboards/inline.py` | Кнопка Robokassa в меню пополнения |
| `app/utils/payment_utils.py` | Порядок методов (Robokassa первым при включении), проверка `method_id` |
| `app/webserver/payments.py` | GET/POST `ROBOKASSA_WEBHOOK_PATH`, вызов `process_robokassa_webhook` |
| `app/services/payment_verification_service.py` | Ожидающие платежи Robokassa, `_fetch_robokassa_payments` |
| `app/services/payment_method_config_service.py` | Конфиг метода `robokassa` |
| `app/services/admin_notification_service.py` | Подпись уведомления для `robokassa` |
| `app/handlers/start.py` | `RobokassaPayment` в очистке при восстановлении удалённого пользователя |
| `app/cabinet/routes/balance.py` | `PaymentMethod.ROBOKASSA` в списке методов |
| `app/cabinet/routes/admin_payments.py` | То же для админки |
| `migrations/alembic/versions/0054_add_robokassa_payments.py` | Таблица `robokassa_payments` (revision `0054` → `0053` в текущем форке) |
| `.env.example` | Блок `ROBOKASSA_*` |
| `locales/ru.json`, `locales/en.json` | Ключи `PAYMENT_ROBOKASSA`, `ROBOKASSA_PAYMENT_CREATED`, `ROBOKASSA_ENTER_AMOUNT`, `ROBOKASSA_NOT_AVAILABLE` |
| `docs/DEPLOY_FULL_STEPS.md` | Раздел про Robokassa / Result URL / отладка |
| `docs/PAYMENT_SYSTEMS_COMPARISON.md` | Строки про Robokassa |

Переменные в **боевом `.env`**: скопировать с сервера (`ROBOKASSA_*`), не коммитить.

---

## 2. Remnawave: internal + external сквады в синке

| Файл | Назначение |
|------|------------|
| `app/services/remnawave_service.py` | Метод `get_all_squads()`: после internal вызывает `api.get_external_squads()`, добавляет в список с полями `uuid`, `name`, `members_count`, `inbounds_count` (0), `inbounds` ([]), без дубликатов по `uuid` |

API уже содержит `get_external_squads` в `app/external/remnawave_api.py` (проверь на форке, что версия панели совместима).

---

## 3. Деплой / Docker / миниапп (твоя инфраструктура)

По истории коммитов и diff — отдельно от апстрима обычно:

| Путь | Заметка |
|------|---------|
| `docker-compose.yml` | Сеть `172.20.0.x`, `DATABASE_URL` с IP Postgres, `extra_hosts`, MTU и т.д. |
| `docker-compose.local.yml` | Локальные отличия |
| `deploy/nginx-bot-port-8443.conf.example` | Пример nginx |
| `deploy/nginx-bot.ghostvpn.cc.conf.example` | Пример под домен |
| `docs/DEPLOY_FULL_STEPS.md` | Полные шаги деплоя |
| `docs/DEPLOY_SERVER_AND_GIT.md` | Git / сервер |
| `docs/MINIAPP_BOT_GHOSTVPN_CC.md` | Миниапп |
| `miniapp/` | `index.html`, `app-config.json` при необходимости |

Точный diff — `git diff upstream/main main -- docker-compose.yml deploy/ docs/DEPLOY*.md miniapp/` (на старом клоне, где есть `upstream`).

---

## 4. Прочие коммиты из истории (без полного списка файлов в чате)

В `git log` встречались сообщения вроде: **Webhooks for payment**, **Receipt**, **Fixed Robokassa**, **Fixed Squad**, **Fixed channel sub**, **DATABASE_URL / compose**. Часть уже покрыта блоками выше; остаток — через:

```bash
git log upstream/main..main --oneline   # если появится общий предок
# или сравнение деревьев:
git diff upstream/main main --stat
```

и точечный перенос файлов.

---

## 5. Как перенести в новый форк (порядок)

1. `git clone` форка Bedolaga → новая папка, ветка `main` = upstream.
2. Добавить `remote old` на старый `mentyrop/ghostvpnbot`, `git fetch old`.
3. Для каждого пути из таблиц: `git checkout old/main -- <path>` (или трёхсторонний merge в IDE).
4. **Миграции:** не копировать папку `migrations/` целиком; либо одна новая ревизия «add robokassa_payments» поверх `head` апстрима, либо ручное слияние Alembic.
5. `docker compose build`, тест оплаты и webhook на стенде.

---

## 6. Про «запомнит ли Cursor всё»

Нет: другой чат не видит этот. Источник правды — **этот файл + старый репозиторий/ветка `backup-*` на сервере** + при необходимости архив `git format-patch old/main` или полный zip проекта.

Обновляй чеклист, если добавишь новые кастомные модули.
