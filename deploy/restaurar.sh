#!/usr/bin/env bash
# Volta a plataforma para um backup. Antes, guarda o estado atual em backups/antes-de-restaurar-*.tar.gz.
# Uso: ./restaurar.sh backups/fiep-2027-01-15_0200.tar.gz
set -euo pipefail
cd "$(dirname "$0")"
arquivo="${1:?informe o backup, ex.: ./restaurar.sh backups/fiep-2027-01-15_0200.tar.gz}"
[ -f "$arquivo" ] || { echo "Arquivo não encontrado: $arquivo"; exit 1; }

read -r -p "Isto substitui os dados atuais pelos de $arquivo. Digite RESTAURAR para continuar: " ok
[ "$ok" = "RESTAURAR" ] || { echo "Cancelado."; exit 1; }

docker compose stop fiep
mkdir -p backups
tar -czf "backups/antes-de-restaurar-$(date +%F_%H%M).tar.gz" dados modelos
rm -rf dados/fiep.db dados/fiep.db-wal dados/fiep.db-shm dados/recebidos modelos
tar -xzf "$arquivo"
chown -R 1000:1000 dados modelos
docker compose start fiep
echo "Restaurado de $arquivo."
