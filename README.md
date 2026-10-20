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
# 1. coloque os .nox de um lote em dados/ (ex.: dados/empresa1/) e gere a planilha de metadados
fiep planilha --entrada dados/empresa1
#    preencha sample_id, replicate_id, sensor_state, contamination_status (e a carga, se houver)

# 2. importe para o banco (dados/fiep.db) — roda o controle de qualidade
fiep db importar --entrada dados
fiep db sql "SELECT * FROM v_replicatas WHERE n_aprovadas < 3"     # réplicas incompletas

# 3. divide em treino/validação/teste (50/25/25), compara representações x modelos e registra o
#    melhor (figuras e tabelas vão para o artigo)
fiep experimento --artigo

# 4. use o modelo
fiep servir                                    # página web + API
fiep prever --entrada nova_coleta/ --db dados/fiep.db
```

**Divisão dos dados:** o que estiver solto em `dados/` é dividido por amostra, estratificado pela
classe, em 50% treino, 25% validação e 25% teste (Hastie et al., *Elements of Statistical Learning*,
seção 7.2; configurável em `[divisao]`). O que estiver em `dados/treino/`, `dados/validacao/` ou
`dados/teste/` é somado ao conjunto correspondente — por exemplo, uma coleta de outra empresa em
`dados/teste/` vira validação externa.

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
  divisao.py           divisão treino / validação / teste (50/25/25 + pastas)
  experimentos.py      protocolo: escolha na validação, avaliação única no teste
  figuras.py           figuras e tabelas para o notebook e o artigo
  model.py, predict.py treino, registro do modelo e previsão
  db.py                banco de dados SQLite
  cli.py               comando `fiep`
notebook/            entrega 1
api/                 entrega 2 (FastAPI + página, Dockerfile)
artigo/              entrega 3 (LaTeX; artigo/gerado/ vem de `fiep experimento --artigo`)
dados/               seus dados (soltos e/ou treino/ validacao/ teste/, fora do Git) + exemplo_case/
configs/default.toml todos os parâmetros
tests/               testes automáticos
tools/nox2excel.py   conversor avulso .nox -> Excel/CSV (e scripts para gerar o .exe)
docs/
```

Não vão para o Git: `.nox`, os dados em `dados/` (exceto `exemplo_case/`), o banco
`dados/fiep.db`, `modelos/` e `resultados/`. **O repositório é público**: guarde os dados das
empresas no drive do projeto.

## Método em uma frase

O sinal usado é a **diferença entre os estágios do sensor no mesmo eletrodo** (antes e depois do
contato com a amostra); as amostras são divididas em treino, validação e teste, os modelos são
ajustados no treino (com validação cruzada **agrupada por amostra**), escolhidos na validação e
medidos uma única vez no teste; o escolhido é registrado com configuração, grade de potencial,
limiar, métricas e commit do código.

## Resultado atual (conjunto de demonstração)

Ver `artigo/gerado/tabelas/` ou a seção 4 do notebook. Os números serão substituídos ao rodar
`fiep experimento --artigo` com os dados reais.

## Declaração de uso de IA

Ver [`IA_DECLARATION.md`](IA_DECLARATION.md).
