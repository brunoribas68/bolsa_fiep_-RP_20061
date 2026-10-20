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

**Não é preciso preencher arquivo por arquivo.** A pipeline deduz sozinha, de cada `.nox`:

| Campo | De onde vem |
|---|---|
| estágio do sensor | nome do arquivo (`limpo`, `sonda`/`oligo`, `rRNA`...) ou, se ele não disser, o nome do procedimento gravado no `.nox` |
| réplica (eletrodo) | canal do potenciostato gravado no `.nox` (`MAC80058#2` → `2`) |
| amostra | a **pasta** do arquivo: uma pasta = uma amostra |
| data | gravada no `.nox` |
| contaminada ou não | nome da pasta: `contaminada/`, `nao_contaminada/`, `positivo/`, `negativo/`, `controle_neg/` |

O jeito mais simples é organizar as pastas assim e não preencher nada:

```
dados/empresa1/
  contaminada/
    A01/   <- os .nox dos 3 estágios de todos os eletrodos da amostra A01
    A02/
  nao_contaminada/
    B01/
```

O único dado que não sai do voltamograma é o resultado do plaqueamento (é o que o modelo aprende
a prever). Se ele não estiver no nome das pastas, informe uma vez **por amostra**:

```bash
fiep planilha --entrada dados/empresa1
```

Isso cria duas tabelas na pasta, já preenchidas com o que foi deduzido:

- `amostras.csv` — **uma linha por amostra**: complete `contamination_status` (1 = contaminada,
  0 = não) e, se houver, `sample_log10_mean_cfu_ml`. As colunas `estagios_encontrados` e
  `observacoes` mostram se falta algum estágio.
- `metadados_nox.csv` — uma linha por arquivo, só para **conferir**. Corrija o que estiver errado;
  o que estiver preenchido nela vence o que a pipeline deduziu (`preenchido_auto` diz o que foi
  deduzido). Rodar de novo só acrescenta arquivos novos.

Se os arquivos seguem um padrão de nome (ex.: `EMP1-S07-R3-sonda.nox`), dá para ensinar a pipeline
em `[metadados].padrao_nome` de `configs/default.toml`.

Depois:

```bash
fiep db importar --entrada dados
fiep db sql "SELECT * FROM v_replicatas WHERE n_aprovadas < 3"     # réplicas incompletas
fiep experimento --artigo
```

Cada réplica precisa dos **três estágios do sensor** medidos no mesmo eletrodo (mesmo canal) para
entrar no modelo de diferença entre estágios. Se faltar algo, `fiep experimento` diz o quê.
