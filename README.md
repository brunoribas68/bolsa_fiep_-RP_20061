# FIEP — Detecção de contaminação em superfícies por voltametria + aprendizado de máquina

Plataforma do projeto FIEP: lê os voltamogramas dos biossensores impressos (arquivos `.nox` do
NOVA), faz o controle de qualidade, organiza tudo num banco de dados rastreável, compara modelos
para classificar superfícies como **contaminadas / não contaminadas** e estimar a **carga
bacteriana**, e disponibiliza o modelo escolhido numa página web.

## As três entregas

| Entrega | Onde | Como abrir |
|---|---|---|
| **1. Notebook** — análise completa, do dado bruto ao modelo | [`notebook/fiep.ipynb`](notebook/fiep.ipynb) | `jupyter notebook notebook/fiep.ipynb` |
| **2. API + página web** — envio de `.nox` e resultado na hora | [`api/`](api/) | `fiep servir` → http://127.0.0.1:8000 |
| **3. Artigo** (LaTeX, pt-BR) — resultados gerados pela pipeline | [`artigo/`](artigo/) | `cd artigo && latexmk -pdf main.tex` ou Overleaf |

As três usam o mesmo pacote Python, `fiep/`.

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate             # Linux/Mac: source .venv/bin/activate
pip install -e ".[dev]"            # pipeline + API + testes
pytest -q
```

Requer Python 3.11 ou mais recente.

## Fluxo de trabalho

```bash
# 1. coloque os .nox de um lote em dados/treino/ e gere a planilha de metadados
fiep planilha --entrada dados/treino
#    preencha sample_id, replicate_id, sensor_state, contamination_status (e a carga, se houver)

# 2. importe para o banco (dados/fiep.db) — roda o controle de qualidade
fiep db importar --entrada dados/treino
fiep db sql "SELECT * FROM v_replicatas WHERE n_aprovadas < 3"     # réplicas incompletas

# 3. compare representações x modelos e registre o melhor (figuras e tabelas vão para o artigo)
fiep experimento --treino dados/treino --validacao dados/validacao --artigo

# 4. use o modelo
fiep servir                                    # página web + API
fiep prever --entrada nova_coleta/ --db dados/fiep.db
```

Detalhes: [`dados/README.md`](dados/README.md) (como preparar os dados),
[`docs/PIPELINE.md`](docs/PIPELINE.md) (como a pipeline funciona),
[`docs/BANCO.md`](docs/BANCO.md) (banco de dados e consultas).

## Estrutura

```
fiep/                pacote da pipeline
  io/                  leitura dos .nox do NOVA (formato binário .NET), sem precisar do NOVA
  ingest.py            junta .nox + planilha e tabelas num formato único
  planilha.py          gera a planilha de metadados de um lote de .nox
  qc.py                controle de qualidade automático
  preprocess.py        grade comum de potencial, suavização, linha de base
  features.py          descritores de pico e diferença entre estágios do sensor
  catalogo.py          modelos de classificação e regressão
  sisso.py             SISSO simplificado (descritor explícito)
  experimentos.py      protocolo de comparação: teste separado + validação cruzada agrupada
  figuras.py           figuras e tabelas para o notebook e o artigo
  model.py, predict.py treino, registro do modelo e previsão
  db.py                banco de dados SQLite
  cli.py               comando `fiep`
notebook/            entrega 1
api/                 entrega 2 (FastAPI + página, Dockerfile)
artigo/              entrega 3 (LaTeX; artigo/gerado/ vem de `fiep experimento --artigo`)
dados/               treino/ e validacao/ (seus dados, fora do Git) + exemplo_case/ (demonstração)
configs/default.toml todos os parâmetros
tests/               testes automáticos
tools/nox2excel.py   conversor avulso .nox -> Excel/CSV (e scripts para gerar o .exe)
docs/
```

Não vão para o Git: `.nox`, o conteúdo de `dados/treino` e `dados/validacao`, o banco
`dados/fiep.db`, `modelos/` e `resultados/`. **O repositório é público**: guarde os dados das
empresas no drive do projeto.

## Método em uma frase

O sinal usado é a **diferença entre os estágios do sensor no mesmo eletrodo** (antes e depois do
contato com a amostra); o teste é separado antes de qualquer escolha, os modelos são comparados
por validação cruzada **agrupada por amostra**, e o escolhido é registrado com configuração, grade
de potencial, limiar, métricas e commit do código.

## Resultado atual (conjunto de demonstração)

Ver `artigo/gerado/tabelas/` ou a seção 4 do notebook. Os números serão substituídos ao rodar
`fiep experimento --artigo` com os dados reais.

## Declaração de uso de IA

Ver [`IA_DECLARATION.md`](IA_DECLARATION.md).
