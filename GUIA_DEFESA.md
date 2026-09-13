# Guia de Defesa — Case Smart Biosensors (RP 20061)

> Números deste guia = a fonte oficial (`outputs/` gerado no seu ambiente, `qc_flag = PASS`,
> 1.695 medições). É a mesma fonte usada no notebook e nos slides — todos batem entre si.

---

## 1. Overview do código

### 1.1 `data_preparation.py` — Etapa 1 ("arrumar os dados")

| Função | O que faz |
|---|---|
| `_read_any` | Lê `.csv`/`.xlsx`, normaliza nomes de coluna (minúsculo, sem espaço/acento estranho). |
| `classify_file` | Compara as colunas do arquivo com 3 conjuntos obrigatórios (`ROLE_REQUIRED_COLUMNS`) e decide: **signal**, **metadata** ou **plating**. Não olha o nome do arquivo. |
| `discover_and_classify` | Varre a pasta inteira, classifica cada arquivo, registra os que não bateram com nenhum schema. |
| `build_prepared_measurements` | `merge` sinal + metadata por `measurement_id` (left join). Calcula duplicidade, pontos ausentes, medições sem par. |
| `build_prepared_samples` | Agrega plaqueamento por `sample_id` (`groupby.mean`) e junta com metadados de amostra. |
| `prepare()` | Função pública: chama tudo acima e escreve `prepared_measurements.csv`, `prepared_samples.csv`, `preparation_report.csv`. |

**Por que classificar por schema, não por nome de arquivo?** Porque assim um lote novo de
dados — mesmo com nome de arquivo diferente — é reconhecido automaticamente. Isso responde
direto à dica do slide de Fase 2: *"permitir que novos arquivos... sejam incorporados... sem
reconstruir manualmente"*.

### 1.2 `ingest_pipeline.py` — Etapa 2 ("ingerir")

| Função | O que faz |
|---|---|
| `load_prepared` | Lê os CSVs gerados na Etapa 1. |
| `filter_by_quality` | Mantém só as medições com `qc_flag` desejado (padrão: `PASS`). |
| `build_wide_table` | Pivota longo→amplo (1 linha por medição, 1 coluna por potencial). Usa um valor-sentinela pra evitar perder linhas quando `contamination_status`/`qc_flag` têm `NaN` no índice do pivot (bug do pandas que apareceu no teste — ver seção 5). |
| `prepare_features` | Monta `X` (correntes + `peak_current`/`min_current`/`delta_current`), `y` (`contamination_status`), `groups` (`sample_id`). |
| `train_and_evaluate` | `GroupShuffleSplit` (treino/teste) + `GroupKFold` (CV), treina Regressão Logística, LDA e Random Forest, calcula todas as métricas pedidas. Tem fallback pra não quebrar se uma dobra cair com 1 classe só (outro bug corrigido — seção 5). |
| `summarize_relevant_regions` | `|coeficiente|` da regressão logística padronizada, por potencial → proxy de "região mais relevante". |
| `export` / `run()` | Grava tudo em CSV + SQLite; decide se há dados suficientes pra modelar. |

### 1.3 O notebook (`case_biossensor.ipynb`)

- **Fase 1**: chama `data_preparation.prepare`, mostra o relatório de qualidade, checa
  pontos-por-curva e réplicas discrepantes, plota voltamogramas reais e compara os 3 estágios.
- **Fase 2**: chama `ingest_pipeline.run`, mostra a tabela wide, consulta o SQLite via SQL.
- **Fase 3**: métricas dos 3 modelos, matriz de confusão, importância por região,
  comparação pico-vs-completo, checagem de efeito de lote/batelada, interpretação escrita.

---

## 2. Números pra ter na ponta da língua

- **200 amostras** (100 *E. coli* / 100 *S. aureus*), **1.800 medições brutas**, **1.695 após
  filtro `qc_flag = PASS`** (105 descartadas: 79 REVIEW + 26 FAIL).
- **150 contaminadas / 50 não contaminadas** — desbalanceamento ~3:1.
- **Zero `measurement_id` órfão** entre os 3 arquivos — junção por schema funcionou 100%.
- **Melhor modelo (medição isolada, baseline): Random Forest** — balanced accuracy **57,1%**,
  sensibilidade **77,9%**, especificidade **36,2%**, ROC-AUC **0,582**.
- **Melhor modelo (diferença entre estágios, melhoria testada): Regressão Logística** —
  balanced accuracy **93,7% ± 1,6%** (média de 10 seeds), ROC-AUC **0,982**. Matriz de
  confusão (seed 42): `[[19,2],[7,90]]`.
- **Efeito de lote significativo** (ANOVA, p<0,0001): pico médio de 19,9 µA (lote L01) a
  22,7 µA (lote L05) — a diferença entre estágios cancela boa parte desse efeito.
- **Pico vs. curva completa** (split único, não é CV, abordagem baseline): pico sozinho teve
  balanced accuracy 58,9% vs. 54,8% da curva completa — não dá pra afirmar que a curva
  completa ajuda mais nessa abordagem sem validação cruzada dedicada.

---

## 2.1 A melhoria testada — diferença entre estágios (NOVO)

**A pergunta que motivou**: "o que traria mais acurácia?" — a resposta testada e confirmada
foi calcular a diferença de sinal entre `capture_probe_16S_rRNA` e `capture_probe` (mesmo
eletrodo, antes/depois do contato com o alvo), em vez de tratar cada estágio como observação
independente.

**Por que funcionou tão bem (salto de 57% → 94% de balanced accuracy)**: como os 3 estágios
são medidos no mesmo eletrodo físico da mesma réplica, o efeito de lote/eletrodo afeta os 3
estágios de forma parecida. Ao subtrair um estágio do outro, esse deslocamento sistemático se
cancela, e sobra majoritariamente o sinal causado pela ligação com o alvo.

**Checagem de vazamento feita antes de aceitar o resultado** (pergunta que a banca PODE fazer:
"como você sabe que não é vazamento de dado?"):
- Nenhum lote é 100% puro de uma classe (`sensor_lot` não determina o rótulo).
- A feature isolada mais correlacionada com o rótulo tem `r=0,70` — forte, mas longe de 1,0.
- Resultado estável em 10 seeds diferentes de split treino/teste (desvio de só 1,6 p.p.).

**O que foi implementado** (`src/advanced_modeling.py`):
1. Reestruturação pra 1 linha por amostra+replicata (combinando os 3 estágios).
2. Suavização Savitzky-Golay antes de extrair descritores.
3. Descritores novos: área sob a curva, potencial do pico, largura do pico.
4. Curva de diferença completa entre estágios como feature (não só o delta do pico).
5. SVM (RBF) e Gradient Boosting adicionados à comparação.
6. 10 seeds de split treino/teste (não só 1) — média ± desvio.
7. Threshold de decisão otimizado (Youden), não só o corte padrão 0,5.

**Trade-off honesto**: perde ~16% das réplicas (as que não têm os 3 estágios com PASS
simultaneamente — 502 de 600). E a validação, embora robusta a 10 seeds, ainda é no mesmo
dataset — validação externa (novo lote, novo operador) é o próximo teste necessário antes de
qualquer uso real do sensor.

---

## 3. Roteiro sugerido (30 min, 3 fases de ~10 min)

**Fase 1 (slides 3–7):** conte a história dos 3 arquivos → os 3 estágios do sensor → qualidade
(zero órfãos, 94% PASS) → mostre a curva real com o pico DPV → compare estágios/status.
*Ponto-chave a verbalizar:* a diferença entre contaminada/não é sutil (21,45 vs 21,15 µA de
pico médio) — já prepara a plateia pro resultado modesto da Fase 3, sem precisar "vender"
como se fosse óbvio.

**Fase 2 (slides 8–9):** pipeline em 2 scripts, por quê (separação de responsabilidades: um
arruma, outro ingere/modela), o schema-based file classification, IDs únicos, banco SQLite
rastreável, longo vs. amplo.

**Fase 3 (slides 10–14):** alvo e por quê, validação agrupada por amostra e por quê,
comparação dos 3 modelos, matriz de confusão do Random Forest, regiões relevantes,
interpretação com as limitações reais (efeito de lote, base desbalanceada, sinal fraco).

---

## 4. Perguntas de interpretação do próprio case — respostas prontas

O slide de Fase 3 lista 6 perguntas explícitas. Aqui estão as respostas, com números:

1. **Quais regiões do voltamograma mais contribuíram?** Potenciais entre ~0,155V e 0,215V
   (próximos ao pico redox) tiveram os maiores coeficientes absolutos na regressão logística.
2. **A corrente de pico foi suficiente?** Aparentemente sim, ou quase — no teste rápido,
   pico sozinho teve desempenho comparável (até levemente melhor) que a curva completa.
   Resposta honesta: "não posso afirmar que o pico é suficiente nem que não é, com um único
   split — isso pede validação cruzada dedicada a essa pergunta."
3. **O uso do voltamograma completo melhorou o desempenho?** Não neste teste específico — e
   isso é uma descoberta legítima, não um erro. Vale mencionar como próximo passo de rigor.
4. **Existem indícios de efeito de lote, batelada ou replicata?** Sim, de lote (ANOVA
   p<0,0001). De batelada, mais fraco. Isso é risco real de o modelo aprender "lote" em vez
   de "contaminação" — mitigação possível: normalizar por lote, ou também agrupar CV por lote.
5. **Quais limitações foram identificadas?** Desbalanceamento de classes, sinal fraco por
   medição isolada, modelo não combina os 3 estágios de uma amostra numa predição só,
   Random Forest com reprodutibilidade parcial entre ambientes (seção 5).
6. **Como o pipeline poderia ser aplicado a novos dados?** Solta os arquivos (mesmo schema)
   na pasta de entrada e roda os 2 scripts de novo — classificação automática cobre isso.

---

## 5. Bugs que você encontrou e corrigiu (bom material pra mostrar rigor)

Vale mencionar 1–2 desses proativamente — mostra que você testou de verdade, não só rodou uma vez:

1. **`pivot_table` com `NaN` no índice explodindo em memória** (tentativa de alocar ~6GB):
   ao montar a tabela wide sem metadata ainda disponível, o pandas tentava um produto
   cartesiano das combinações de índice. Resolvido trocando `NaN` por um valor-sentinela
   antes do pivot.
2. **`GroupKFold` quebrando com poucas amostras**: quando uma dobra fica com só uma classe de
   `contamination_status`, `cross_validate` lançava exceção. Agora captura e reporta `NaN`
   pra aquele modelo em vez de derrubar o pipeline inteiro.
3. **Random Forest com reprodutibilidade parcial entre ambientes**: mesmo com
   `random_state` fixo, o RF variou um pouco entre uma reexecução minha e a sua (regressão
   logística e LDA bateram exatamente). É uma característica conhecida do RF entre versões
   de scikit-learn/hardware — vale citar como limitação de reprodutibilidade se perguntarem.
4. **O pipeline original (`biosensor_pipeline.py`, pré-existente) tentava inferir bactéria/
   amostra/replicata do *nome do arquivo*** — não funcionava com os dados reais (schema
   diferente, um único arquivo consolidado). Foi por isso que vocês receberam os dois scripts
   novos em vez de um patch no antigo.

---

## 6. Perguntas prováveis da banca (além das do slide)

| Pergunta | Resposta curta |
|---|---|
| Por que `GroupKFold`/`GroupShuffleSplit` em vez de split comum? | Réplicas e estágios da mesma amostra não podem vazar entre treino e teste — senão a métrica fica otimista de forma artificial. |
| Por que `balanced_accuracy` como métrica principal, não acurácia? | Base desbalanceada (150/50) — um modelo que sempre chuta "contaminada" acerta 75% sem aprender nada. Balanced accuracy neutraliza isso. |
| Por que só `PASS`, não incluir `REVIEW`? | Escolha conservadora — mais fácil de defender "só usamos leituras sem ressalva de qualidade" do que justificar incluir dado sinalizado pra revisão. |
| Por que essas 3 features derivadas (peak/min/delta)? | Descritores simples e interpretáveis, complementam a curva completa sem adicionar muita complexidade. |
| O que você mudaria com mais tempo? | Já implementamos o item mais importante (diferença entre estágios — ver seção 2.1). Próximos: validação externa (novo lote/operador), CV agrupada por lote além de amostra, SMOTE como alternativa ao `class_weight`. |
| Por que a performance não foi mais alta? | Sinal eletroquímico é inerentemente fraco pra essa tarefa nesse recorte (ROC-AUC ~0,55–0,58) — isso é um resultado, não uma falha de código. A hipótese mais promissora é usar a *diferença* entre estágios do mesmo sensor, não cada estágio isolado. |

---

## 7. Se pedirem pra modificar o código ao vivo

Três modificações fáceis e seguras de fazer na hora, sem quebrar nada:

1. **Trocar a política de qualidade**: `python src/ingest_pipeline.py --keep-flags PASS REVIEW`
   (ou editar o default em `build_parser()`).
2. **Adicionar um modelo novo** (ex.: SVM): dentro de `train_and_evaluate`, no dicionário
   `models = {...}`, adicionar `"svm": Pipeline([("scaler", StandardScaler()), ("clf", SVC(probability=True, class_weight="balanced"))])` — já reaproveita todo o resto da função (CV, métricas, export).
3. **Mudar a semente aleatória**: `--random-state 7` — bom pra mostrar que os resultados
   variam um pouco (não são um fluke de uma seed específica), reforça a discussão de
   reprodutibilidade da seção 5.

---

## 8. Checklist final antes de enviar

- [ ] Notebook, scripts, banco, README, requirements.txt, declaração de IA — todos com os
      **mesmos números** (`qc_flag = PASS`, 1.695 medições). Já conferido.
- [ ] Você consegue abrir `ingest_pipeline.py` e apontar, sem procurar, onde fica o split
      por grupo e onde fica o cálculo de cada métrica.
- [ ] Você sabe explicar, em uma frase, por que `data_preparation.py` e `ingest_pipeline.py`
      são scripts separados (responsabilidades diferentes: um valida/junta, outro modela).
- [ ] Praticar dizer os números da seção 2 sem olhar o notebook.
