#!/usr/bin/env bash
# =============================================================================
# GhostVPN bot: обновление с upstream v3.55.0 → v3.56.0 (BEDOLAGA-DEV)
# =============================================================================
# Безопасно мерджит upstream/v3.56.0 в локальную main с сохранением:
#   - Robokassa и кастомных платёжных правок
#   - локальных миграций 0054, 0083..0092 (Robokassa, ensure_*-патчи)
#   - docker-compose.yml, vpn_logo.png и других инфраструктурных файлов
#
# Запускать в git bash на Windows из корня репозитория:
#   bash scripts/update_to_v3.56.0.sh
# =============================================================================

set -euo pipefail

# -- цвета для логов ----------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[+]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }

confirm() {
  read -r -p "$1 [y/N]: " ans
  [[ "${ans:-N}" =~ ^[yY]$ ]]
}

# -- 0. sanity checks ---------------------------------------------------------
if [ ! -d .git ]; then
  err "Запусти скрипт из корня репозитория ghostvpnbot (где .git)"
  exit 1
fi

if ! git remote get-url upstream >/dev/null 2>&1; then
  warn "remote 'upstream' не настроен. Добавляю..."
  git remote add upstream https://github.com/BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot.git
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT_BRANCH" != "main" ]; then
  warn "Текущая ветка: $CURRENT_BRANCH (ожидается main)."
  confirm "Продолжить?" || exit 1
fi

# нормализация EOL во время merge — спасает от ложных конфликтов CRLF↔LF
git config merge.renormalize true

# -- 1. бэкап -----------------------------------------------------------------
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP="backup/pre-v3.56.0-$TS"
log "Создаю backup-ветку: $BACKUP"
git branch "$BACKUP"
ok "Backup готов. Откат: git reset --hard $BACKUP"

# -- 2. fetch -----------------------------------------------------------------
log "git fetch upstream --tags ..."
git fetch upstream --tags --prune

# проверим что тэг существует
if ! git rev-parse -q --verify "refs/tags/v3.56.0" >/dev/null; then
  err "Тэг v3.56.0 не найден в upstream. Проверь подключение к github.com"
  exit 1
fi

log "Целевой коммит upstream/v3.56.0: $(git rev-parse --short v3.56.0)"

# -- 3. merge -----------------------------------------------------------------
log "Запускаю merge upstream v3.56.0 ..."
set +e
git merge --no-ff --no-commit v3.56.0 -m "Merge upstream v3.56.0"
MERGE_EXIT=$?
set -e

# -- 4. policy: какие пути всегда «наши» -------------------------------------
# (см. docs/FORK_CUSTOMIZATION_CHECKLIST.md)
OURS_PATHS=(
  # === Robokassa ===
  "app/services/robokassa_service.py"
  "app/services/payment/robokassa.py"
  "app/database/crud/robokassa.py"
  "app/handlers/balance/robokassa.py"
  "migrations/alembic/versions/0054_add_robokassa_payments.py"

  # === Инфраструктура / Docker ===
  "docker-compose.yml"
  "docker-compose.local.yml"
  "vpn_logo.png"

  # === Локальные ensure_* миграции, не существующие в upstream ===
  "migrations/alembic/versions/0083_ensure_paypear_payments_exists.py"
  "migrations/alembic/versions/0087_ensure_rollypay_payments_exists.py"
  "migrations/alembic/versions/0088_ensure_aurapay_payments_exists.py"
  "migrations/alembic/versions/0089_ensure_etoplatezhi_payments_exists.py"
  "migrations/alembic/versions/0090_ensure_antilopay_payments_exists.py"
  "migrations/alembic/versions/0091_ensure_rollypay_aurapay_etoplatezhi_payments.py"
  "migrations/alembic/versions/0092_ensure_upstream_base_provider_tables.py"

  # === Документация форка ===
  "docs/FORK_CUSTOMIZATION_CHECKLIST.md"
)

log "Принудительно беру 'наши' версии для критичных путей:"
for p in "${OURS_PATHS[@]}"; do
  if git ls-files --error-unmatch "$p" >/dev/null 2>&1; then
    # на случай если конфликт именно тут
    git checkout --ours -- "$p" 2>/dev/null || true
    git add "$p" 2>/dev/null || true
    echo "    ours: $p"
  fi
done

# -- 5. оставшиеся конфликты --------------------------------------------------
CONFLICTS="$(git diff --name-only --diff-filter=U || true)"
if [ -n "$CONFLICTS" ]; then
  warn "Остались конфликты, которые нужно разрулить вручную:"
  echo "$CONFLICTS" | sed 's/^/    - /'
  echo
  echo "Подсказки по разрешению:"
  echo "  • Файлы Robokassa-связанные → git checkout --ours -- <file>"
  echo "  • app/services/payment_*.py, app/utils/payment_utils.py,"
  echo "    app/webserver/payments.py → ВАЖНО: смерджить руками."
  echo "    Логика Robokassa (mixin, webhook, методы verification) должна остаться."
  echo "  • Если в файле просто новые методы из upstream — берём theirs:"
  echo "       git checkout --theirs -- <file>"
  echo "    и потом досыпаем Robokassa-блоки руками."
  echo "  • Миграции (см. ниже) — отдельная история."
  echo
  echo "После разрешения: git add <files>  &&  выходи из скрипта  &&"
  echo "запусти scripts/post_merge_fix.sh (он перенумерует/спатчит миграции)"
  exit 2
fi

# -- 6. фикс цепочки миграций -------------------------------------------------
log "Фикс цепочки миграций (down_revision)…"

ALEMBIC_DIR="migrations/alembic/versions"
# Найти все НОВЫЕ upstream миграции, добавленные в v3.56.0 (после 0082)
NEW_UPSTREAM_MIGRATIONS=()
for f in "$ALEMBIC_DIR"/00{83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99}_*.py; do
  [ -f "$f" ] || continue
  base="$(basename "$f")"
  # «наши» ensure-* пропускаем, они уже учтены
  case "$base" in
    0083_ensure_paypear_payments_exists.py)             continue;;
    0087_ensure_rollypay_payments_exists.py)            continue;;
    0088_ensure_aurapay_payments_exists.py)             continue;;
    0089_ensure_etoplatezhi_payments_exists.py)         continue;;
    0090_ensure_antilopay_payments_exists.py)           continue;;
    0091_ensure_rollypay_aurapay_etoplatezhi_payments.py) continue;;
    0092_ensure_upstream_base_provider_tables.py)       continue;;
  esac
  # это файл, которого не было раньше
  if ! git show "HEAD:$f" >/dev/null 2>&1; then
    NEW_UPSTREAM_MIGRATIONS+=("$f")
  fi
done

if [ "${#NEW_UPSTREAM_MIGRATIONS[@]}" -gt 0 ]; then
  warn "Найдены новые upstream миграции, требуют перенумерации после 0092:"
  for f in "${NEW_UPSTREAM_MIGRATIONS[@]}"; do echo "    - $f"; done
  echo
  echo "Скрипт НЕ пытается их автоматически переименовывать (риск сломать DDL)."
  echo "После окончания merge:"
  echo "  1) Для каждой переименуй файл и поправь revision/down_revision,"
  echo "     чтобы цепочка шла: 0092_ensure_upstream_base_provider_tables → новые миграции"
  echo "  2) Локально подними БД из dump и прогони alembic upgrade head"
  echo "  3) Если всё ок — финализируй merge коммитом."
fi

# -- 7. финализация merge -----------------------------------------------------
if [ "$MERGE_EXIT" -ne 0 ] && [ -z "$CONFLICTS" ]; then
  # были конфликты только в OURS_PATHS — уже разрулили выше
  :
fi

log "Финализирую merge-коммит..."
if ! git commit --no-edit 2>/dev/null; then
  warn "git commit ругается — возможно ничего не было в merge state."
fi

# -- 8. синтаксическая проверка Python ---------------------------------------
log "Проверяю синтаксис Python (compileall)…"
if command -v python3 >/dev/null 2>&1; then PYBIN=python3; else PYBIN=python; fi
if $PYBIN -m compileall -q app main.py migrations 2>&1 | tee /tmp/compile.log; then
  if grep -qE 'SyntaxError|Sorry: ' /tmp/compile.log; then
    err "Найдены SyntaxError, проверь /tmp/compile.log"
    exit 3
  fi
  ok "compileall OK"
else
  err "compileall провалился"
  exit 3
fi

# -- 9. готово ----------------------------------------------------------------
ok "Локально обновлено до v3.56.0."
echo
echo "Дальше:"
echo "  1) Проверь diff:  git log --oneline ${BACKUP}..HEAD"
echo "  2) Запусти pytest (если используешь):  pytest -x  (опционально)"
echo "  3) Push:  git push origin main"
echo "  4) На сервере:  bash scripts/server_deploy_v3.56.0.sh"
echo
echo "Откат, если что-то не так:"
echo "  git reset --hard $BACKUP"
