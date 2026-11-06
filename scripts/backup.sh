#!/bin/sh
# Dumps PostgreSQL and the media volume into backups/, keeping the last 14 days.
# A backup on the same VPS is not enough: copy backups/ elsewhere afterwards.
set -eu
cd "$(dirname "$0")/.."
. ./.env

stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p backups
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > "backups/db-$stamp.dump.tmp"
mv "backups/db-$stamp.dump.tmp" "backups/db-$stamp.dump"
docker compose exec -T backend tar -C /app/media -czf - . > "backups/media-$stamp.tar.gz"
find backups -type f -mtime +14 -delete
echo "backups/db-$stamp.dump backups/media-$stamp.tar.gz"
