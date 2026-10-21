# Plataforma web (login, coletas, banco de amostras)

Frontend em React (`web/`) e backend em FastAPI (`api/`), sobre o mesmo banco e o mesmo modelo da
pipeline. É por aqui que os colaboradores enviam as coletas feitas nas empresas.

## Primeira vez

```bash
pip install -e ".[api]"
cd web && npm install && npm run build && cd ..        # compila o frontend (web/dist)

fiep usuario criar --email voce@exemplo.org --nome "Seu Nome" --papel admin   # pede a senha
fiep servir                                            # http://127.0.0.1:8000
```

O banco é criado na primeira execução com as migrations, já com o **case de exemplo** (empresa
"Exemplo (case sintético)", 200 amostras) para testar. Quando chegarem os dados reais:
`fiep db exemplo --remover`.

Desenvolvimento do frontend com recarga automática: `fiep servir` num terminal e
`cd web && npm run dev` noutro (abre em http://localhost:5173, com proxy para a API).

## Perfis

| Perfil | Pode |
|---|---|
| Administrador | tudo, inclusive criar/desativar contas, redefinir senhas e apagar coletas |
| Colaborador | enviar coletas, cadastrar empresas, editar rótulos e metadados, prever |
| Leitor | consultar e prever |

Não há cadastro aberto: o admin cria as contas (página **Usuários** ou `fiep usuario criar`).

## Telas

- **Painel**: amostras por resultado e por empresa, réplicas completas, modelo em uso, coletas recentes.
- **Nova coleta**: empresa, data, uso no treino (sorteio 50/25/25, ou fixo em treino/validação/teste) e as
  amostras. Arraste a pasta do lote (uma subpasta por amostra) ou adicione amostra por amostra. Para cada
  uma: código, resultado do plaqueamento e carga. Aceita `.nox` e Excel/CSV exportado do NOVA.
  Ao enviar, os arquivos são guardados (`dados/recebidos/`), lidos, passam pelo controle de qualidade e
  vão para o banco; estágio do sensor e réplica são deduzidos dos arquivos.
- **Amostras**: busca e filtros; o resultado do plaqueamento e a carga são editáveis direto na tabela.
- **Amostra**: voltamogramas por réplica (os três estágios sobrepostos), medições com o QC e o estágio
  editável, plaqueamento, histórico e o botão **Prever com o modelo**.
- **Previsão**: classifica arquivos sem gravar nada (e converte `.nox` para Excel).

## Segurança

- Senhas com bcrypt (custo 12), mínimo de 10 caracteres; a senha nunca volta do servidor.
- Sessão em cookie `httpOnly`, `SameSite=Strict` (e `Secure` com `FIEP_COOKIE_SEGURO=1`), assinada
  com `FIEP_SECRET`, validade de 8 h. Trocar a senha, mudar o perfil ou desativar a conta derruba as
  sessões abertas.
- Toda alteração exige o cabeçalho `X-Requested-With: fiep` (proteção contra CSRF).
- 5 tentativas de login erradas em 15 min (por e-mail ou IP) bloqueiam novas tentativas.
- Cabeçalhos de segurança (CSP, `X-Frame-Options`, `nosniff`); uploads limitados por tipo, tamanho
  (50 MB) e caminho (sem `..`).

Em produção: rode atrás de HTTPS, defina `FIEP_SECRET` (`openssl rand -base64 48`),
`FIEP_COOKIE_SEGURO=1` e, de preferência, Postgres em `FIEP_DB_URL`. Todas as variáveis estão em
`api/config.py`. Imagem Docker: `api/Dockerfile`.

## API

Documentação interativa em `/docs`. Principais rotas: `/api/auth/*`, `/api/usuarios`, `/api/empresas`,
`/api/coletas`, `/api/amostras`, `/api/medicoes/{id}`, `/api/prever`, `/api/excel`, `/api/painel`.
