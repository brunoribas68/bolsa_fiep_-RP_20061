# Declaração de uso de ferramentas de IA

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
- Apoio na documentação técnica (README, comentários de código, este arquivo).

Toda a validação da lógica, as decisões de modelagem (definição da variável-alvo,
estratégia de validação, escolha de features) e a interpretação final dos resultados
foram revisadas e são de responsabilidade do autor da entrega.
