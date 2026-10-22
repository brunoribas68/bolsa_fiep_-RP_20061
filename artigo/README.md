# Artigo (LaTeX, pt-BR)

```
main.tex            documento principal
secoes/*.tex        resumo, introdução, métodos, resultados, discussão, conclusão
referencias.bib     referências (confira volume/páginas antes de submeter)
gerado/             figuras e tabelas do último `fiep experimento --artigo` (não edite à mão)
  figuras/*.png
  tabelas/numeros.tex  -> macros com os números do texto (\ABteste, \MelhorModelo, ...)
  tabelas/tabela_*.tex
```

## Atualizar os resultados

Depois de colocar os dados reais em `dados/` (ver `dados/README.md`), na raiz do repositório:

```bash
fiep experimento --artigo                 # a partir das pastas
fiep experimento --db dados/fiep.db --artigo   # ou a partir do banco (dados enviados pela plataforma)
```

Os números do texto, as tabelas e as figuras se atualizam na próxima compilação. Trechos que
dependem de informação do laboratório aparecem em **vermelho** (`\preencher{...}`): procure por
`\preencher` para encontrar todos.

## Compilar

```bash
latexmk -pdf main.tex
```

ou envie a pasta `artigo/` para o Overleaf (compilador pdfLaTeX). Requer os pacotes `babel`
(português), `natbib`, `booktabs`, `subcaption`, `mathptmx`, presentes nas distribuições TeX Live
e MiKTeX completas.

Para mudar para o modelo de uma revista, troque `\documentclass` e o estilo de bibliografia em
`main.tex`; as seções e o conteúdo gerado continuam os mesmos.
