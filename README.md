# Case - Organização e modelagem de sinais eletroquímicos

Este repositório entrega uma solução reprodutível para:
- leitura e integração de arquivos de voltametria;
- validação de qualidade dos dados;
- organização em banco rastreável;
- preparação de features para machine learning;
- treinamento/validação de modelos e exportação de resultados.

## Estrutura

- `/src/biosensor_pipeline.py`: funções do pipeline (ingestão, validação, organização, modelagem e exportação).
- `/src/run_pipeline.py`: CLI para execução fim-a-fim.
- `/notebooks/case_biossensor.ipynb`: notebook executável para análise e apresentação.
- `/requirements.txt`: dependências.
- `/IA_DECLARATION.md`: declaração de uso de IA.

## Requisitos

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Formato esperado dos dados

Os arquivos podem ser `.csv`, `.txt`, `.xlsx` ou `.xls` e devem conter colunas reconhecíveis de:
- potencial (`potential`, `potencial`, `e`, `voltage`, `v`)
- corrente (`current`, `corrente`, `i`, `ua`, `ma`)

Metadados (bactéria, amostra, replicata, lote, batelada e condição) são lidos de colunas existentes e/ou inferidos do nome dos arquivos.

## Execução

```bash
python src/run_pipeline.py --input-dir /caminho/para/dados_brutos --output-dir /caminho/saida
```

## Saídas geradas

No diretório de saída:
- `voltammograms_long.csv` (formato longo)
- `voltammograms_wide.csv` (formato amplo)
- `metadata_experiments.csv`
- `validation_report.csv`
- `biosensor_case.db` (SQLite)
- `model_metrics.csv` (quando há dados suficientes)
- `test_predictions.csv` (quando há dados suficientes)
- `feature_importance_regions.csv` (quando há dados suficientes)

## Pipeline implementado

1. Leitura dos arquivos brutos.
2. Validação de duplicidade, ausências, formato, incompletude e inconsistências.
3. Tratamento e padronização de identificadores.
4. Organização em tabelas relacionáveis (metadados + sinais).
5. Preparação da matriz de features (voltamograma completo + descritores derivados).
6. Modelagem com divisão por amostra (sem vazamento de replicatas), validação cruzada agrupada e comparação de modelos.
7. Exportação dos dados processados e resultados.

## Modelos e métricas

Modelos:
- Regressão logística (baseline)
- LDA
- Random Forest

Métricas:
- Matriz de confusão
- Sensibilidade
- Especificidade
- Precisão
- F1-score
- Balanced accuracy
- ROC-AUC (quando aplicável)

## Inclusão de novos dados

Para incorporar novos arquivos, basta adicioná-los ao diretório de entrada e reexecutar o pipeline.
Não é necessário reconstruir manualmente as estruturas.
