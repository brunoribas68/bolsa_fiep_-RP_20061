# Dicionário de dados — base do genossensor (RNA)

Base nova, feita para os ensaios do genossensor: um eletrodo impresso (SPCE) com um **elemento de
captura** (oligonucleotídeo, ex.: `Oligo 4N`) é medido em DPV **sem o alvo** (o **branco**) e depois
**com o RNA da bactéria** (o **alvo**) em várias concentrações. O sensor é *signal-off*: quando o RNA
hibridiza, o pico **cai** — o pico do alvo tem de ficar **abaixo do branco**.

Tabela: `ensaios` (uma linha por arquivo `.nox` / voltamograma). Continuam no banco e ligadas a ela:
`empresas`, `coletas` (cada importação) e `usuarios`. As tabelas da base antiga (`amostras`,
`medicoes`, `curvas`…, do case sintético) ficam no banco, mas não entram neste fluxo.

## Campos

### Identificação

| Campo | Tipo | Obrigatório | Descrição | De onde vem |
|---|---|---|---|---|
| `id` | inteiro | sim | número da linha | automático |
| `empresa_id` | inteiro | não | empresa ou laboratório (tabela `empresas`) | `--empresa` |
| `coleta_id` | inteiro | não | importação que trouxe a linha (tabela `coletas`) | automático |
| `eletrodo_id` | texto | **sim** | ID do eletrodo, ex.: `E1` | nome do arquivo (`…-E1.nox`), `--eletrodo` ou `ensaios.csv` |
| `canal` | texto | não | instrumento/canal do potenciostato, ex.: `MAC80196#2` | `.nox` |

### O que está no eletrodo

| Campo | Tipo | Obrigatório | Descrição | De onde vem |
|---|---|---|---|---|
| `elemento_captura` | texto | **sim** | sonda imobilizada (o "tipo do branco"), ex.: `Oligo 4N` | nome do procedimento, `--elemento` ou `ensaios.csv` |
| `tipo` | texto | **sim** | `branco` (só a sonda), `alvo` (com RNA) ou `negativo` (amostra sem o RNA-alvo) | nome do procedimento (`Branco`, concentração, `negativo`/`controle`) |
| `alvo` | texto | não | o que se quer detectar: `RNA` | nome do procedimento |
| `bacteria` | texto | não | bactéria de origem do RNA, ex.: `E. coli` | `--bacteria` ou `ensaios.csv` |
| `concentracao` | número | **sim** | concentração do alvo; **0** no branco e no negativo (o banco recusa outro valor) | nome do procedimento (`0,5 ng-mL`, `500 pg/mL`…) |
| `unidade` | texto | sim | sempre `ng/mL` (pg, fg e µg são convertidos) | automático |
| `branco_id` | inteiro | não | o branco de referência deste alvo/negativo (`ensaios.id`) | automático: branco do mesmo eletrodo, mesmo elemento de captura e mesma empresa, o mais recente antes da medição |

### Medição

| Campo | Tipo | Descrição | De onde vem |
|---|---|---|---|
| `tecnica` | texto | `DPV` (também aceita SWV) | nome do procedimento / curva |
| `tipo_eletrodo` | texto | ex.: `SPCE` | nome do procedimento |
| `tratamento` | texto | ex.: `H2SO4` | nome do procedimento |
| `procedimento` | texto | nome original do procedimento no NOVA | `.nox` |
| `medido_em` | data e hora | início do procedimento | `.nox` |

### Pico voltamétrico (extraído automaticamente)

| Campo | Unidade | Descrição |
|---|---|---|
| `e_pico_v` | V | potencial do pico |
| `i_pico_ua` | µA | corrente no pico |
| `i_base_ua` | µA | corrente da linha de base local sob o pico |
| `altura_ua` | µA | altura do pico acima da base (proeminência) — **o sinal principal** |
| `largura_v` | V | largura a meia altura |
| `area_uav` | µA·V | área sob a curva inteira |
| `potential_v`, `current_ua` | V, µA | a curva completa (para refazer o pico ou treinar com a curva) |

O pico é procurado nos 90 % centrais da faixa de potencial (as bordas têm transientes) e escolhido
pela proeminência, o mesmo critério do resto da pipeline (`fiep/features.py`, `achar_pico`).

### Controle

| Campo | Descrição |
|---|---|
| `qc_flag` | `PASS` / `FAIL` marcado à mão (`ensaios.csv`); `FAIL` fica fora do treino |
| `conjunto` | `treino`, `validacao` ou `teste` fixo (`--conjunto`); vazio = livre |
| `arquivo`, `sha256` | nome do arquivo e impressão digital (importar de novo não duplica) |
| `observacoes` | texto livre |
| `criado_em` | quando entrou no banco |

## Colunas calculadas (não ficam gravadas; `fiep rna tabela`)

| Coluna | Fórmula |
|---|---|
| `altura_branco_ua` | `altura_ua` do branco ligado (`branco_id`) |
| `sinal_rel_pct` | `100 × (altura_branco − altura) / altura_branco` — queda do pico em relação ao branco |
| `abaixo_do_branco` | alvo com `altura_ua < altura_branco_ua` (regra do sensor); `False` gera aviso |
| `log10_concentracao` | `log10(concentracao)` dos alvos |
| rótulo (no treino) | **contaminado** = alvo com concentração acima de `--limiar` (padrão 0); **não contaminado** = negativo e, por padrão, o branco (`--sem-branco` usa só os negativos) |

## Correções: `ensaios.csv`

Quando o nome do procedimento ou do arquivo não traz algum campo, ou traz errado, coloque na pasta
um `ensaios.csv` com a coluna `arquivo` e só as colunas a corrigir:

```
arquivo;eletrodo_id;bacteria;concentracao;qc_flag
dpv-rna-550-E1.nox;E1;E. coli;55;PASS
dpv-rna-15-E1.nox;E3;E. coli;;FAIL
```

## Como os arquivos devem chegar

- Um `.nox` por medição DPV, com o procedimento no NOVA nomeado assim:
  `DPV SPCE H2SO4 <elemento de captura> Branco` e `DPV SPCE H2SO4 <elemento de captura> RNA <conc> ng-mL`.
- O ID do eletrodo no nome do arquivo: `dpv-branco-E1.nox`, `dpv-rna-15-E1.nox`.
- Para cada eletrodo, o **branco antes do alvo**, no mesmo eletrodo (é o que dá o sinal relativo).
- Para treinar contaminado × não contaminado são precisos **controles negativos** (eletrodo com
  amostra sem o RNA-alvo, `negativo` no nome) e várias repetições de cada concentração em eletrodos
  diferentes. O branco sozinho não é uma amostra negativa: é o eletrodo antes de receber a amostra.

## Comandos

```bash
fiep rna importar --entrada dados/rna [--empresa "SENAI"] [--bacteria "E. coli"]
fiep rna tabela [--saida dados/rna_base.xlsx]
fiep rna treinar [--limiar 1] [--sem-branco] [--saida resultados/rna/treino.json]
```
