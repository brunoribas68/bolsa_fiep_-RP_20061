# Pasta de dados

```
dados/
  treino/        <- coloque aqui os .nox (e/ou tabelas) + a planilha de metadados usados para TREINAR
  validacao/     <- validação externa: coletas que o modelo nunca viu (ex.: outra empresa/outro lote).
                    Só são usadas no fim, para medir o desempenho real. Mesmo formato de treino/.
  exemplo_case/  <- dados do case (sintéticos), usados nos testes e para demonstrar a pipeline
  fiep.db        <- banco SQLite gerado pela pipeline (não vai para o Git)
```

Nada dentro de `treino/` e `validacao/` vai para o Git (o repositório é público).

## Como preparar um lote de .nox

1. Copie os `.nox` para `dados/treino/` (pode usar subpastas por empresa/data).
2. Gere a planilha de metadados já com a lista de arquivos:

   ```bash
   fiep planilha --entrada dados/treino
   ```

   Isso cria `dados/treino/metadados_nox.csv` com uma linha por arquivo. Se a planilha já existir,
   só os arquivos novos são acrescentados.
3. Preencha as colunas (Excel ou LibreOffice, salvando como CSV):

   | Coluna | Obrigatória | Exemplo |
   |---|---|---|
   | `sample_id` | sim | `EMP1_S001` |
   | `replicate_id` | sim | `1` (eletrodo/réplica) |
   | `sensor_state` | sim | `carbon_clean`, `capture_probe` ou `capture_probe_16S_rRNA` |
   | `contamination_status` | sim no treino | `1` contaminada, `0` não contaminada |
   | `sample_log10_mean_cfu_ml` | para regressão | `5.2` |
   | `qc_flag` | não | `PASS`, `REVIEW`, `FAIL` |
   | `target_bacterium`, `surface_type`, `sensor_lot`, `experimental_batch`, `operator_id`, `measurement_date` | recomendadas | |

4. Importe e confira:

   ```bash
   fiep db importar --entrada dados/treino
   fiep db sql "SELECT * FROM v_replicatas WHERE n_aprovadas < 3"
   ```

Cada réplica precisa dos **três estágios do sensor** medidos no mesmo eletrodo para entrar no
modelo de diferença entre estágios.
