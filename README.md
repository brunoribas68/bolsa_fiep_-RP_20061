# FIEP — Genossensor de RNA: detecção de contaminação pelo voltamograma

O genossensor é um eletrodo impresso (SPCE) com um **elemento de captura** (oligonucleotídeo). Medido
em DPV sem o alvo, ele dá o **branco** (não contaminado); depois de receber o **RNA da bactéria**, dá o
**alvo** (contaminado). O sensor é *signal-off*: com o RNA, o pico cai. Este projeto recebe os `.nox`
do potenciostato (Metrohm Autolab / NOVA), guarda cada voltamograma numa base com o pico medido, treina
e compara modelos que olham **a curva de uma medição** e diz se ela é de **contaminado ou não**.

```
.nox (dpv-branco-E1, dpv-RNA-0,1-E1) ──► base `ensaios` (pico, eletrodo, concentração) ──► modelo pela curva
                                                                                              │
                 plataforma web (login) · notebook · fiep rna prever ◄── modelo em uso ◄──────┘
```

## As entregas

| Entrega | Onde | Como abrir |
|---|---|---|
| **1. Notebook** — da base ao modelo, com as figuras | [`notebook/fiep.ipynb`](notebook/fiep.ipynb) | `jupyter notebook notebook/fiep.ipynb` |
| **2. Plataforma web + API** — login, envio de coletas, base de ensaios, gráficos, modelos, previsão | [`api/`](api/) + [`web/`](web/) | `fiep servir` → http://127.0.0.1:8000 |
| **3. Artigo** (LaTeX, pt-BR) | [`artigo/`](artigo/) | `cd artigo && latexmk -pdf main.tex` |

Todas usam o mesmo pacote Python, [`fiep/`](fiep/). O artigo ainda tem os resultados da fase anterior
(case sintético); eles serão refeitos quando a base de RNA tiver dados suficientes.

---

## 1. Instalação

Requer **Python 3.11+** e, para a plataforma web, **Node.js 18+** (só para compilar a tela).

**Windows (PowerShell)**, na pasta do repositório:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[api,dev]"
cd web; npm install; npm run build; cd ..
fiep verificar
```

**Linux / Mac:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[api,dev]"
(cd web && npm install && npm run build)
fiep verificar
```

`fiep verificar` confere dependências, banco, modelo e tela e diz o que falta.

| Extra do `pip install -e ".[...]"` | Para quê |
|---|---|
| (nenhum) | base, treino e previsão pela linha de comando |
| `api` | plataforma web (FastAPI, login) |
| `dev` | testes (`pytest`) |
| `notebook` | Jupyter e matplotlib |
| `postgres` | banco Postgres em vez de SQLite |

### Problemas comuns

| Sintoma | Solução |
|---|---|
| `... é da versão anterior da plataforma (com o case de exemplo)` | O banco é da fase anterior. `fiep db zerar` guarda uma cópia em `dados/backup/`, recria o banco e **mantém as contas e senhas**; depois importe os `.nox` de novo com `fiep rna importar`. |
| `ModuleNotFoundError: No module named 'fiep'` | Com o `.venv` ativo e **na raiz do repositório**: `python -m pip install -e ".[api,dev]"`. Enquanto isso, `python -m fiep <comando>` funciona sem instalar. |
| `fiep` não é reconhecido | O `.venv` não está ativo: `.venv\Scripts\Activate.ps1` (no PowerShell pode ser preciso `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` uma vez). |
| `No module named 'fastapi'` / `jwt` | Faltou o extra da plataforma: `python -m pip install -e ".[api]"`. |
| A página diz "Frontend não compilado" ou mostra a tela antiga | O `fiep servir` compila sozinho quando a tela está desatualizada (precisa do Node.js). Manualmente: `cd web`, `npm install`, `npm run build`. |
| `... não é um banco da plataforma FIEP` | O arquivo em `--db` (ou `dados/fiep.db`) não foi criado pela plataforma: use outro caminho ou mova o arquivo. |
| Não consigo entrar | `fiep usuario listar` mostra se a conta existe; `fiep usuario senha --email voce@...` define uma senha nova; sem conta, `fiep usuario criar --email ... --papel admin`. Depois de 5 tentativas erradas o login fica bloqueado por 15 min (ou reinicie o `fiep servir`). |
| `precisa de pelo menos 3 medições de branco e 3 de RNA` | O treino precisa de pelo menos 3 ensaios aprovados de cada tipo. Veja quantos há com `fiep rna tabela`. |
| Depois do `git pull` algo quebrou | Reinstale (`python -m pip install -e ".[api,dev]"`) e recompile a tela (`cd web && npm install && npm run build`). |

---

## 2. Primeiros passos

```bash
fiep usuario criar --email voce@exemplo.org --nome "Seu Nome" --papel admin   # pede a senha (mín. 10)
fiep rna pastas --entrada dados/rna             # cria dados/rna/contaminado e dados/rna/nao_contaminado
#   ... coloque os .nox nas pastas ...
fiep rna importar --entrada dados/rna --empresa "SENAI"
fiep rna treinar                                # quando houver pelo menos 3 brancos e 3 RNA
fiep servir                                     # http://127.0.0.1:8000
```

O banco (`dados/fiep.db`) é criado vazio no primeiro uso.

---

## 3. Dados

### Nome dos arquivos (padrão da equipe)

**técnica - etapa - concentração (ng/mL) - eletrodo**, um `.nox` por medição:

| Arquivo | O que é | Rótulo |
|---|---|---|
| `dpv-branco-E1.nox` | eletrodo com o elemento de captura, sem o alvo | não contaminado |
| `dpv-RNA-0,1-E1.nox`, `dpv-RNA-10,0-E1.nox` | com o RNA na concentração em ng/mL, **sempre com vírgula** | contaminado |

- O `E1` é o eletrodo: o branco e o RNA do mesmo eletrodo levam o mesmo `Ej`.
- O elemento de captura vem do procedimento gravado pelo NOVA (ex.: `DPV SPCE H2SO4 Oligo 4N Branco`).
  Se não vier, use `--elemento "Oligo 4N"` (ou o campo na Nova coleta).
- Se o nome e o procedimento discordarem, vale o nome e a importação avisa. Nomes antigos sem vírgula
  (`dpv-rna-15-E1` = 1,5 ng/mL) continuam aceitos: a concentração vem do procedimento.
- Arquivos de outras etapas (`dpv-bare-…`, `dpv-tratado-…`) **não entram**: a base tem só branco e RNA.
- Correções sem renomear: um `ensaios.csv` na pasta (coluna `arquivo` + as colunas a trocar).

Dicionário de dados completo: [`docs/DICIONARIO_DADOS.md`](docs/DICIONARIO_DADOS.md).

### Pastas

```
dados/
  rna/
    contaminado/       só dpv-RNA-<conc>-Ej.nox
    nao_contaminado/   só dpv-branco-Ej.nox
  recebidos/           .nox enviados pela plataforma
  fiep.db              banco
```

Um arquivo na pasta errada (branco em `contaminado/`, RNA em `nao_contaminado/`) **não é gravado**, e
a importação diz qual foi. Importar de novo não duplica (SHA-256). Um RNA com o pico acima do branco do
eletrodo gera aviso (o contrário do esperado para o sensor).

**Nada de `dados/`, `modelos/` nem `.nox` vai para o Git — o repositório é público.**

---

## 4. Linha de comando

```bash
fiep rna pastas --entrada dados/rna                  # cria contaminado/ e nao_contaminado/
fiep rna importar --entrada dados/rna --empresa SENAI   # grava no banco, com o pico de cada curva
fiep rna tabela --saida dados/base.xlsx               # a base, a queda do pico e a calibração
fiep rna treinar                                      # compara os modelos e registra o melhor
fiep modelos listar                                   # modelos treinados (* = em uso)
fiep rna prever --entrada nova.nox                    # classifica uma medição nova
fiep servir                                           # plataforma web
```

Sem instalar o pacote: `python -m fiep <comando>` na raiz do repositório.

### Todos os comandos

| Comando | Para quê | Exemplos |
|---|---|---|
| `fiep rna pastas` | cria `contaminado/` (só RNA) e `nao_contaminado/` (só branco) | `fiep rna pastas --entrada dados/rna` |
| `fiep rna importar` | lê os `.nox`, mede o pico e grava na base; liga cada RNA ao branco do mesmo eletrodo | `fiep rna importar --entrada dados/rna [--empresa "SENAI"] [--elemento "Oligo 4N"] [--eletrodo E1] [--bacteria "E. coli"]` |
| `fiep rna tabela` | mostra a base com a queda do pico em relação ao branco e a calibração; avisa RNA acima do branco | `fiep rna tabela [--saida base.xlsx\|base.csv]` |
| `fiep rna treinar` | compara 6 representações da curva × 15 algoritmos (validação por eletrodo), mede o melhor no teste e o registra como modelo em uso | `fiep rna treinar [--algoritmos log_reg lda] [--representacoes curva pico] [--seed 42] [--rapido] [--sem-ativar] [--saida cartao.json]` |
| `fiep rna prever` | classifica `.nox` novos com o modelo em uso | `fiep rna prever --entrada pasta/ [--id <modelo>] [--salvar]` |
| `fiep modelos listar` | modelos treinados, com a acurácia balanceada de referência (`*` = em uso) | `fiep modelos listar` |
| `fiep modelos mostrar` | dados, validação e a comparação completa de um modelo | `fiep modelos mostrar --id <id>` |
| `fiep modelos ativar` | troca o modelo usado pela plataforma e pelo `fiep rna prever` | `fiep modelos ativar --id <id>` |
| `fiep modelos catalogo` | representações da curva e algoritmos, com o código para `--algoritmos` / `--representacoes` | `fiep modelos catalogo` |
| `fiep excel` | converte `.nox` para Excel no formato do NOVA | `fiep excel --entrada pasta [--saida pasta] [--refazer]` |
| `fiep db migrar` | cria/atualiza o banco | `fiep db migrar [--db URL]` |
| `fiep db sql` | consulta livre | `fiep db sql "SELECT tipo, COUNT(*) FROM ensaios GROUP BY tipo" [--saida x.csv]` |
| `fiep db zerar` | apaga todos os dados e recria o banco; guarda uma cópia em `dados/backup/`, mantém as contas de usuário e pede confirmação (digite ZERAR); também tira de um banco da versão anterior | `fiep db zerar` · `fiep db zerar --sem-usuarios` · `fiep db zerar --sim` |
| `fiep servir` | plataforma web + API (compila a tela se estiver desatualizada) | `fiep servir [--host 0.0.0.0] [--porta 8000] [--db URL] [--modelos pasta] [--sem-compilar]` |
| `fiep usuario` | contas: criar, listar, redefinir senha, desativar | `fiep usuario criar --email x@y --nome "..." --papel admin\|colaborador\|leitor` · `fiep usuario listar` · `fiep usuario senha --email x@y` · `fiep usuario desativar --email x@y` |
| `fiep verificar` | diagnóstico da instalação | `fiep verificar` |
| `fiep docs` | regera [`docs/COMANDOS.md`](docs/COMANDOS.md) (todas as opções de todos os comandos) | `fiep docs` |

Opções comuns: `-v` (mostra o andamento do treino), `--db` (arquivo SQLite ou URL; padrão:
`FIEP_DB_URL` ou `dados/fiep.db`), `--modelos` (padrão: `modelos`). Lista completa:
[`docs/COMANDOS.md`](docs/COMANDOS.md) e `fiep <comando> -h`.

O conversor avulso `tools/nox2excel.py` (e o `.exe` para quem não tem Python) continua igual; CV sai só
com o último scan (`--scan todos` ou `--scan N` para outros). Ver [`tools/LEIA-ME.txt`](tools/LEIA-ME.txt).

---

## 5. Modelo pela curva

- **O que o modelo vê**: um voltamograma por vez, sem comparar com o branco do eletrodo. Rótulo: branco =
  não contaminado, RNA (qualquer concentração) = contaminado. Ensaios reprovados no QC ficam de fora.
- **Representações da curva** (6): a curva inteira (100 pontos na faixa comum de potencial); a forma
  (reescalada entre 0 e 1); a derivada (Savitzky-Golay); a curva **sem a linha de base** ("achatamento"),
  por reta vale a vale (como a base linear do NOVA) ou por ALS (base suave por baixo do sinal); as medidas
  do pico (potencial, corrente, base, altura, largura, área). A comparação diz, com os dados, se tirar a
  base ajuda — ver [`docs/PIPELINE.md`](docs/PIPELINE.md).
- **Algoritmos** (15): regressão logística (L2 em 3 intensidades e L1), LDA, SVM RBF (2), kNN, floresta
  aleatória, extra trees, gradient boosting, rede neural MLP, a rede de **Aliev et al. (2024)**
  (3 camadas de 250 neurônios; a arquitetura do artigo, treinada nos nossos dados), naive Bayes e
  **SISSO** (fórmula explícita; só com as medidas do pico). Lista com nomes: `fiep modelos catalogo`.
- **Validação**: as medições de um eletrodo nunca ficam metade no treino e metade na avaliação. Com 8 ou
  mais eletrodos, cerca de 25 % deles ficam guardados como **teste**; o resto escolhe a combinação por
  validação cruzada por eletrodo e o vencedor é medido **uma única vez** no teste. Com menos eletrodos
  não há teste independente e o resultado diz isso (é o da validação cruzada, otimista). Empate: vence a
  combinação mais simples.
- **Previsão**: CONTAMINADO / NÃO CONTAMINADO com a probabilidade; **REPETIR MEDIÇÃO** se a curva não
  cobre a faixa de potencial do modelo; **INCONCLUSIVO** enquanto a acurácia balanceada de referência do
  modelo for menor que 0,7.
- **Calibração** (exploratória): a queda do pico em relação ao branco do mesmo eletrodo contra log₁₀ da
  concentração; o limite de detecção aparece com 3 ou mais brancos.

Saídas: o modelo em `modelos/<id>/` (`modelo.joblib` + `cartao.json`) e uma linha na tabela `modelos`;
`modelos/ATUAL` diz qual está em uso. Modelos de versões antigas (da época do case) são ignorados pela
lista, pela tela e pela previsão; podem ser apagados da pasta. Detalhes: [`docs/PIPELINE.md`](docs/PIPELINE.md).

---

## 6. Plataforma web

Detalhes: [`docs/PLATAFORMA.md`](docs/PLATAFORMA.md).

| Tela | O que faz |
|---|---|
| Login | e-mail e senha (o admin cria as contas) |
| Painel | brancos, RNA e eletrodos na base, modelo em uso, coletas recentes, ensaios por concentração |
| Coletas | cada envio, quem enviou e quando, com os avisos |
| Nova coleta | empresa, descrição, data, elemento de captura e bactéria; arraste os `.nox` ou a pasta com `contaminado/` e `nao_contaminado/`; **antes de enviar mostra como cada arquivo será lido** (branco/RNA, concentração, eletrodo) e quais não vão entrar |
| Ensaios | a base inteira, com filtros (empresa, tipo, eletrodo), a queda do pico e a calibração; clique numa linha para ver a curva junto do branco do eletrodo e editar tipo, concentração, eletrodo, elemento, bactéria e QC; CSV |
| Gráficos | **linha**: média ± desvio das curvas de cada concentração (ou todas as curvas, ou um eletrodo); **dispersão**: qualquer par entre log₁₀ concentração, queda do pico, altura, corrente, potencial, base, largura e área, com reta e correlação; PNG e CSV |
| Modelos | o modelo em uso (acurácia balanceada, sensibilidade, especificidade, AUC, no teste ou na validação cruzada), a comparação de todas as combinações, a matriz de confusão no teste, o histórico (admin escolhe qual usar) e os treinos; botão **Treinar modelos** escolhe algoritmos, representações e empresas. Nomes legíveis, com explicação ao passar o mouse |
| Previsão | classifica `.nox` sem gravar na base (ou registra no histórico de previsões), mostra a curva e o pico; converte `.nox` para Excel |
| Empresas | cadastro das empresas e laboratórios |
| Usuários (admin) | criar contas, perfil, desativar, redefinir senha |
| Minha conta | trocar a própria senha |

Perfis: **admin** (tudo, inclusive trocar o modelo em uso), **colaborador** (envia e edita dados,
inicia treinos), **leitor** (consulta e prevê). O treino pela plataforma roda em segundo plano, um por
vez; o modelo novo só entra em uso se o admin marcar "Usar o melhor modelo" ou clicar **Usar este
modelo** depois.

Frontend em React + Material UI, tema claro/escuro automático e layout para celular. Desenvolvimento:
`fiep servir` num terminal e `cd web && npm run dev` noutro (http://localhost:5173). Documentação da
API: http://127.0.0.1:8000/docs.

### Variáveis de ambiente

| Variável | Padrão | Para quê |
|---|---|---|
| `FIEP_DB_URL` | `dados/fiep.db` | banco (arquivo SQLite ou `postgresql+psycopg://usuario:senha@host/fiep`) |
| `FIEP_SECRET` | gerada em `dados/.segredo` | chave das sessões — **defina em produção** (`openssl rand -base64 48`) |
| `FIEP_COOKIE_SEGURO` | `0` | `1` = cookie só por HTTPS (produção) |
| `FIEP_SESSAO_HORAS` | `8` | duração do login |
| `FIEP_MODELOS` | `modelos` | modelos treinados, o modelo em uso (`modelos/ATUAL`) e o andamento dos treinos (`modelos/_treinos`) |
| `FIEP_ARMAZENAMENTO` | `dados/recebidos` | onde ficam os `.nox` enviados |
| `FIEP_ADMIN_EMAIL` / `FIEP_ADMIN_SENHA` | — | cria o primeiro admin se não houver usuários (Docker) |
| `FIEP_SENHA_NOVA` | — | senha para `fiep usuario criar/senha` sem digitar (scripts) |

### Docker e servidor

No servidor (VPS), a plataforma roda com Docker Compose e HTTPS automático pelo Caddy, a partir da pasta
[`deploy/`](deploy/): `./instalar.sh` uma vez; depois `./backup.sh` (agendado todo dia), `./restaurar.sh` e
`./atualizar.sh`. Passo a passo da instalação e da manutenção: [`docs/DEPLOY.md`](docs/DEPLOY.md).

Só a imagem, para testar no computador:

```bash
docker build -f api/Dockerfile -t fiep .
docker run -p 8000:8000 -e FIEP_SECRET="..." -e FIEP_ADMIN_EMAIL=voce@exemplo.org \
  -e FIEP_ADMIN_SENHA='troque-esta-senha' -v "$PWD/dados:/app/dados" -v "$PWD/modelos:/app/modelos" fiep
```

---

## 7. Banco de dados

Modelo ORM (SQLAlchemy) em [`fiep/orm/`](fiep/orm/): `usuarios`, `empresas`, `coletas`, `ensaios`
(um voltamograma por linha, com o pico e a curva), `modelos` e `predicoes`. Migrations Alembic em
[`fiep/migracoes/`](fiep/migracoes/) (uma só, `r001`; um banco da versão anterior é recusado com a
orientação de rodar `fiep db zerar`). Dicionário: [`docs/DICIONARIO_DADOS.md`](docs/DICIONARIO_DADOS.md).
Para mudar o banco: edite o modelo, `alembic revision --autogenerate -m "..."` e `fiep db migrar`.
Detalhes e consultas úteis: [`docs/BANCO.md`](docs/BANCO.md).

---

## 8. Notebook e artigo

- **Notebook**: `jupyter notebook notebook/fiep.ipynb` (instale o extra `notebook`). Importa
  `dados/rna/`, mostra as curvas branco × RNA de cada eletrodo, a queda do pico e a calibração, treina e
  compara os modelos (quando houver dados) e classifica arquivos como a plataforma.
- **Artigo**: `cd artigo && latexmk -pdf main.tex`. Introdução e métodos seguem valendo; resultados e
  figuras são da fase anterior e serão refeitos com a base de RNA. Ver [`artigo/README.md`](artigo/README.md).

---

## 9. Testes e verificação

```bash
pytest -q                         # testes automáticos (base, modelo, banco, plataforma)
cd web && npm run build           # checa os tipos (TypeScript) e compila a tela
fiep verificar                    # instalação, banco, modelo e tela
```

Os testes usam curvas DPV sintéticas (nenhum arquivo real). Com `.nox` reais numa pasta,
`FIEP_NOX_DIR=<pasta> pytest -q` roda também os testes do leitor de `.nox`. O CI (GitHub Actions) roda
os testes em Python 3.11–3.14, compila a tela e o artigo.

---

## 10. Estrutura

```
fiep/                   pacote: base, modelo, banco e linha de comando
  io/                     leitura dos .nox (formato binário .NET) e das exportações do NOVA
  genossensor.py          base: nome do arquivo e do procedimento, pastas, importação, ligação ao branco, calibração
  pico.py                 pico do DPV (potencial, corrente, base, altura, largura, área)
  modelagem.py            representações da curva, comparação dos modelos, registro e previsão
  catalogo.py, sisso.py   os 15 algoritmos
  excel.py                .nox -> Excel (formato do NOVA)
  orm/, migracoes/        modelo do banco e migrations
  db.py                   conectar, consulta SQL, zerar
  usuarios.py             contas (bcrypt)
  cli.py                  comando `fiep`
api/                    backend FastAPI (login, coletas, ensaios, gráficos, modelos e treinos, previsão) + Dockerfile
web/                    frontend React + Material UI (Vite + TypeScript)
notebook/               entrega 1
artigo/                 entrega 3
tools/nox2excel.py      conversor avulso .nox -> Excel/CSV (e .exe para quem não tem Python)
deploy/                 servidor: Docker Compose + Caddy (HTTPS), instalar, backup, restaurar, atualizar
docs/                   COMANDOS (todas as opções), PIPELINE, BANCO, PLATAFORMA, DICIONARIO_DADOS, DEPLOY
tests/                  testes automáticos
```

## Declaração de uso de IA

Ver [`IA_DECLARATION.md`](IA_DECLARATION.md).
