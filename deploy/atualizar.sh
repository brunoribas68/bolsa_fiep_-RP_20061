#!/usr/bin/env bash
# Atualiza a plataforma para a versão mais nova do GitHub: faz backup, baixa o código e reconstrói.
# O banco é migrado sozinho quando o sistema sobe. Uso: ./atualizar.sh
set -euo pipefail
cd "$(dirname "$0")"
./backup.sh
git pull --ff-only
docker compose up -d --build
docker image prune -f > /dev/null
echo "Atualizado para: $(git log -1 --format='%h %s')"
