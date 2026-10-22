# Como a pipeline funciona

```
dados/ ou plataforma (.nox / Excel do NOVA) ─► ingerir ─► QC ─► banco (dados/fiep.db)
                                                   │
                                                   ▼
          divisão por amostra: treino 50% · validação 25% · teste 25% (+ pastas treino/ validacao/ teste/)
                                                   │
     treino: ajuste + CV agrupada ─► validação: escolha ─► treino+validação: re-treino ─► teste (uma vez)
                                                          │                                   │
                                     resultados/<id>/ (figuras, tabelas) ─► artigo/gerado/   modelos/<id>/
                                                                                              │
nova coleta (.nox / Excel)    ─► ingerir ─► QC ─► mesma grade/config do modelo ─► previsão ◄──┘
                                              └─► reprovadas: "REPETIR MEDIÇÃO" + motivo
```

O **mesmo código** faz o pré-processamento no treino e na previsão; a grade de potencial, a
configuração, a lista de características e o limiar ficam gravados no modelo.

## Comandos

| Comando | O que faz |
|---|---|
| `fiep planilha --entrada dados/empresa1` | cria `amostras.csv` (uma linha por amostra) e `metadados_nox.csv` (conferência), já com amostra, réplica, estágio e data deduzidos |
| `fiep db importar --entrada dados` | lê `.nox`/tabelas, grava no banco (com o conjunto de cada pasta) e roda o QC |
| `fiep db resumo` / `fiep db sql "..."` / `fiep db exportar` | consulta e exporta o banco |
| `fiep experimento [--dados dados] [--artigo]` | divide os dados, compara variantes × modelos, registra o melhor, gera figuras/tabelas |
| `fiep experimento --db dados/fiep.db --filtro-teste "experimental_batch = 'B10'"` | idem, a partir do banco (o lote B10 vai inteiro para o teste) |
| `fiep treinar --db dados/fiep.db` | treino rápido com a configuração padrão (sem comparar variantes) |
| `fiep prever --entrada pasta/ [--db dados/fiep.db]` | classifica uma coleta nova com o modelo registrado |
| `fiep servir [--db dados/fiep.db]` | página web + API |
| `fiep qc --dados ...`, `fiep ingerir`, `fiep tudo` | fluxo só com arquivos CSV (sem banco) |

Sem instalar o pacote: `python -m fiep <comando>` na raiz do repositório.

## Entrada de dados

Ver [`dados/README.md`](../dados/README.md). Tabelas são reconhecidas **pelas colunas**:

| Papel | Colunas obrigatórias |
|---|---|
| Índice dos `.nox` (planilha, opcional: corrige o que foi deduzido) | `arquivo`, `sample_id` |
| Sinal (formato do case) | `measurement_id`, `potential_V`, `current_uA` |
| Metadados (formato do case) | `measurement_id`, `sample_id`, `contamination_status` |
| Plaqueamento | `sample_id`, `colony_count` |
| Amostras (rótulo e carga, uma linha por amostra) | `sample_id`, `contamination_status` |

Metadados sem planilha são deduzidos por `fiep/metadados_auto.py`: etapa pelo nome do
arquivo/procedimento, eletrodo pelo `E1`, `E2`… do nome (ou o canal do potenciostato), amostra pela
pasta, rótulo pelo nome da pasta.

## Protocolos (`fiep/protocolos.py`)

O protocolo do biossensor (etapas na ordem e técnica) é reconhecido pelos nomes das etapas
(`[dados].protocolo = "auto"`) e gravado no modelo: **NS1** (SWV: bloqueio → mAb_NS1 → final) e
**rRNA 16S** do case (DPV: carbon_clean → capture_probe → capture_probe_16S_rRNA). O modelo usa a
diferença entre a última etapa e a anterior no mesmo eletrodo. Só medições da técnica do protocolo
entram no treino.

`.nox` ou Excel/CSV exportado pelo NOVA (`fiep/io/nox.py: exportacao_to_curves`; aba `Info` do
`fiep excel` traz canal e procedimento). Do `.nox`: DPV/SWV → potencial aplicado × `WE(1).δ.Current`; CV/LSV → potencial aplicado ×
`WE(1).Current` (último scan). Correntes em µA. O potencial medido e a corrente de base vão para o QC.
No Excel, a técnica vem do nome/procedimento ou das colunas (forward/backward = SWV).

## Controle de qualidade (`fiep/qc.py`)

| Regra | Resultado |
|---|---|
| menos de `min_pontos` pontos ou muitos pontos inválidos | FAIL |
| corrente bruta acima de `max_abs_corrente_ua` (sobrecarga) | FAIL |
| potencial medido longe do aplicado em mais de `max_frac_desvio_e` dos pontos, descontado o deslocamento constante (amplitude do pulso na SWV) | FAIL |
| corrente > `fator_outlier_lote` × mediana da mesma técnica/etapa | REVIEW |
| `qc_flag` da planilha | vale o mais restritivo |

## Experimentos (`fiep/experimentos.py`)

1. **Divisão por amostra** (`fiep/divisao.py`): dados soltos em `dados/` → 50% treino, 25% validação,
   25% teste, estratificado pela classe (Hastie et al., *Elements of Statistical Learning*, 7.2;
   proporções em `[divisao]`). Pastas `dados/treino|validacao|teste/` são somadas ao conjunto. A
   grade de potencial é definida só no treino.
2. **Variantes** de representação: `dif_resumo`, `dif_curva`, `dif_curva_linha_base`,
   `dif_curva_sem_suavizar`, `estagio_final`.
3. **Modelos** (`fiep/catalogo.py`): regressão logística (L2 em 3 intensidades, L1), LDA, SVM RBF
   (2 valores de C), kNN, floresta aleatória, extra trees, gradient boosting e SISSO simplificado.
4. **Treino**: cada combinação é ajustada no treino; a validação cruzada agrupada por amostra
   (StratifiedGroupKFold) dá a média ± desvio e o limiar (J de Youden nas previsões fora da dobra).
5. **Escolha na validação**: maior acurácia balanceada no conjunto de validação (desempate: AUC na
   validação e acurácia da CV). **Teste**: cada combinação é re-treinada com treino + validação e
   medida no teste; o número que vale é o da combinação escolhida — o teste não escolhe nada.
6. **Regressão** da carga (log10 UFC/mL) nas contaminadas: Ridge, PLS, SVR, RF, extra trees, GB;
   mesmo protocolo (escolha pelo RMSE na validação).
7. **Por amostra**: no teste, a probabilidade da amostra é a média das réplicas
   (`teste_por_amostra.csv`); com `[niveis]` configurado, a carga estimada vira nível de
   contaminação e a matriz de confusão dos níveis vai para `niveis_teste.csv`.
8. Saídas em `resultados/<id>/`: `classificacao.csv`, `regressao.csv`, `resumo.json`,
   `figuras/*.png`, `tabelas/*.tex`; o melhor modelo (+ regressor) vai para `modelos/<id>/` e
   passa a ser o usado pela API. Com `--artigo`, figuras e tabelas são copiadas para `artigo/gerado/`.

Para testar mais modelos, acrescente-os em `fiep/catalogo.py`; para outra representação, em
`VARIANTES` de `fiep/experimentos.py`.

## Registro dos modelos

`modelos/<id>/modelo.joblib` (modelo + regressor + grade + config + features + limiar) e
`cartao.json` (métricas de CV, validação e teste, divisão usada, variante, commit do código, impressão digital dos dados);
`modelos/registro.csv` acumula o histórico e `modelos/ATUAL` aponta para o modelo em uso. O banco
também registra modelos e previsões (`docs/BANCO.md`).
