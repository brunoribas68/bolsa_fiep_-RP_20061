# Como a pipeline funciona

```
dados/treino/ (.nox + planilha)  ─► ingerir ─► QC ─► banco SQLite (dados/fiep.db)
                                                          │
                                                          ▼
                        experimento: teste separado ─► CV agrupada (variantes × modelos) ─► melhor
                                                          │                                   │
                                     resultados/<id>/ (figuras, tabelas) ─► artigo/gerado/   modelos/<id>/
                                                                                              │
nova coleta (.nox + planilha) ─► ingerir ─► QC ─► mesma grade/config do modelo ─► previsão ◄──┘
                                              └─► reprovadas: "REPETIR MEDIÇÃO" + motivo
```

O **mesmo código** faz o pré-processamento no treino e na previsão; a grade de potencial, a
configuração, a lista de características e o limiar ficam gravados no modelo.

## Comandos

| Comando | O que faz |
|---|---|
| `fiep planilha --entrada dados/treino` | cria/completa a planilha de metadados do lote de `.nox` |
| `fiep db importar --entrada dados/treino` | lê `.nox`/tabelas, grava no banco e roda o QC |
| `fiep db resumo` / `fiep db sql "..."` / `fiep db exportar` | consulta e exporta o banco |
| `fiep experimento [--validacao dados/validacao] [--artigo]` | compara variantes × modelos, registra o melhor, gera figuras/tabelas |
| `fiep experimento --db dados/fiep.db --filtro-validacao "experimental_batch = 'B10'"` | idem, a partir do banco |
| `fiep treinar --db dados/fiep.db` | treino rápido com a configuração padrão (sem comparar variantes) |
| `fiep prever --entrada pasta/ [--db dados/fiep.db]` | classifica uma coleta nova com o modelo registrado |
| `fiep servir [--db dados/fiep.db]` | página web + API |
| `fiep qc --dados ...`, `fiep ingerir`, `fiep tudo` | fluxo só com arquivos CSV (sem banco) |

Sem instalar o pacote: `python -m fiep <comando>` na raiz do repositório.

## Entrada de dados

Ver [`dados/README.md`](../dados/README.md). Tabelas são reconhecidas **pelas colunas**:

| Papel | Colunas obrigatórias |
|---|---|
| Índice dos `.nox` (planilha) | `arquivo`, `sample_id` |
| Sinal (formato do case) | `measurement_id`, `potential_V`, `current_uA` |
| Metadados (formato do case) | `measurement_id`, `sample_id`, `contamination_status` |
| Plaqueamento | `sample_id`, `colony_count` |

Do `.nox`: DPV/SWV → potencial aplicado × `WE(1).δ.Current`; CV/LSV → potencial aplicado ×
`WE(1).Current` (último scan). Correntes em µA. O potencial medido e a corrente de base vão para o QC.
Só a técnica de `[dados].tecnica` (padrão DPV) entra no treino.

## Controle de qualidade (`fiep/qc.py`)

| Regra | Resultado |
|---|---|
| menos de `min_pontos` pontos ou muitos pontos inválidos | FAIL |
| corrente bruta acima de `max_abs_corrente_ua` (sobrecarga) | FAIL |
| potencial medido longe do aplicado em mais de `max_frac_desvio_e` dos pontos | FAIL |
| corrente > `fator_outlier_lote` × mediana da mesma técnica/estágio | REVIEW |
| `qc_flag` da planilha | vale o mais restritivo |

## Experimentos (`fiep/experimentos.py`)

1. **Teste separado antes de tudo**: `dados/validacao/` (validação externa) ou 20% das amostras,
   estratificado pela classe.
2. **Variantes** de representação: `dif_resumo`, `dif_curva`, `dif_curva_linha_base`,
   `dif_curva_sem_suavizar`, `estagio_final`.
3. **Modelos** (`fiep/catalogo.py`): regressão logística (L2 em 3 intensidades, L1), LDA, SVM RBF
   (2 valores de C), kNN, floresta aleatória, extra trees, gradient boosting e SISSO simplificado.
4. **Seleção** pela acurácia balanceada média na validação cruzada agrupada por amostra (treino);
   limiar pelo J de Youden nas previsões fora da dobra.
5. **Teste** de todas as combinações (para a tabela), mas o escolhido é o melhor da validação cruzada.
6. **Regressão** da carga (log10 UFC/mL) nas contaminadas: Ridge, PLS, SVR, RF, extra trees, GB.
7. Saídas em `resultados/<id>/`: `classificacao.csv`, `regressao.csv`, `resumo.json`,
   `figuras/*.png`, `tabelas/*.tex`; o melhor modelo (+ regressor) vai para `modelos/<id>/` e
   passa a ser o usado pela API. Com `--artigo`, figuras e tabelas são copiadas para `artigo/gerado/`.

Para testar mais modelos, acrescente-os em `fiep/catalogo.py`; para outra representação, em
`VARIANTES` de `fiep/experimentos.py`.

## Registro dos modelos

`modelos/<id>/modelo.joblib` (modelo + regressor + grade + config + features + limiar) e
`cartao.json` (métricas de CV e teste, variante, commit do código, impressão digital dos dados);
`modelos/registro.csv` acumula o histórico e `modelos/ATUAL` aponta para o modelo em uso. O banco
também registra modelos e previsões (`docs/BANCO.md`).
