# Projeto FIEP — monitoramento microbiológico de superfícies por voltametria + ML

Pipeline para detectar contaminação microbiana em superfícies a partir de voltamogramas de
biossensores (eletrodos impressos com sonda de captura para rRNA 16S): leitura dos arquivos do
potenciostato, controle de qualidade, banco de dados rastreável, treino de modelos e previsão para
amostras novas.

O repositório começou como a solução do case do processo seletivo (RP 20061, Instituto SENAI de
Inovação Eletroquímica). Os scripts do case continuam em `src/` como referência; o código usado
daqui em diante é o pacote `fiep/`.

## Estrutura

```
fiep/                       # pacote da pipeline (código de produção)
  io/nox.py, io/nrbf.py     #   leitura dos arquivos .nox do NOVA (sem precisar do NOVA)
  ingest.py                 #   junta tabelas e .nox num formato canônico
  qc.py                     #   controle de qualidade automático
  preprocess.py             #   grade comum de potencial, suavização, linha de base
  features.py               #   descritores de pico e diferença entre estágios do sensor
  model.py                  #   validação cruzada agrupada, escolha e registro do modelo
  predict.py                #   previsão para medições novas
  db.py                     #   banco de dados SQLite
  cli.py                    #   comando `fiep`
configs/default.toml        # todos os parâmetros da pipeline
templates/                  # modelo da planilha de metadados para os .nox
tests/                      # testes automáticos (dados sintéticos)
tools/nox2excel.py          # conversor avulso .nox -> Excel/CSV (+ scripts para gerar o .exe)
docs/PIPELINE.md            # como a pipeline funciona
docs/BANCO.md               # esquema do banco e consultas úteis
case_biossensor.ipynb       # notebook: fases 1-3 do case + Fase 4 (pipeline e banco)
src/                        # scripts originais do case (referência)
Dados/                      # dados do case (versionados)
prepared/, outputs_advanced/# resultados do case (versionados)
GUIA_DEFESA.md              # notas de estudo do case
IA_DECLARATION.md
```

Não vão para o Git (ver `.gitignore`): arquivos `.nox`, `dados/` (banco e dados processados),
`modelos/`, `nova_coleta/`, `*.db`.

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate             # Linux/Mac: source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                          # confere a instalação
```

Requer Python 3.11 ou mais recente.

## Uso rápido

```bash
# 1. importar dados para o banco (dados/fiep.db) — tabelas do case e/ou .nox
fiep db importar --entrada Dados
fiep db importar --entrada coleta_empresa1/

# 2. treinar a partir do banco (o modelo fica em modelos/<id>/ e registrado no banco)
fiep treinar --db dados/fiep.db

# 3. prever medições novas e gravar o resultado no banco
fiep prever --entrada nova_coleta/ --db dados/fiep.db --saida resultado.csv

# consultar e exportar
fiep db resumo
fiep db sql "SELECT * FROM v_replicatas WHERE n_aprovadas < 3"
fiep db exportar --saida dados/fiep_banco.xlsx
```

Sem instalar o pacote, use `python -m fiep ...` na raiz do repositório. Detalhes em
[`docs/PIPELINE.md`](docs/PIPELINE.md) e [`docs/BANCO.md`](docs/BANCO.md).

## Dados de entrada

A pasta de entrada pode misturar fontes. Tabelas (`.csv`, `.xlsx`) são reconhecidas **pelas
colunas**, não pelo nome do arquivo:

| Papel | Colunas obrigatórias | Conteúdo |
|---|---|---|
| Sinal | `measurement_id`, `potential_V`, `current_uA` | 1 linha por ponto do voltamograma (formato do case) |
| Metadados | `measurement_id`, `sample_id`, `contamination_status` | amostra, réplica, estágio do sensor, lote, qualidade |
| Plaqueamento | `sample_id`, `colony_count` | referência microbiológica (UFC) por placa |
| **Índice dos .nox** | `arquivo`, `sample_id` | 1 linha por arquivo `.nox`, com os metadados dele |

**Arquivos `.nox` do NOVA** (testado com DPV, SWV e CV): coloque-os na pasta junto com a planilha de índice
(modelo em [`templates/metadados_nox_modelo.csv`](templates/metadados_nox_modelo.csv)). Para treinar,
cada linha precisa de `sample_id`, `replicate_id`, `sensor_state` (`carbon_clean`, `capture_probe`,
`capture_probe_16S_rRNA`) e `contamination_status`; na previsão, `contamination_status` fica vazio.
Do `.nox` são usados o potencial aplicado e a corrente (δi em DPV/SWV), além do potencial medido e da
corrente bruta, que alimentam o controle de qualidade.

## Controle de qualidade

Cada medição é avaliada automaticamente e reprovada se tiver sobrecarga de corrente, potencial
medido longe do aplicado, poucos pontos ou muitos pontos inválidos; correntes muito acima das do
mesmo lote ficam em revisão. O resultado é combinado com o `qc_flag` da planilha (vale o pior) e
fica registrado no banco. Medições reprovadas não entram no treino e, na previsão, voltam como
"REPETIR MEDIÇÃO" com o motivo. Limites em `configs/default.toml`.

## Resultado atual (dados do case)

Validação cruzada em 5 dobras **agrupadas por amostra**, 200 amostras / 502 réplicas completas
após o QC, features de diferença entre estágios do sensor:

| Modelo | Acurácia balanceada | Sensibilidade | Especificidade | AUC |
|---|---|---|---|---|
| Regressão logística | 0,951 | 0,941 | 0,961 | 0,978 |
| Random Forest | 0,925 | 0,912 | 0,938 | 0,970 |
| SVM (RBF) | 0,919 | 0,893 | 0,946 | 0,965 |

Em 10 amostras deixadas fora do treino (27 réplicas), todas foram classificadas corretamente.

## Notebook

Abra `case_biossensor.ipynb` **a partir da raiz do repositório** e rode tudo. As fases 1–3
reproduzem a análise do case com os scripts de `src/`; a Fase 4 mostra a pipeline `fiep` passo a
passo (ingestão, QC, pré-processamento, treino, previsão, banco de dados e `.nox` reais). Para a
seção de `.nox`, coloque os arquivos e a planilha numa pasta `nova_coleta/`.

## Scripts originais do case (`src/`)

```bash
pip install -r requirements.txt
python src/run_pipeline.py --input-dir Dados --output-dir .          # 3 etapas do case
python src/run_pipeline.py --input-dir Dados --output-dir . --skip-advanced
```

Geram `prepared/` (tabelas canônicas e relatório de qualidade), `outputs/` (banco SQLite do
case, métricas, importância por região) e `outputs_advanced/` (comparação da abordagem de
diferença entre estágios). Resumo da metodologia do case:

- **Baseline**: 1 medição = 1 linha (um estágio do sensor por vez) — acurácia balanceada ~50–57%.
- **Melhoria**: 1 amostra+réplica = 1 linha, usando a *diferença* entre os estágios
  `capture_probe_16S_rRNA` e `capture_probe` (mesmo eletrodo, antes/depois do contato com o alvo) —
  ~90–94%. Explicação completa e checagem de vazamento de dados em `GUIA_DEFESA.md`.
- **Validação**: sempre agrupada por `sample_id`.

## Segurança dos dados

Este repositório é **público**. Dados reais do projeto (arquivos `.nox`, planilhas das empresas
validadoras, o banco `dados/fiep.db` e os modelos treinados) não devem ser commitados — o
`.gitignore` já os exclui. Guarde-os no drive do projeto.

## Declaração de uso de IA

Ver `IA_DECLARATION.md`.
