# Case — Smart Biosensors: Banco de Dados e Classificação de Contaminação Bacteriana

Solução para o case do Bolsista Pesquisador Machine Learning (RP 20061, Instituto SENAI de
Inovação Eletroquímica): organização e validação de dados de voltametria (biossensores),
construção de um banco rastreável e classificação de contaminação microbiológica a partir do
sinal eletroquímico.

## Estrutura do repositório

```
Dados/                      # arquivos brutos (não versionado — ver "Dados de entrada")
src/
  data_preparation.py       # Etapa 1: classifica arquivos pelo schema, junta e valida
  ingest_pipeline.py        # Etapa 2: features, modelagem baseline, exportação
  advanced_modeling.py      # Etapa 3: features de diferença entre estágios (melhoria testada)
run_pipeline.py             # CLI único que roda as 3 etapas em sequência
case_biossensor.ipynb       # notebook autocontido — mesma lógica, sem depender de src/
prepared/                   # gerado — tabelas canônicas (Etapa 1)
outputs/                    # gerado — banco de dados estruturado baseline (Etapa 2)
outputs_advanced/           # gerado — resultado da melhoria testada (Etapa 3)
requirements.txt
GUIA_DEFESA.md              # notas de estudo pessoais (não é entregável do case)
IA_DECLARATION.md
```

`prepared/`, `outputs/` e `Dados/` não são versionados (ver `.gitignore`) — são grandes
(o banco `.db` e o CSV em formato longo passam de 50MB) e 100% regeneráveis rodando o
pipeline. `outputs/model_metrics.csv`, `outputs/voltammograms_wide.csv`,
`outputs/feature_importance_regions.csv` etc. (os arquivos pequenos) ficam versionados como
amostra do banco estruturado.

## Dados de entrada

O pipeline reconhece automaticamente três papéis de arquivo **pelo conjunto de colunas**, não
pelo nome do arquivo — qualquer novo lote com esse schema é incorporado sem alterar código:

| Papel | Colunas obrigatórias | Conteúdo |
|---|---|---|
| Sinal (voltamograma) | `measurement_id`, `potential_V`, `current_uA` | 1 linha por ponto medido |
| Metadata | `measurement_id`, `sample_id`, `contamination_status` | liga sinal → amostra/estágio/qualidade |
| Plaqueamento | `sample_id`, `colony_count` | referência microbiológica (CFU) por amostra |

Coloque os três arquivos brutos dentro de uma pasta `Dados/` na raiz do projeto antes de
executar (local ou Colab — não vêm versionados no repositório).

## Como executar

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Opção A — CLI local, sem notebook (recomendado para rodar rápido/reproduzir)

```bash
python run_pipeline.py --input-dir Dados --output-dir .
```

Isso roda as 3 etapas em sequência e cria `prepared/`, `outputs/` e `outputs_advanced/` na
raiz do projeto. Opções úteis:

```bash
# pular a etapa 3 (mais lenta — treina 5 modelos em 10 seeds cada):
python run_pipeline.py --input-dir Dados --output-dir . --skip-advanced

# mudar a política de qualidade (padrão: só qc_flag=PASS):
python run_pipeline.py --input-dir Dados --output-dir . --keep-flags PASS REVIEW

# rodar as etapas individualmente:
python src/data_preparation.py --input-dir Dados --output-dir prepared
python src/ingest_pipeline.py --prepared-dir prepared --output-dir outputs
python src/advanced_modeling.py --prepared-dir prepared --output-dir outputs_advanced
```

### Opção B — Notebook (self-contained, cobre as 3 fases do case com narrativa/gráficos)

Abra `case_biossensor.ipynb` (local, Jupyter ou Google Colab) e rode `Restart & Run All`.
O notebook não importa nada de `src/` — toda a lógica está inline nele mesmo.

## Saídas geradas

**`prepared/`** (Etapa 1): `prepared_measurements.csv`, `prepared_samples.csv`,
`preparation_report.csv` (relatório de qualidade — duplicatas, ausências, medições órfãs).

**`outputs/`** (Etapa 2, banco baseline): `voltammograms_long.csv` / `voltammograms_wide.csv`,
`metadata_experiments.csv`, `biosensor_case.db` (SQLite, todas as tabelas), `model_metrics.csv`,
`test_predictions.csv`, `feature_importance_regions.csv`.

**`outputs_advanced/`** (Etapa 3, melhoria testada): `advanced_modeling_summary.csv`
(comparação de modelos × abordagens), `advanced_modeling_all_seeds.csv` (10 seeds),
`advanced_modeling_best_config_detail.json` (matriz de confusão + threshold ótimo da melhor
configuração).

## Metodologia (resumo)

- **Alvo**: `contamination_status` (0/1), vindo de `metadata_*.csv`.
- **Baseline (Etapa 2)**: 1 medição = 1 linha (um estágio do sensor por vez). Balanced
  accuracy ~50–57% — sinal fraco.
- **Melhoria testada (Etapa 3)**: 1 amostra+replicata = 1 linha, usando a *diferença* de sinal
  entre os estágios `capture_probe_16S_rRNA` e `capture_probe` (mesmo eletrodo, antes/depois
  do contato com o alvo) como feature, em vez de tratar cada estágio isoladamente. Balanced
  accuracy sobe para ~90–94% — ver `GUIA_DEFESA.md` para a explicação completa (por que
  funciona, checagem de vazamento de dados, trade-offs).
- **Validação**: split treino/teste e CV sempre agrupados por `sample_id` — réplicas/estágios
  da mesma amostra nunca ficam em treino e teste ao mesmo tempo.
- **Modelos**: Regressão Logística, LDA, Random Forest (Etapa 2) + SVM, Gradient Boosting
  (Etapa 3).

## Incluir novos dados

Adicione os novos arquivos (mesmo schema de colunas) à pasta `Dados/` e rode
`python run_pipeline.py --input-dir Dados --output-dir .` de novo — a classificação por schema
cobre isso automaticamente, sem precisar reescrever nada.

## Declaração de uso de IA

Ver `IA_DECLARATION.md`.
