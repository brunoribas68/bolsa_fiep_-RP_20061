# Dicionário de dados — base do genossensor (RNA)

Cada eletrodo impresso (SPCE) recebe um **elemento de captura** (oligonucleotídeo, ex.: `Oligo 4N`) e é
medido em DPV:

- **branco**: o eletrodo só com o elemento de captura → **não contaminado**;
- **RNA**: depois de receber o RNA da bactéria, em uma concentração → **contaminado**.

O sensor é *signal-off*: com o RNA, o pico **cai** em relação ao branco do mesmo eletrodo.

Tabela `ensaios`: uma linha por arquivo `.nox` (um voltamograma). Ligadas a ela: `empresas`, `coletas`
(cada envio) e `usuarios`. O modelo usa a **curva de cada linha sozinha** (ver
[PIPELINE.md](PIPELINE.md)); a ligação ao branco serve para a queda do pico e a calibração.

## Campos

### Identificação

| Campo | Tipo | Obrigatório | Descrição | De onde vem |
|---|---|---|---|---|
| `id` | inteiro | sim | número da linha | automático |
| `empresa_id` | inteiro | não | empresa ou laboratório (tabela `empresas`) | `--empresa` ou a tela Nova coleta |
| `coleta_id` | inteiro | não | envio que trouxe a linha (tabela `coletas`) | automático |
| `eletrodo_id` | texto | **sim** | ID do eletrodo, ex.: `E1` — o mesmo no branco e no RNA do eletrodo | nome do arquivo (`…-E1.nox`), `--eletrodo` ou `ensaios.csv` |
| `canal` | texto | não | instrumento/canal do potenciostato, ex.: `MAC80196#2` | `.nox` |

### O que está no eletrodo

| Campo | Tipo | Obrigatório | Descrição | De onde vem |
|---|---|---|---|---|
| `tipo` | texto | **sim** | `branco` (não contaminado) ou `rna` (contaminado) | nome do arquivo; se fora do padrão, procedimento do NOVA (`Branco` ou `RNA <conc> ng-mL`) |
| `concentracao` | número | **sim** | concentração do RNA em ng/mL; **0** no branco (o banco recusa outro valor) | nome do arquivo (`dpv-RNA-0,1-E1`); se sem vírgula ou ausente, o procedimento (`0,5 ng-mL`, `500 pg/mL`…; pg, fg e µg são convertidos) |
| `elemento_captura` | texto | não | sonda imobilizada (o "tipo do branco"), ex.: `Oligo 4N` | procedimento, `--elemento` ou `ensaios.csv` |
| `bacteria` | texto | não | bactéria de origem do RNA, ex.: `E. coli` | `--bacteria`, a tela Nova coleta ou `ensaios.csv` |
| `branco_id` | inteiro | não | o branco de referência deste RNA (`ensaios.id`) | automático: branco do mesmo eletrodo, elemento de captura e empresa, o mais recente antes da medição |

### Medição

| Campo | Tipo | Descrição | De onde vem |
|---|---|---|---|
| `tecnica` | texto | `DPV` (aceita SWV) | nome do arquivo / curva |
| `tipo_eletrodo` | texto | ex.: `SPCE` | procedimento |
| `tratamento` | texto | ex.: `H2SO4` | procedimento |
| `procedimento` | texto | nome original do procedimento no NOVA | `.nox` |
| `medido_em` | data e hora | início do procedimento | `.nox` |

### Pico voltamétrico (medido na importação)

| Campo | Unidade | Descrição |
|---|---|---|
| `e_pico_v` | V | potencial do pico |
| `i_pico_ua` | µA | corrente no pico |
| `i_base_ua` | µA | corrente da linha de base sob o pico |
| `altura_ua` | µA | altura do pico acima da base (proeminência) |
| `largura_v` | V | largura a meia altura |
| `area_uav` | µA·V | área sob a curva inteira |
| `potential_v`, `current_ua` | V, µA | **a curva completa** — é o que o modelo usa |

O pico é o máximo local de maior proeminência nos 90 % centrais da faixa de potencial
(`fiep/pico.py`).

### Controle

| Campo | Descrição |
|---|---|
| `qc_flag` | `PASS` / `FAIL` (vazio = aprovado); `FAIL` fica fora do treino. Muda na tela Ensaios ou no `ensaios.csv` |
| `arquivo`, `sha256` | nome do arquivo e impressão digital (importar de novo não duplica) |
| `observacoes` | texto livre; a importação anota aqui quando o nome e o procedimento discordam |
| `criado_em` | quando entrou no banco |

## Colunas calculadas (não ficam gravadas; `fiep rna tabela`, tela Ensaios)

| Coluna | Fórmula |
|---|---|
| `altura_branco_ua` | `altura_ua` do branco ligado (`branco_id`) |
| `queda_pct` | `100 × (altura_branco − altura) / altura_branco` — queda do pico em relação ao branco |
| `abaixo_do_branco` | RNA com `altura_ua < altura_branco_ua` (regra do sensor); `False` gera aviso |

## Padrão de nome dos arquivos

Regra da equipe: **técnica - etapa - concentração (ng/mL) - eletrodo**, um `.nox` por medição.

| Arquivo | Entra como |
|---|---|
| `dpv-branco-Ej.nox` | branco (não contaminado) |
| `dpv-RNA-i-Ej.nox`, com `i` sempre com vírgula: `dpv-RNA-0,1-Ej`, `dpv-RNA-1,0-Ej`, `dpv-RNA-10,0-Ej`, `dpv-RNA-100,0-Ej` | RNA (contaminado) na concentração `i` |
| `dpv-bare-Ej.nox`, `dpv-tratado-Ej.nox` | **não entram** (a base tem só branco e RNA) |

`j` = número do eletrodo. Dúvidas sobre o padrão: Adriano Silva.

- O nome manda no tipo, na concentração e no eletrodo; o procedimento do NOVA completa o elemento de
  captura (ex.: `DPV SPCE H2SO4 Oligo 4N Branco`). Se discordarem, vale o nome e a importação avisa.
- Nomes antigos sem vírgula (`dpv-rna-15-E1` = 1,5 ng/mL) continuam aceitos: a concentração vem do
  procedimento.

### Pastas

`fiep rna pastas --entrada dados/rna` cria:

```
dados/rna/
  contaminado/       só dpv-RNA-<conc>-Ej.nox
  nao_contaminado/   só dpv-branco-Ej.nox
```

A pasta é uma conferência: o tipo vem do nome do arquivo, e um arquivo cuja pasta discorda (branco em
`contaminado/`, RNA em `nao_contaminado/`) não é gravado; a importação avisa qual é. Arquivos fora
dessas duas pastas são aceitos sem conferência.

### Correções: `ensaios.csv`

Quando o nome ou o procedimento não traz algum campo, ou traz errado, coloque na pasta um `ensaios.csv`
com a coluna `arquivo` e só as colunas a corrigir (separador `;` ou `,`):

```
arquivo;eletrodo_id;bacteria;concentracao;qc_flag
dpv-rna-550-E1.nox;E1;E. coli;55;PASS
dpv-rna-15-E1.nox;E3;E. coli;;FAIL
```

## Para o treino render

- Branco **e** RNA em cada eletrodo, com o mesmo `Ej`.
- Repetições de cada concentração em **eletrodos diferentes** — o treino separa por eletrodo; com 8 ou
  mais eletrodos sobra um teste independente.
- Pelo menos 3 brancos (o limite de detecção usa o desvio dos brancos).

## Comandos

```bash
fiep rna pastas --entrada dados/rna
fiep rna importar --entrada dados/rna [--empresa "SENAI"] [--elemento "Oligo 4N"] [--bacteria "E. coli"]
fiep rna tabela [--saida dados/base.xlsx]
fiep rna treinar
fiep rna prever --entrada nova.nox
```
