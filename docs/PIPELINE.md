# Pipeline FIEP

Pacote `fiep/`: do arquivo do potenciostato (`.nox` do NOVA ou tabelas) até a previsão
"contaminada / não contaminada", com o **mesmo código** no treino e na predição.

```
            ┌──────────── TREINO ────────────┐
.nox + planilha ─┐                              │
tabelas (case) ──┴─► ingerir ─► QC ─► pré-processar ─► features ─► CV agrupada ─► modelos/<id>/
                                                                                    (modelo, grade,
            ┌──────────── PREDIÇÃO ──────────┐                                      config, métricas)
nova coleta ─────► ingerir ─► QC ─► pré-processar ─► features ─► modelo salvo ─► resultado.csv
                              │     (grade do treino)
                              └─► reprovadas: "REPETIR MEDIÇÃO" + motivo
```

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install -e ".[dev]"           # + ".[mlflow]" para registrar treinos no MLflow
pytest -q                         # testes (usam dados sintéticos)
```

## Comandos

Com banco de dados (recomendado; ver [`BANCO.md`](BANCO.md)):

```bash
fiep db importar --entrada Dados                     # grava em dados/fiep.db e roda o QC
fiep treinar --db dados/fiep.db                      # treina e registra o modelo no banco
fiep prever  --entrada nova_coleta/ --db dados/fiep.db
fiep db exportar --saida dados/fiep_banco.xlsx
```

Só com arquivos CSV:

```bash
fiep tudo    --entrada Dados                         # ingerir + treinar
fiep ingerir --entrada Dados --saida dados/processados
fiep qc      --dados dados/processados               # relatório de qualidade (qc.csv)
fiep treinar --dados dados/processados --config configs/default.toml
fiep prever  --entrada nova_coleta/ --saida resultado.csv
```

Sem instalar o pacote: `python -m fiep <comando> ...` na raiz do repositório.

## Entrada de dados

A pasta de entrada pode misturar fontes. Tabelas são reconhecidas **pelas colunas**:

| Papel | Colunas obrigatórias |
|---|---|
| Sinal (case) | `measurement_id`, `potential_V`, `current_uA` |
| Metadados (case) | `measurement_id`, `sample_id`, `contamination_status` |
| Plaqueamento | `sample_id`, `colony_count` |
| **Índice dos .nox** | `arquivo`, `sample_id` |

Para `.nox`, coloque na mesma pasta uma planilha (CSV ou Excel) com uma linha por arquivo.
Modelo em `templates/metadados_nox_modelo.csv`. Colunas usadas:

- `arquivo`: nome do `.nox` (com ou sem extensão) — obrigatório
- `sample_id`, `replicate_id`, `sensor_state` — obrigatórios para o modo de diferença entre estágios
- `contamination_status` (0/1) — obrigatório para treino; vazio na predição
- `qc_flag` (PASS/REVIEW/FAIL), `sample_log10_mean_cfu_ml`, `sensor_lot`, `surface_type`,
  `experimental_batch`, `operator_id`, `measurement_date` — recomendados

`sensor_state` usa os nomes do protocolo: `carbon_clean`, `capture_probe`,
`capture_probe_16S_rRNA` (configuráveis em `[dados].estagios`).

Do `.nox` a pipeline usa: DPV/SWV → `Potential applied` × `WE(1).δ.Current`;
CV/LSV → `Potential applied` × `WE(1).Current` (último scan por padrão). Correntes em µA.

## Controle de qualidade (`fiep/qc.py`)

| Regra | Resultado |
|---|---|
| menos de `min_pontos` pontos, ou muitos pontos inválidos | FAIL |
| corrente bruta acima de `max_abs_corrente_ua` (sobrecarga) | FAIL |
| potencial medido longe do aplicado em mais de `max_frac_desvio_e` dos pontos (.nox) | FAIL |
| corrente > `fator_outlier_lote` × mediana da mesma técnica/estágio | REVIEW |
| `qc_flag` da planilha | prevalece o pior entre planilha e regras |

Só entram no treino e na predição as medições com `qc_final` em `flags_aceitas`.

## Modelo e registro

- Validação cruzada **agrupada por amostra** (`StratifiedGroupKFold`).
- Limiar escolhido pelo J de Youden nas previsões fora da dobra.
- Cada treino cria `modelos/<id>/` com `modelo.joblib` (modelo + grade + config + features + limiar),
  `cartao.json` (métricas, commit do código, impressão digital dos dados), `metricas_cv.csv`,
  `previsoes_cv.csv`, `qc_treino.csv`; acrescenta uma linha em `modelos/registro.csv`
  e atualiza `modelos/ATUAL`.
- `modelos/` e `dados/` não vão para o Git: guarde-os no drive do projeto.

## Resultado atual (dados do case)

Treino com `Dados/` (200 amostras, 502 réplicas completas após o QC), CV agrupada em 5 dobras:

| Modelo | Acurácia balanceada | Sensibilidade | Especificidade | AUC |
|---|---|---|---|---|
| Regressão logística | 0,951 | 0,941 | 0,961 | 0,978 |
| Random Forest | 0,925 | 0,912 | 0,938 | 0,970 |
| SVM (RBF) | 0,921 | 0,895 | 0,946 | 0,965 |

## Próximos passos (plano de tarefas)

- T09: planilha de ligação voltamograma ↔ plaqueamento das coletas reais (o banco já liga `medicoes` ↔ `plaqueamentos` por `sample_id`).
- T13: comparar `linha_de_base = "linear_extremos"` com a correção do NOVA.
- T31: regressão da carga (log UFC/mL) usando `sample_log10_mean_cfu_ml`.
- T32: SISSO como candidato adicional em `fiep/model.py`.
