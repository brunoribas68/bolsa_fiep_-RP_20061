# FIEP — Detecção de contaminação em superfícies por voltametria + aprendizado de máquina

Os pesquisadores medem biossensores impressos no potenciostato (Metrohm Autolab / NOVA) e geram
voltamogramas. Este projeto recebe esses arquivos (`.nox` ou o Excel/CSV exportado pelo NOVA),
faz o controle de qualidade, guarda tudo num banco de voltamogramas, treina e compara modelos e
diz se a superfície está **contaminada ou não** (e a **carga estimada** / nível de contaminação).

```
.nox / Excel do NOVA ──► leitura + metadados automáticos ──► controle de qualidade ──► banco (SQLite/Postgres)
                                                                                          │
              plataforma web (login) ◄── modelo registrado ◄── experimento: treino 50% · validação 25% · teste 25%
```

## As três entregas

| Entrega | Onde | Como abrir |
|---|---|---|
| **1. Notebook** — do dado bruto ao modelo, com as figuras | [`notebook/fiep.ipynb`](notebook/fiep.ipynb) | `jupyter notebook notebook/fiep.ipynb` |
| **2. Plataforma web + API** — login, envio de coletas, banco de amostras, previsão | [`api/`](api/) + [`web/`](web/) | `fiep servir` → http://127.0.0.1:8000 |
| **3. Artigo** (LaTeX, pt-BR) — números, tabelas e figuras gerados pela pipeline | [`artigo/`](artigo/) | `cd artigo && latexmk -pdf main.tex` ou Overleaf |

Todas usam o mesmo pacote Python, [`fiep/`](fiep/).

---

## 1. Instalação

Requer **Python 3.11+** e, para a plataforma web, **Node.js 18+** (só para compilar o frontend).

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

`fiep verificar` confere dependências, banco, modelo e frontend e diz o que falta.

| Extra do `pip install -e ".[...]"` | Para quê |
|---|---|
| (nenhum) | pipeline: leitura, QC, banco, experimentos, previsão pela linha de comando |
| `api` | plataforma web (FastAPI, login) |
| `dev` | testes (`pytest`) |
| `notebook` | Jupyter |
| `postgres` | banco Postgres em vez de SQLite |

### Problemas comuns

| Sintoma | Solução |
|---|---|
| `ModuleNotFoundError: No module named 'fiep'` ao rodar `fiep ...` | A instalação do pacote no `.venv` ficou incompleta ou aponta para outra pasta. Com o `.venv` ativo e **na raiz do repositório**: `python -m pip install -e ".[api,dev]"`. Enquanto isso, `python -m fiep <comando>` funciona na raiz sem instalar. |
| `fiep` não é reconhecido | O `.venv` não está ativo: `.venv\Scripts\Activate.ps1` (no PowerShell pode ser preciso `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` uma vez). |
| `No module named 'fastapi'` / `jwt` | Faltou o extra da plataforma: `python -m pip install -e ".[api]"`. |
| A página diz "Frontend não compilado" | `cd web`, `npm install`, `npm run build`. |
| `table ... already exists` | Banco criado por uma versão antiga: atualize (`git pull`); o banco antigo é convertido sozinho e guardado como `dados/fiep.antigo-<data>.db`. |
| Depois do `git pull` algo quebrou | Reinstale (`python -m pip install -e ".[api,dev]"`) e recompile o frontend (`cd web && npm install && npm run build`). |

---

## 2. Primeiros passos (com os dados de exemplo)

```bash
fiep usuario criar --email voce@exemplo.org --nome "Seu Nome" --papel admin   # pede a senha (mín. 10)
fiep servir                                                                     # http://127.0.0.1:8000
```

O banco (`dados/fiep.db`) é criado no primeiro uso, já com o **case de demonstração** (200 amostras
sintéticas da empresa "Exemplo (case sintético)"; `FIEP_DADOS_EXEMPLO=0` para criar vazio). Para
treinar um modelo com ele: `fiep experimento --db dados/fiep.db`. Quando houver dados reais no
banco, o exemplo **fica fora do treino** automaticamente (`--com-exemplo` para incluir) e pode ser
apagado com `fiep db exemplo --remover`.

---

## 3. Dados

### Formatos aceitos

- `.nox` do NOVA 2.x (lido direto, sem o NOVA);
- Excel/CSV exportado pelo NOVA (colunas `Potential applied (V)`, `WE(1).δ.Current (A)`…; CSV com `;` e vírgula decimal também);
- tabelas no formato do case (`measurement_id`, `potential_V`, `current_uA` + metadados).

### O que a pipeline deduz sozinha (sem planilha)

| Campo | De onde vem |
|---|---|
| **amostra** | a pasta do arquivo (uma pasta = uma amostra) |
| **eletrodo** | `E1`, `E2`… no nome do arquivo (`final-E3.nox` → `E3`); sem isso, o canal do potenciostato |
| **etapa do sensor** | nome do arquivo ou do procedimento gravado no `.nox` (ver protocolos) |
| **técnica** | gravada no `.nox` (DPV, SWV, CV…); no Excel, pelas colunas |
| **data** | gravada no `.nox` |
| **contaminada ou não** | nome da pasta: `contaminada/`, `nao_contaminada/`, `positivo/`, `negativo/`, `controle_neg/` |

O resultado do plaqueamento (rótulo e carga em log10 UFC/mL) **não sai do voltamograma**: informe
pelo nome da pasta, na plataforma, ou em `amostras.csv` (uma linha por amostra, criado por
`fiep planilha`). Modelos: [`templates/`](templates/).

### Protocolos de biossensor

O modelo usa a **diferença entre a última etapa e a anterior, no mesmo eletrodo**. O protocolo é
reconhecido automaticamente pelos nomes das etapas (`[dados].protocolo = "auto"`):

| Protocolo | Técnica | Etapas, na ordem | Exemplo de arquivos |
|---|---|---|---|
| Imunossensor NS1 | SWV | bloqueio → mAb-NS1 → final | `bloqueio-E1.nox`, `mAb-NS1-E1.nox`, `final-E1.nox` |
| rRNA 16S (case) | DPV | carbono limpo → sonda → sonda + rRNA | `DPV_limpo_E1`, `DPV_sonda_E1`, `DPV_rRNA_E1` |

Novo protocolo: `[protocolos.<nome>]` em `configs/default.toml` (ver [`fiep/protocolos.py`](fiep/protocolos.py)).

### Onde colocar os arquivos e como são divididos

```
dados/
  empresa1/contaminada/A01/*.nox   <- dados "soltos": divididos 50% treino / 25% validação / 25% teste
  treino/  validacao/  teste/      <- opcionais: vão inteiros para aquele conjunto (ex.: outra empresa em teste/)
  exemplo_case/                    <- demonstração (usado só se não houver mais nada)
  excel/                           <- cópias em Excel dos .nox (geradas; não entram no treino)
  recebidos/                       <- arquivos enviados pela plataforma
  fiep.db                          <- banco
```

A divisão é **por amostra** (réplicas e etapas da mesma amostra ficam juntas) e estratificada
pela classe. Proporções em `[divisao]`. Detalhes: [`dados/README.md`](dados/README.md).

**Nada de `dados/` (exceto `exemplo_case/`), `modelos/`, `resultados/` nem `.nox` vai para o Git —
o repositório é público.**

---

## 4. Fluxo pela linha de comando

```bash
fiep planilha --entrada dados/empresa1       # confere o que foi deduzido; complete amostras.csv
fiep db importar --entrada dados             # grava no banco (QC + cópia em Excel em dados/excel/)
fiep db resumo                               # contagens
fiep db sql "SELECT * FROM v_replicatas WHERE n_aprovadas < 3"   # eletrodos sem as 3 etapas
fiep experimento --artigo                    # treino/validação/teste, compara modelos, registra o melhor
fiep modelos listar                          # acurácia de cada modelo treinado; * = o que está em uso
fiep modelos mostrar                         # métricas do modelo em uso e a comparação de algoritmos
fiep prever --entrada nova_coleta/ --saida resultado.csv          # por amostra e por eletrodo
fiep servir                                  # plataforma web
```

Sem instalar o pacote: `python -m fiep <comando>` na raiz do repositório.

### Todos os comandos

| Comando | Para quê | Exemplos |
|---|---|---|
| `fiep planilha` | deduz amostra/eletrodo/etapa/data; cria `metadados_nox.csv` (conferência) e `amostras.csv` (rótulos) | `fiep planilha --entrada dados/empresa1` |
| `fiep excel` | converte `.nox` para Excel no formato do NOVA | `fiep excel --entrada dados/empresa1 [--saida pasta] [--refazer]` |
| `fiep db migrar` | cria/atualiza o banco pelas migrations | `fiep db migrar [--sem-exemplo] [--db URL]` |
| `fiep db importar` | lê arquivos, roda o QC e grava no banco | `fiep db importar --entrada dados [--empresa "Laticínio A"] [--conjunto teste] [--sem-excel]` |
| `fiep db resumo` | contagens do banco | `fiep db resumo` |
| `fiep db sql` | consulta livre (views: `v_medicoes`, `v_replicatas`, `v_qc_atual`, `v_predicoes`) | `fiep db sql "SELECT ..." [--saida x.csv]` |
| `fiep db exportar` | banco inteiro para Excel (uma aba por tabela) ou CSV | `fiep db exportar --saida dados/banco.xlsx` · `--formato csv --saida pasta/` |
| `fiep db exemplo` | carrega / remove o case de demonstração | `fiep db exemplo` · `fiep db exemplo --remover` |
| `fiep experimento` | divide 50/25/25, compara 5 representações × 14 algoritmos (ou só os escolhidos), escolhe na validação, mede no teste, registra o melhor | `fiep experimento [--artigo] [--rapido]` · `fiep experimento --db dados/fiep.db [--filtro "empresa_id = 2"] [--filtro-teste "..."] [--com-exemplo]` · `fiep experimento --algoritmos mlp,random_forest,svm_rbf --variantes dif_curva [--nao-ativar]` |
| `fiep modelos listar` | todos os modelos treinados com acurácia, acurácia balanceada, AUC e por amostra no teste (`*` = em uso) | `fiep modelos listar` |
| `fiep modelos mostrar` | métricas de um modelo e a comparação de todos os algoritmos testados | `fiep modelos mostrar [--id <id>]` (sem `--id`: o modelo em uso) |
| `fiep modelos ativar` | troca o modelo usado pela plataforma e pelo `fiep prever` | `fiep modelos ativar --id <id>` |
| `fiep modelos catalogo` | algoritmos e representações disponíveis (nomes para `--algoritmos` / `--variantes`) | `fiep modelos catalogo` |
| `fiep prever` | classifica dados novos com o modelo registrado | `fiep prever --entrada pasta/ [--saida r.csv] [--db] [--modelo modelos/<id>]` |
| `fiep servir` | plataforma web + API | `fiep servir [--host 0.0.0.0] [--porta 8000] [--db URL] [--modelos pasta]` |
| `fiep usuario` | contas: criar, listar, redefinir senha, desativar | `fiep usuario criar --email x@y --nome "..." --papel admin\|colaborador\|leitor` · `fiep usuario listar` · `fiep usuario senha --email x@y` · `fiep usuario desativar --email x@y` |
| `fiep verificar` | diagnóstico da instalação | `fiep verificar` |
| `fiep docs` | regera [`docs/COMANDOS.md`](docs/COMANDOS.md) (todas as opções de todos os comandos) | `fiep docs` |
| `fiep ingerir` · `fiep qc` · `fiep treinar` · `fiep tudo` | (avançado) fluxo só com arquivos CSV, sem banco | `fiep tudo --entrada dados/empresa1` |

Opções comuns: `-v` (mostra o andamento), `--config arquivo.toml` (padrão: `FIEP_CONFIG` ou
`configs/default.toml`), `--db` (arquivo SQLite ou URL; padrão: `FIEP_DB_URL` ou `dados/fiep.db`).
A lista completa de opções de cada comando está em [`docs/COMANDOS.md`](docs/COMANDOS.md) e em
`fiep <comando> -h`.

---

## 5. Plataforma web

Para os colaboradores enviarem as coletas das empresas. Detalhes: [`docs/PLATAFORMA.md`](docs/PLATAFORMA.md).

| Tela | O que faz |
|---|---|
| Login | e-mail e senha (não há cadastro aberto: o admin cria as contas) |
| Painel | amostras por resultado e por empresa, eletrodos completos, modelo em uso **com a acurácia no teste**, coletas recentes |
| **Gráficos** | **linha**: voltamograma médio ± desvio por resultado (contaminada × não contaminada) em cada etapa ou na diferença última − anterior, ou por etapa do sensor; curvas individuais opcionais. **Dispersão**: um ponto por eletrodo, qualquer par de variáveis (corrente/potencial do pico, área, amplitude, largura de cada etapa, diferenças entre etapas, carga log10 UFC/mL), cor por resultado ou empresa, linha de tendência e correlação r; atalhos prontos (sinal × carga, etapa anterior × final…). Filtros por empresa, protocolo e QC; baixa PNG de cada gráfico e a tabela de descritores em CSV; clique num ponto abre a amostra |
| **Modelos** | acurácia do modelo em uso (acurácia, acurácia balanceada, sensibilidade, especificidade, AUC, por amostra); abas **Comparação de algoritmos** (melhor de cada algoritmo + tabela ordenável de todas as combinações), **Gráficos** (ROC, matriz de confusão, fórmula SISSO…), **Carga** (regressão), **Histórico** (todos os modelos; admin escolhe qual usar) e **Treinos**; botão **Treinar modelos** escolhe os algoritmos de IA, as representações, as empresas e a divisão treino/validação/teste |
| Nova coleta | empresa, data, uso no treino (sorteio ou treino/validação/teste) e as amostras: arraste a pasta do lote (uma subpasta por amostra) ou adicione amostra a amostra, com o resultado do plaqueamento e a carga |
| Coletas | cada envio, quem enviou e quando; avisos (eletrodos sem as 3 etapas, QC) |
| Amostras | busca e filtros; rótulo e carga editáveis na tabela |
| Amostra | voltamogramas por eletrodo (3 etapas sobrepostas), medições com QC e etapa editável, plaqueamento, **Prever com o modelo** |
| Previsão | classifica arquivos sem gravar; converte `.nox` para Excel |
| Empresas | cadastro das empresas validadoras |
| Usuários (admin) | criar contas, perfil, desativar, redefinir senha |
| Minha conta | trocar a própria senha |

Perfis: **admin** (tudo, inclusive trocar o modelo em uso), **colaborador** (envia e edita dados,
inicia treinos), **leitor** (consulta e prevê).

Treino pela plataforma: roda em segundo plano (um por vez; o andamento aparece na aba Treinos).
O modelo novo só passa a ser usado se o admin marcar "Usar o melhor modelo" ao treinar ou clicar
**Usar este modelo** depois — assim dá para testar vários algoritmos sem mexer no que está em uso.

Frontend em React + **Material UI** (MUI), com tema claro/escuro automático e layout para celular
(o menu lateral vira gaveta). Desenvolvimento: `fiep servir` num terminal e `cd web && npm run dev`
noutro (http://localhost:5173); o tema fica em `web/src/tema.ts` e os componentes comuns em
`web/src/componentes/comum.tsx`. Documentação da API: http://127.0.0.1:8000/docs.

### Variáveis de ambiente

| Variável | Padrão | Para quê |
|---|---|---|
| `FIEP_DB_URL` | `dados/fiep.db` | banco (arquivo SQLite ou `postgresql+psycopg://usuario:senha@host/fiep`) |
| `FIEP_SECRET` | gerada em `dados/.segredo` | chave das sessões — **defina em produção** (`openssl rand -base64 48`) |
| `FIEP_COOKIE_SEGURO` | `0` | `1` = cookie só por HTTPS (produção) |
| `FIEP_SESSAO_HORAS` | `8` | duração do login |
| `FIEP_MODELOS` | `modelos` | pasta dos modelos treinados e do modelo em uso (`modelos/ATUAL`) |
| `FIEP_RESULTADOS` | `resultados` | tabelas e figuras de cada experimento (comparação mostrada na tela Modelos) e o estado dos treinos |
| `FIEP_ARMAZENAMENTO` | `dados/recebidos` | onde ficam os arquivos enviados |
| `FIEP_DADOS_EXEMPLO` | `1` | carregar o case de exemplo ao criar o banco |
| `FIEP_ADMIN_EMAIL` / `FIEP_ADMIN_SENHA` | — | cria o primeiro admin se não houver usuários (Docker) |
| `FIEP_CONFIG` | `configs/default.toml` | configuração da pipeline (protocolos, QC, níveis…) |
| `FIEP_SENHA_NOVA` | — | senha para `fiep usuario criar/senha` sem digitar (scripts) |

### Docker

```bash
docker build -f api/Dockerfile -t fiep .
docker run -p 8000:8000 -e FIEP_SECRET="..." -e FIEP_ADMIN_EMAIL=voce@exemplo.org \
  -e FIEP_ADMIN_SENHA='troque-esta-senha' -v "$PWD/dados:/app/dados" -v "$PWD/modelos:/app/modelos" fiep
```

---

## 6. Modelos e resultados

- **Representações** (5): descritores de pico + diferenças entre etapas; curva de diferença
  completa; idem com linha de base; idem sem suavização; só a etapa final.
- **Algoritmos** (14): regressão logística (L2 em 3 intensidades e L1), LDA, SVM RBF (2), kNN, floresta
  aleatória, extra trees, gradient boosting, **rede neural MLP**, naive Bayes e **SISSO** simplificado
  (fórmula explícita). Lista com nomes: `fiep modelos catalogo`. Para testar só alguns:
  `fiep experimento --algoritmos mlp,svm_rbf --variantes dif_curva` ou o botão **Treinar modelos**
  na tela Modelos. Para incluir outro algoritmo, acrescente-o em `fiep/catalogo.py`.
- **Protocolo**: treino 50% (validação cruzada agrupada por amostra → limiar de Youden), escolha na
  validação 25%, re-treino com treino + validação e avaliação **uma única vez** no teste 25%.
- **Resultado por amostra**: média das probabilidades dos eletrodos aprovados no QC, com a
  concordância entre eles.
- **Carga e níveis**: regressão da carga (log10 UFC/mL) nas contaminadas; com `[niveis]`
  configurado (ex.: `limites_log10 = [3.0, 5.0]`, `nomes = ["baixa", "moderada", "alta"]`) a carga
  vira nível de contaminação — os limites são decisão da equipe e mudam sem re-treinar.
- **Controle de qualidade**: sobrecarga de corrente, potencial que não acompanha o aplicado
  (descontada a amplitude do pulso na SWV), poucos pontos, corrente fora do padrão do lote.

Saídas de `fiep experimento`: `resultados/<id>/` (tabelas, figuras, `resumo.json`) e o modelo em
`modelos/<id>/` (passa a ser o usado pela plataforma, a menos que use `--nao-ativar`). Onde ver a
acurácia e comparar: tela **Modelos** da plataforma, ou `fiep modelos listar` / `fiep modelos mostrar`. Com `--artigo`, figuras, tabelas e números
vão para `artigo/gerado/`. Como funciona em detalhe: [`docs/PIPELINE.md`](docs/PIPELINE.md).

---

## 7. Banco de dados

Modelo ORM (SQLAlchemy) em [`fiep/orm/`](fiep/orm/), separado por domínio (`auth`, `cadastro`,
`dados`, `ml`), com migrations Alembic em [`fiep/migracoes/`](fiep/migracoes/) — a última carrega
os dados de exemplo. Para mudar o banco: edite o modelo, `alembic revision --autogenerate -m "..."`
e `fiep db migrar`. Detalhes e consultas úteis: [`docs/BANCO.md`](docs/BANCO.md).

---

## 8. Notebook e artigo

- **Notebook**: `jupyter notebook notebook/fiep.ipynb` (instale o extra `notebook`). Usa os dados de
  `dados/` (ou o case de exemplo), reaproveita o último experimento feito com os mesmos dados
  (`REFAZER = True` para rodar de novo).
- **Artigo**: `fiep experimento --artigo` atualiza `artigo/gerado/`; compile com
  `cd artigo && latexmk -pdf main.tex`. Trechos a completar pelo laboratório aparecem em vermelho
  (`\preencher{...}`). Ver [`artigo/README.md`](artigo/README.md).

---

## 9. Testes e verificação

```bash
pytest -q                         # testes automáticos (pipeline, banco, plataforma, protocolos)
cd web && npm run build           # checa os tipos (TypeScript) e compila o frontend
fiep verificar                    # instalação, banco, modelo e frontend
```

Com `.nox` reais numa pasta, `FIEP_NOX_DIR=<pasta> pytest -q` roda também os testes que leem os
arquivos. O CI (GitHub Actions) roda os testes em Python 3.11–3.14, compila o frontend e o artigo.

---

## 10. Estrutura

```
fiep/                   pacote: pipeline, banco e linha de comando
  io/                     leitura dos .nox (formato binário .NET) e das exportações do NOVA
  ingest.py               junta .nox, Excel e tabelas num formato único
  metadados_auto.py       deduz amostra, eletrodo, etapa, data e rótulo
  protocolos.py           protocolos de biossensor (etapas, técnica, nomes)
  planilha.py             metadados_nox.csv + amostras.csv
  excel.py                .nox -> Excel (formato do NOVA)
  qc.py                   controle de qualidade
  preprocess.py           grade de potencial, suavização, linha de base
  features.py             descritores e diferença entre etapas
  catalogo.py, sisso.py   modelos
  divisao.py              treino / validação / teste
  experimentos.py         comparação de modelos e registro do melhor
  figuras.py              figuras e tabelas (notebook e artigo)
  model.py, predict.py    treino, registro e previsão (por eletrodo e por amostra, níveis)
  registro.py             modelos treinados: métricas, comparação, troca do modelo em uso
  graficos.py             dados da tela Gráficos (curvas médias e descritores por eletrodo)
  orm/, migracoes/        modelo do banco e migrations
  db.py, legado.py        funções do banco; conversão do banco antigo
  usuarios.py             contas (bcrypt)
  cli.py                  comando `fiep`
api/                    backend FastAPI (login, coletas, amostras, previsão, gráficos, modelos e treinos) + Dockerfile
web/                    frontend React + Material UI (Vite + TypeScript)
notebook/               entrega 1
artigo/                 entrega 3
configs/default.toml    todos os parâmetros (protocolos, QC, divisão, níveis, modelos)
templates/              modelos de amostras.csv e metadados_nox.csv
tools/nox2excel.py      conversor avulso .nox -> Excel/CSV (e .exe para quem não tem Python)
docs/                   COMANDOS (todas as opções), PIPELINE, BANCO, PLATAFORMA
tests/                  testes automáticos
```

## Declaração de uso de IA

Ver [`IA_DECLARATION.md`](IA_DECLARATION.md).
