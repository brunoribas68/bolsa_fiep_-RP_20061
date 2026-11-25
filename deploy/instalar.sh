#!/usr/bin/env bash
# Instalação no servidor (uma vez só). Pede o domínio e o primeiro admin, gera a chave,
# agenda o backup diário e sobe o sistema. Uso (como root, dentro de deploy/): ./instalar.sh
set -euo pipefail
cd "$(dirname "$0")"
command -v docker > /dev/null || { echo "Docker não encontrado: instale (template 'Ubuntu com Docker' da Hostinger)."; exit 1; }

definir() {  # troca a linha CHAVE=... do .env (aceita qualquer caractere no valor)
    awk -v k="$1" -v v="$2" 'index($0, k "=") == 1 { print k "=" v; next } { print }' .env > .env.novo
    mv .env.novo .env
}
if [ ! -f .env ]; then
    cp .env.exemplo .env
    read -r -p "Domínio do sistema (ex.: genossensor.resiquant.com.br): " dominio
    read -r -p "E-mail do primeiro administrador: " email
    read -r -s -p "Senha do primeiro administrador: " senha; echo
    case "$senha" in *"'"*) rm .env; echo "A senha não pode ter aspas simples ('). Rode de novo."; exit 1;; esac
    [ ${#senha} -ge 10 ] || { rm .env; echo "A senha precisa ter pelo menos 10 caracteres. Rode de novo."; exit 1; }
    definir DOMINIO "$dominio"
    definir FIEP_ADMIN_EMAIL "$email"
    definir FIEP_ADMIN_SENHA "'$senha'"   # entre aspas simples: o docker compose não mexe em $ nem espaços
    definir FIEP_SECRET "$(head -c 48 /dev/urandom | base64 | tr -d '\n/+=')"
    chmod 600 .env
fi

mkdir -p dados modelos backups
chown -R 1000:1000 dados modelos      # usuário do sistema dentro do container
chmod +x backup.sh restaurar.sh atualizar.sh

linha="0 2 * * * $PWD/backup.sh >> $PWD/backups/backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v "$PWD/backup.sh" || true; echo "$linha" ) | crontab -
echo "Backup diário agendado para 2h."

docker compose up -d --build
echo "Pronto. Abra https://$(grep ^DOMINIO= .env | cut -d= -f2) (o HTTPS pode levar 1-2 minutos na primeira vez)."
