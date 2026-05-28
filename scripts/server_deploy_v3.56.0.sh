#!/usr/bin/env bash
# =============================================================================
# GhostVPN bot: деплой v3.56.0 на production-сервер (Docker Compose)
# =============================================================================
# Запускать на сервере из каталога с docker-compose.yml:
#   bash scripts/server_deploy_v3.56.0.sh
# =============================================================================

set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${CYAN}[+]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }

# Имя контейнера/сервиса бота (из docker-compose.yml)
COMPOSE_SERVICE="${COMPOSE_SERVICE:-bot}"
CONTAINER_NAME="${CONTAINER_NAME:-remnawave_bot}"
DB_CONTAINER="${DB_CONTAINER:-remnawave_bot_db}"

# 0) sanity
if [ ! -f docker-compose.yml ]; then
  err "docker-compose.yml не найден в текущей папке"
  exit 1
fi

# 1) сохраним .env (на всякий случай)
TS="$(date +%Y%m%d_%H%M%S)"
if [ -f .env ]; then
  cp -a .env ".env.backup.$TS"
  ok "Backup .env → .env.backup.$TS"
fi

# 2) бэкап БД (pg_dump через контейнер)
log "Бэкап Postgres → backup_db_$TS.sql.gz ..."
if docker ps --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
  POSTGRES_USER="$(docker exec "$DB_CONTAINER" sh -lc 'echo $POSTGRES_USER' | tr -d '\r')"
  POSTGRES_DB="$(docker exec "$DB_CONTAINER" sh -lc 'echo $POSTGRES_DB' | tr -d '\r')"
  docker exec "$DB_CONTAINER" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    | gzip > "backup_db_${TS}.sql.gz"
  ok "Dump готов: $(ls -lh "backup_db_${TS}.sql.gz" | awk '{print $5}')"
else
  warn "Контейнер $DB_CONTAINER не запущен — пропускаю pg_dump"
fi

# 3) обновляем код
log "git fetch + pull origin main ..."
git fetch origin
# защита от случайных локальных правок на сервере
if ! git diff --quiet || ! git diff --cached --quiet; then
  warn "На сервере есть локальные изменения. Делаю stash."
  git stash push -u -m "server-deploy-$TS"
fi
git checkout main
git pull --ff-only origin main

NEW_HEAD="$(git rev-parse --short HEAD)"
ok "Код обновлён, HEAD=$NEW_HEAD"

# 4) пересборка образа
log "docker compose build --pull $COMPOSE_SERVICE ..."
docker compose build --pull "$COMPOSE_SERVICE"

# 5) рестарт
log "docker compose up -d ..."
docker compose up -d

# 6) ждём health
log "Жду готовности контейнера $CONTAINER_NAME ..."
for i in {1..30}; do
  sleep 2
  STATUS="$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo none)"
  RUNNING="$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || echo false)"
  if [ "$RUNNING" = "true" ]; then
    if [ "$STATUS" = "healthy" ] || [ "$STATUS" = "none" ]; then
      ok "Контейнер запущен (health=$STATUS)"
      break
    fi
  fi
  if [ "$i" -eq 30 ]; then
    err "Не дождался healthy за 60с"
    docker compose logs --tail=80 "$COMPOSE_SERVICE"
    exit 2
  fi
done

# 7) лог последних ошибок (если есть)
log "Последние строки лога:"
docker compose logs --tail=40 "$COMPOSE_SERVICE" || true

ok "Деплой v3.56.0 готов."
echo
echo "Полезные команды:"
echo "  docker compose logs -f $COMPOSE_SERVICE         # смотреть логи"
echo "  docker compose ps                               # статус"
echo "  docker compose exec $COMPOSE_SERVICE alembic current     # текущая ревизия БД"
echo
echo "Откат:"
echo "  git reset --hard ORIG_HEAD"
echo "  docker compose up -d --build"
echo "  # восстановить БД (если миграции не сошлись):"
echo "  gunzip -c backup_db_${TS}.sql.gz | docker exec -i $DB_CONTAINER \\"
echo "      psql -U \$POSTGRES_USER -d \$POSTGRES_DB"
