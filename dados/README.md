# Pasta de dados

```
dados/
  (seus .nox + planilha)  <- SOLTOS aqui: divididos em treino / validação / teste (50/25/25)
  treino/        <- opcional: vai INTEIRO para o treino (somado à parte sorteada)
  validacao/     <- opcional: vai inteiro para a validação (escolha do modelo)
  teste/         <- opcional: vai inteiro para o teste (ex.: coleta de outra empresa/lote = validação externa)
  exemplo_case/  <- dados do case (sintéticos), usados só quando não há nenhum outro dado
  fiep.db        <- banco SQLite gerado pela pipeline (não vai para o Git)
```

Nada disso vai para o Git (o repositório é público), exceto `exemplo_case/` e este arquivo.
Pode usar subpastas para organizar (ex.: `dados/empresa1/2026-11/`): tudo fora das quatro pastas
reservadas conta como dado solto.

## Regra da divisão

1. Tudo o que estiver **solto em `dados/`** é dividido **por amostra** (todas as réplicas e estágios de
   uma amostra ficam no mesmo conjunto), estratificado pela classe, em **50% treino, 25% validação e
   25% teste** — a divisão típica sugerida por Hastie, Tibshirani e Friedman (*The Elements of
   Statistical Learning*, 2.ª ed., seção 7.2). As proporções ficam em `[divisao]` de
   `configs/default.toml`.
2. O que estiver em **`dados/treino/`, `dados/validacao/` ou `dados/teste/`** vai inteiro para aquele
   conjunto e é **somado** à parte sorteada. Uma amostra que esteja numa dessas pastas nunca é sorteada
   para outro conjunto (e a mesma amostra em duas pastas é erro).
3. Se a validação ou o teste ficarem vazios (ex.: só há dados em `dados/treino/`), eles são sorteados
   do treino nas mesmas proporções.
4. Sem dado nenhum, usa `dados/exemplo_case/` (demonstração).

Para que serve cada conjunto:

| Conjunto | Uso |
|---|---|
| treino | ajustar os modelos; a validação cruzada agrupada dentro dele dá o limiar de decisão e a estabilidade |
| validação | escolher a representação × modelo (maior acurácia balanceada) |
| teste | medir **uma vez** o modelo escolhido, re-treinado com treino + validação; não participa de nenhuma escolha |

Com o banco (`fiep db importar --entrada dados`), cada parte é gravada com o seu conjunto e
`fiep experimento --db dados/fiep.db` aplica a mesma regra. Também é possível definir conjuntos por
filtro SQL: `--filtro-teste "sensor_lot = 'L09'"`.

## Como preparar um lote de .nox

1. Copie os `.nox` para uma subpasta de `dados/` (ex.: `dados/empresa1/`, que conta como dado solto)
   ou para `dados/teste/` se for uma coleta reservada para a validação externa.
2. Gere a planilha de metadados já com a lista de arquivos:

   ```bash
   fiep planilha --entrada dados/empresa1
   ```

   Isso cria `dados/empresa1/metadados_nox.csv` com uma linha por arquivo. Se a planilha já existir,
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
   fiep db importar --entrada dados
   fiep db sql "SELECT * FROM v_replicatas WHERE n_aprovadas < 3"
   ```

Cada réplica precisa dos **três estágios do sensor** medidos no mesmo eletrodo para entrar no
modelo de diferença entre estágios.
