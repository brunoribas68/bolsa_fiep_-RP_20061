# Case — Smart Biosensors: Banco de Dados e Classificação de Contaminação Bacteriana

Solução para o case do Bolsista Pesquisador Machine Learning (RP 20061): organização e
validação de dados de voltametria (biossensores), construção de um banco rastreável e
classificação de contaminação microbiológica a partir do sinal eletroquímico.

## Estrutura

```
Dados/                         # arquivos brutos (não versionados aqui, ver "Dados de entrada")
src/
  data_preparation.py          # Etapa 1: classifica arquivos pelo schema, junta e valida
  ingest_pipeline.py           # Etapa 2: features, modelagem, validação e exportação
case_biossensor.ipynb          # notebook único com as 3 fases do case, já executado
requirements.txt
README.md
IA_DECLARATION.md
```

## Dados de entrada

O pipeline reconhece automaticamente três papéis de arquivo **pelo conjunto de colunas**,
não pelo nome do arquivo — então qualquer novo lote com esse schema é incorporado sem
alterar código:

| Papel | Colunas obrigatórias | Conteúdo |
|---|---|---|
| Sinal (voltamograma) | `measurement_id`, `potential_V`, `current_uA` | 1 linha por ponto medido |
| Metadata | `measurement_id`, `sample_id`, `contamination_status` | liga sinal → amostra/estágio/qualidade |
| Plaqueamento | `sample_id`, `colony_count` | referência microbiológica (CFU) por amostra |

Coloque os três arquivos dentro de uma pasta `Dados/` (mesmo nível do notebook) antes de
executar. No Colab: monte o Google Drive ou faça upload direto dos 3 arquivos para essa pasta.

## Como executar

### Opção A — Notebook (recomendado, cobre as 3 fases)

Abra `case_biossensor.ipynb` (local ou Google Colab) e rode todas as células, na ordem.
Ele importa `src/data_preparation.py` e `src/ingest_pipeline.py` internamente.

### Opção B — Linha de comando (os dois scripts separadamente)

```bash
pip install -r requirements.txt

# Etapa 1: arrumar os dados (classificar, juntar, validar)
python src/data_preparation.py --input-dir Dados --output-dir prepared

# Etapa 2: ingerir (features, modelos, exportação)
python src/ingest_pipeline.py --prepared-dir prepared --output-dir outputs
```

## Saídas geradas

Em `prepared/`:
- `prepared_measurements.csv` — sinal + metadata já unidos (formato longo).
- `prepared_samples.csv` — 1 linha por amostra, com CFU de plaqueamento agregado.
- `preparation_report.csv` — relatório de qualidade da junção (duplicatas, ausências, etc.).

Em `outputs/`:
- `voltammograms_long.csv` / `voltammograms_wide.csv` — formato longo e formato amplo (tabela analítica).
- `metadata_experiments.csv` — metadados por amostra.
- `biosensor_case.db` — SQLite com todas as tabelas acima, rastreável por `measurement_id`.
- `model_metrics.csv` — métricas de CV e teste para os 3 modelos (regressão logística, LDA, Random Forest).
- `test_predictions.csv` — predições do conjunto de teste.
- `feature_importance_regions.csv` — regiões do voltamograma mais relevantes para a classificação.

## Metodologia (resumo — detalhes no notebook)

- **Alvo**: `contamination_status` (0/1), vindo de `metadata_*.csv`.
- **Features**: corrente em cada potencial do voltamograma + descritores derivados
  (`peak_current`, `min_current`, `delta_current`).
- **Validação**: split treino/teste e validação cruzada **agrupados por `sample_id`**,
  para réplicas/estágios da mesma amostra nunca vazarem entre treino e teste.
- **Modelos**: regressão logística (baseline), LDA e Random Forest.
- **Métricas**: matriz de confusão, sensibilidade, especificidade, precisão, F1,
  balanced accuracy e ROC-AUC (quando aplicável).
- **Filtro de qualidade**: por padrão mantém medições com `qc_flag` em `PASS`/`REVIEW`
  (configurável via `--keep-flags` no `ingest_pipeline.py`).

## Incluir novos dados

Basta adicionar os novos arquivos (mesmo schema de colunas) à pasta de entrada e
reexecutar as duas etapas — não é necessário reconstruir manualmente nenhuma estrutura.

## Declaração de uso de IA

Ver `IA_DECLARATION.md`.
