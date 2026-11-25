#!/usr/bin/env bash
# Backup da plataforma: banco (cópia consistente, com o sistema no ar), modelos e .nox recebidos.
# Gera backups/fiep-AAAA-MM-DD_HHMM.tar.gz; se RCLONE_DESTINO estiver no .env, envia uma cópia para lá.
# Uso: ./backup.sh   (o instalar.sh agenda todo dia às 2h)
set -euo pipefail
cd "$(dirname "$0")"
valor() { grep -m1 "^$1=" .env | cut -d= -f2-; }  # lê só o que precisa do .env
RCLONE_DESTINO=$(valor RCLONE_DESTINO); BACKUPS_MANTER=$(valor BACKUPS_MANTER)

mkdir -p backups
nome="fiep-$(date +%F_%H%M)"
# Cópia do SQLite pela API de backup: segura mesmo com alguém usando o sistema.
docker compose exec -T fiep python -c "
import sqlite3
o = sqlite3.connect('dados/fiep.db'); d = sqlite3.connect('dados/_backup.db')
o.backup(d); d.close(); o.close()"
tar -czf "backups/$nome.tar.gz" --transform 's,^dados/_backup.db$,dados/fiep.db,' \
    dados/_backup.db modelos $( [ -d dados/recebidos ] && echo dados/recebidos )
rm -f dados/_backup.db
echo "Backup criado: backups/$nome.tar.gz"

# Mantém só os mais recentes.
ls -1t backups/fiep-*.tar.gz | tail -n +"$(( ${BACKUPS_MANTER:-14} + 1 ))" | xargs -r rm --

if [ -n "${RCLONE_DESTINO:-}" ]; then
    rclone copy "backups/$nome.tar.gz" "$RCLONE_DESTINO" && echo "Cópia enviada para $RCLONE_DESTINO"
fi
