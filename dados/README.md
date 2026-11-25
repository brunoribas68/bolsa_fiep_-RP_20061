# Pasta de dados

```
dados/
  rna/
    contaminado/       <- dpv-RNA-<conc>-Ej.nox (com o RNA da bactéria; conc em ng/mL, sempre com decimal: 0,1 / 10,0)
    nao_contaminado/   <- dpv-branco-Ej.nox (eletrodo só com o elemento de captura)
    ensaios.csv        <- opcional: correções (coluna arquivo + as colunas a trocar)
  recebidos/           <- .nox enviados pela plataforma (uma pasta por coleta)
  backup/              <- cópias feitas pelo fiep db zerar
  fiep.db              <- banco SQLite
```

**Nada disso vai para o Git** (o repositório é público), só este arquivo.

`fiep rna pastas --entrada dados/rna` cria `contaminado/` e `nao_contaminado/`.
`fiep rna importar --entrada dados/rna` grava os `.nox` no banco: um arquivo na pasta errada (um branco
em `contaminado/`, um RNA em `nao_contaminado/`), de outra etapa (`bare`, `tratado`...) ou sem o
eletrodo no nome não entra, e a importação diz qual foi e por quê. Importar de novo não duplica.

O `Ej` é o eletrodo: o branco e o RNA do mesmo eletrodo levam o mesmo `Ej`. O treino nunca separa as
medições de um eletrodo entre treino e teste.

Campos, regras e o padrão de nome: [`../docs/DICIONARIO_DADOS.md`](../docs/DICIONARIO_DADOS.md).
