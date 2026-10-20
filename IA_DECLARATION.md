# Declaração de uso de ferramentas de IA

## Projeto FIEP (pipeline, banco de dados, API e artigo)

Foi utilizada uma ferramenta de IA (Claude, da Anthropic) como apoio no desenvolvimento do código
deste repositório: leitor dos arquivos `.nox` do NOVA, pipeline de ingestão e controle de
qualidade, banco de dados SQLite, módulo de experimentos (incluindo a implementação simplificada do
SISSO), API e página web, notebook, testes, documentação e a estrutura e primeira redação do
artigo. As escolhas de método (alvo, protocolo de validação, critérios de qualidade), a revisão do
código e dos resultados e o texto final do artigo são de responsabilidade do autor.

## Entrega original do case (histórico)


Foi utilizada uma ferramenta de IA (Claude, da Anthropic) como apoio ao longo do
desenvolvimento desta entrega, nas seguintes atividades:

- Diagnóstico de um erro de execução no pipeline original (schema de colunas
  incompatível com os arquivos reais fornecidos).
- Estruturação inicial dos dois scripts do pipeline (`data_preparation.py` e
  `ingest_pipeline.py`), incluindo a lógica de classificação de arquivos por schema,
  junção das três tabelas por `measurement_id`/`sample_id`, montagem da tabela wide
  e validação/CV agrupada por amostra.
- Apoio na escrita do notebook (`case_biossensor.ipynb`), organizando o conteúdo nas
  três fases pedidas pelo case.
- Revisão de consistência metodológica (ex.: identificação de que o target correto
  para a classificação é `contamination_status`, e não um rótulo inferido do nome do
  arquivo, como no pipeline original) e de bugs de robustez encontrados durante os
  testes (falha de validação cruzada com poucas amostras; estouro de memória no
  `pivot_table` ao lidar com valores ausentes).
- Apoio no desenvolvimento e teste de uma segunda abordagem de features (diferença de
  sinal entre estágios do sensor, descritores de curva mais ricos, modelos adicionais
  SVM/Gradient Boosting), incluindo checagem de vazamento de dados antes de aceitar o
  resultado (verificação de que o ganho de desempenho não vinha de um confundidor como
  lote do sensor).
- Apoio na montagem da apresentação de slides (estrutura, gráficos, conteúdo).
- Apoio na documentação técnica (README, comentários de código, este arquivo, e o guia
  de preparação para a defesa).

Toda a validação da lógica, as decisões de modelagem (definição da variável-alvo,
estratégia de validação, escolha de features) e a interpretação final dos resultados
foram revisadas e são de responsabilidade do autor da entrega.
