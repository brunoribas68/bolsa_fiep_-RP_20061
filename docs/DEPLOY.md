# Servidor: instalação e manutenção

Manual para colocar a plataforma no ar num VPS (Hostinger KVM 2, servidor no Brasil) e cuidar dela no dia
a dia. Tudo que é do servidor está na pasta [`deploy/`](../deploy/):

| Arquivo | Para que serve |
|---|---|
| `docker-compose.yml` | sobe o sistema (`fiep`) e o Caddy, que dá o HTTPS do domínio |
| `Caddyfile` | liga o domínio ao sistema; o certificado HTTPS é pedido e renovado sozinho |
| `.env.exemplo` | modelo da configuração (domínio, chave, primeiro admin, backup) |
| `instalar.sh` | instalação, uma vez só |
| `backup.sh` | backup do banco, dos modelos e dos `.nox` recebidos (agendado todo dia às 2h) |
| `restaurar.sh` | volta para um backup |
| `atualizar.sh` | faz backup, baixa a versão nova do GitHub e reinicia |

Como funciona: o servidor roda dois "contêineres" (programas isolados). Um é o sistema; o outro, o Caddy,
recebe os acessos pela internet (portas 80 e 443) e repassa ao sistema. Os dados ficam fora deles, em
`deploy/dados/` e `deploy/modelos/`, então reiniciar ou atualizar não apaga nada.

---

## 1. Antes de instalar

1. **Servidor**: no painel da Hostinger, em VPS, escolha o sistema operacional **Ubuntu 24.04 com Docker**.
   Anote o **IP** do servidor.
2. **Domínio**: no painel de DNS do domínio (Hostinger, Registro.br ou onde ele estiver), crie um registro:
   - Tipo **A**, nome **genossensor** (ou o subdomínio escolhido), aponta para **o IP do servidor**.
   - Pode levar até 24 h para valer. Teste no computador: `ping genossensor.resiquant.com.br` deve mostrar o IP.
3. **Firewall**: se o firewall do painel da Hostinger estiver ativo, libere as portas **22** (acesso),
   **80** e **443** (site).
4. **Acesso ao servidor**: use o terminal do navegador no painel da Hostinger, ou
   `ssh root@IP-DO-SERVIDOR` no computador.

## 2. Instalar (uma vez)

O repositório é privado, então o servidor precisa de uma chave de leitura (deploy key):

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519   # cria a chave do servidor
cat ~/.ssh/id_ed25519.pub                          # copie o texto que aparecer
```

No GitHub: repositório → **Settings → Deploy keys → Add deploy key**, cole o texto e deixe **sem** marcar
"Allow write access". Depois, no servidor:

```bash
cd /opt
git clone git@github.com:ORGANIZACAO/REPOSITORIO.git fiep    # troque pelo endereço do repositório
cd fiep/deploy
./instalar.sh
```

O `instalar.sh` pergunta o domínio, o e-mail e a senha do primeiro administrador (mínimo 10 caracteres,
sem aspas simples), gera a chave das sessões, agenda o backup diário e sobe o sistema. A primeira subida
leva alguns minutos (monta a tela e instala as bibliotecas).

**Primeiro acesso**: abra `https://genossensor.resiquant.com.br`, entre com o admin e troque a senha em
**Minha conta**. Depois apague a senha do `.env` (deixe a linha `FIEP_ADMIN_SENHA=` vazia): ela só é usada
quando o banco não tem nenhum usuário.

## 3. Backup fora do servidor (Google Drive ou OneDrive)

O `backup.sh` já guarda as últimas 14 cópias em `deploy/backups/`. A Hostinger ainda faz um backup semanal
do servidor inteiro. Para ter também uma cópia diária fora do servidor, use o **rclone**:

```bash
apt install -y rclone
rclone config
```

No `rclone config`: `n` (novo) → nome `drive` → tipo `drive` (Google Drive) ou `onedrive` → deixe em branco
o que não souber → quando perguntar *"Use web browser to automatically authenticate?"*, responda `n`. Ele
mostra um comando `rclone authorize ...`: rode esse comando num computador com navegador e rclone
instalado (rclone.org/downloads), entre com a conta da empresa e cole de volta no servidor o código que
aparecer.

Depois, no `deploy/.env`, defina `RCLONE_DESTINO=drive:backup-fiep` e teste:

```bash
./backup.sh        # deve terminar com "Cópia enviada para drive:backup-fiep"
```

## 4. Dia a dia

Todos os comandos abaixo são rodados dentro de `/opt/fiep/deploy`.

| Tarefa | Como |
|---|---|
| Criar ou desativar usuário | pela tela, em **Usuários** (admin). No terminal: `docker compose exec fiep fiep usuario criar --email x@y.com --nome "Nome" --papel colaborador` |
| Atualizar para a versão nova | `./atualizar.sh` (faz backup antes; o banco se atualiza sozinho) |
| Fazer backup agora | `./backup.sh` |
| Voltar para um backup | `ls backups/` e `./restaurar.sh backups/fiep-AAAA-MM-DD_HHMM.tar.gz` (pede para digitar RESTAURAR) |
| Ver se está no ar | `docker compose ps` (os dois devem estar *running*) |
| Ver os registros (erros) | `docker compose logs --tail 100 fiep` |
| Reiniciar | `docker compose restart` |
| Outros comandos do sistema | `docker compose exec fiep fiep usuario listar` (qualquer comando do [README](../README.md)) |
| Espaço em disco | `df -h /` |

Uma vez por mês, vale rodar `apt update && apt upgrade -y` (atualizações de segurança do Ubuntu) e
conferir se os backups estão chegando ao Drive.

## 5. Problemas comuns

- **O site não abre ou dá erro de certificado**: o domínio ainda não aponta para o IP (aguarde a
  propagação) ou as portas 80/443 estão fechadas. Veja `docker compose logs caddy`.
- **"502 Bad Gateway"**: o sistema não subiu. Veja `docker compose logs --tail 100 fiep`.
- **Esqueci a senha do admin**: `docker compose exec fiep fiep usuario senha --email admin@...`.
- **Disco cheio**: apague backups antigos de `backups/` e rode `docker system prune -f`.

## 6. Colocar outro sistema no mesmo servidor

Cada sistema roda no seu contêiner e ganha um subdomínio próprio; um não interfere no outro.

1. No DNS, crie outro registro A (ex.: `estoque`) para o mesmo IP.
2. No `docker-compose.yml`, acrescente o serviço do novo sistema (sem `ports`: quem fala com a internet é o
   Caddy).
3. No `Caddyfile`, acrescente um bloco:
   ```
   estoque.resiquant.com.br {
   	reverse_proxy nome-do-servico:porta
   }
   ```
4. `docker compose up -d` e `docker compose restart caddy`.

Se os sistemas ficarem pesados para o KVM 2, o plano pode ser aumentado no painel da Hostinger sem
reinstalar.
