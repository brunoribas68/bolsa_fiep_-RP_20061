# Como o fluxo funciona

```
.nox (dpv-branco-Ej, dpv-RNA-<conc>-Ej) ─► leitura (fiep/io/nox.py) ─► pico (fiep/pico.py) ─► tabela `ensaios`
   │  nome do arquivo: tipo, concentração, eletrodo                       │  cada RNA ligado ao branco do eletrodo
   │  procedimento do NOVA: elemento de captura                           ▼
   │  pasta contaminado/ | nao_contaminado/: conferência         modelagem (fiep/modelagem.py)
   │                                                              4 representações × 15 algoritmos
   │                                                              validação por eletrodo; teste guardado
   ▼                                                                      │
novo .nox ─► mesma leitura ─► confere a faixa de potencial ─► previsão ◄── modelos/<id>/ (em uso: modelos/ATUAL)
```

## 1. Base (`fiep/genossensor.py`)

- **Leitura**: a primeira curva DPV/SWV do `.nox` (último scan, se houver vários), em V e µA.
- **Campos**: do nome do arquivo saem o tipo (`branco` ou `rna`), a concentração em ng/mL e o eletrodo
  (`Ej`); do procedimento do NOVA, o elemento de captura, a técnica, o eletrodo impresso e o tratamento.
  Se discordarem, vale o nome. Nome antigo sem vírgula (`rna-15` = 1,5): vale o procedimento.
- **O que não entra** (com aviso): outras etapas (`bare`, `tratado`...), RNA sem concentração, sem o
  eletrodo no nome, curva com menos de 20 pontos, arquivo na pasta errada, o mesmo arquivo de novo.
- **Ligação ao branco**: cada RNA é ligado ao branco do mesmo eletrodo, elemento de captura e empresa
  (o mais recente antes da medição). Serve para a queda do pico e a calibração, **não** para o modelo.
- **Calibração**: reta da queda do pico (%) contra log₁₀(concentração) nos RNA ligados a um branco;
  limite de detecção = 3 × desvio relativo dos brancos ÷ inclinação (com 3 ou mais brancos).

## 2. Pico (`fiep/pico.py`)

O máximo local de maior proeminência nos 90 % centrais da faixa de potencial (nas pontas a corrente sobe
ou desce pela dupla camada e o máximo absoluto costuma cair ali). Medidas: potencial e corrente do pico,
corrente da base (pico − proeminência), altura (a proeminência), largura a meia altura e área.

## 3. Modelo (`fiep/modelagem.py`)

1. **Dados**: ensaios com qc_flag diferente de FAIL. Rótulo: RNA = 1 (contaminado), branco = 0. Grupo: o
   eletrodo. Mínimo: 3 de cada.
2. **Teste**: com 8 ou mais eletrodos, um quarto deles (StratifiedGroupKFold, 4 partes) fica guardado,
   desde que o teste tenha as duas classes e o treino continue com 3 de cada. Sem isso, não há teste e o
   cartão do modelo avisa.
3. **Grade comum**: 100 potenciais na faixa coberta por todas as curvas do treino.
4. **Representações**: `curva` (a corrente na grade), `forma` (cada curva reescalada entre 0 e 1),
   `derivada` (Savitzky-Golay, janela 11, ordem 3) e `pico` (as 6 medidas do pico).
5. **Comparação**: cada representação × cada algoritmo do catálogo (`fiep/catalogo.py`), por validação
   cruzada agrupada por eletrodo (até 5 partes; com menos de 3 eletrodos, por medição, com aviso de que
   é otimista). SISSO só com `pico`. Métrica: acurácia balanceada no limiar 0,5; desempate pela AUC e
   depois pela ordem (representação mais simples, algoritmo mais simples).
6. **Vencedor**: retreinado em todo o treino e medido uma vez no teste.
7. **Registro**: `modelos/<id>/modelo.joblib` (estimador, representação, grade e cartão) e
   `cartao.json`; linha na tabela `modelos`; `modelos/ATUAL` aponta o modelo em uso.

O cartão guarda: algoritmo e representação (com nomes legíveis), grade, dados (curvas, brancos, RNA,
eletrodos, quais ficaram no teste, concentrações), métricas da validação cruzada e do teste, a de
referência (teste se houver), se é confiável (≥ 0,7), avisos e o placar de todas as combinações.

## 4. Previsão

`prever_arquivos(pacote, arquivos)`: lê cada `.nox`, mede o pico, confere se a curva cobre a faixa da
grade do modelo (tolerância de 0,02 V) e aplica a mesma representação.

| Resultado | Quando |
|---|---|
| CONTAMINADO / NÃO CONTAMINADO | probabilidade ≥ 0,5 / < 0,5 |
| REPETIR MEDIÇÃO | curva curta ou faixa de potencial diferente da do treino |
| INCONCLUSIVO | o modelo tem acurácia balanceada de referência < 0,7 (a probabilidade aparece, mas não vira decisão) |

## Comandos

```bash
fiep rna importar --entrada dados/rna
fiep rna treinar [-v]                 # -v mostra o andamento
fiep rna prever --entrada nova.nox
```

Em Python:

```python
from fiep import db, genossensor as g, modelagem as m
s = db.conectar()
g.importar(s, "dados/rna")
pacote = m.treinar(g.tabela(s, incluir_curvas=True))
m.salvar(pacote, "modelos", s=s)
m.prever_arquivos(m.carregar("modelos"), ["nova.nox"])
```
