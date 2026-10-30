# Plataforma web (login, coletas, banco de amostras)

Frontend em React com Material UI (`web/`; tema em `web/src/tema.ts`) e backend em FastAPI (`api/`), sobre o mesmo banco e o mesmo modelo da
pipeline. É por aqui que os colaboradores enviam as coletas feitas nas empresas.

## Primeira vez

```bash
pip install -e ".[api]"
cd web && npm install && npm run build && cd ..        # compila o frontend (web/dist)

fiep usuario criar --email voce@exemplo.org --nome "Seu Nome" --papel admin   # pede a senha
fiep servir                                            # http://127.0.0.1:8000
```

O banco é criado na primeira execução com as migrations, já com o **case de exemplo** (empresa
"Exemplo (case sintético)", 200 amostras) para testar. Quando chegarem os dados reais:
`fiep db exemplo --remover`.

Desenvolvimento do frontend com recarga automática: `fiep servir` num terminal e
`cd web && npm run dev` noutro (abre em http://localhost:5173, com proxy para a API).

## Perfis

| Perfil | Pode |
|---|---|
| Administrador | tudo, inclusive criar/desativar contas, redefinir senhas e apagar coletas |
| Colaborador | enviar coletas, cadastrar empresas, editar rótulos e metadados, prever |
| Leitor | consultar e prever |

Não há cadastro aberto: o admin cria as contas (página **Usuários** ou `fiep usuario criar`).

## Telas

- **Painel**: amostras por resultado e por empresa, réplicas completas, modelo em uso (com a acurácia
  no teste), coletas recentes.
- **Gráficos**: gráficos dos dados do banco, com filtro por empresa, protocolo (rRNA 16S, NS1…) e
  QC (só aprovadas ou todas):
  - *Linha (voltamogramas)*: "por resultado" mostra a média ± 1 desvio padrão das contaminadas,
    não contaminadas e sem resultado numa etapa ou na diferença última − anterior (o sinal que o
    modelo usa); "por etapa" sobrepõe as etapas do sensor. Pode mostrar as curvas individuais
    (até 120 eletrodos). As curvas passam pelo mesmo QC e pré-processamento do modelo.
  - *Dispersão*: um ponto por eletrodo; eixos X e Y escolhidos entre os descritores de cada etapa
    (corrente e potencial do pico, amplitude, área, largura a meia altura, corrente mínima), as
    diferenças entre etapas e a carga (log10 UFC/mL). Cor (e forma) por resultado ou empresa,
    linha de tendência com r de Pearson, legenda clicável para ocultar grupos, clique no ponto
    abre a amostra.
  - Botões para baixar cada gráfico em PNG (com título e legenda, para relatório/artigo) e a
    tabela de descritores em CSV (abre no Excel).
- **Modelos**: métricas do modelo em uso no conjunto de teste (acurácia, acurácia balanceada,
  sensibilidade, especificidade, AUC e acurácia balanceada por amostra) e as abas:
  - *Comparação de algoritmos*: o melhor resultado de cada algoritmo e a tabela de todas as
    combinações representação × algoritmo (CV, validação e teste; a escolhida tem estrela);
  - *Gráficos*: figuras do experimento (ROC, matriz de confusão, comparação, fórmula SISSO);
  - *Carga*: regressores da carga (log10 UFC/mL);
  - *Histórico*: todos os modelos treinados; o admin escolhe qual a plataforma usa;
  - *Treinos*: andamento e resultado dos treinos iniciados pela plataforma.

  **Treinar modelos** (colaborador ou admin) abre a escolha dos algoritmos de IA (agrupados por
  família: lineares, SVM, vizinhos, árvores, rede neural, probabilísticos, SISSO), das
  representações, das empresas, da divisão treino/validação/teste e se inclui os dados de
  exemplo. O treino roda em segundo plano, um por vez. O modelo novo só entra em uso se o admin
  marcar "usar o melhor modelo" ou clicar **Usar este modelo**.
- **Nova coleta**: empresa, data, uso no treino (sorteio 50/25/25, ou fixo em treino/validação/teste) e as
  amostras. Arraste a pasta do lote (uma subpasta por amostra) ou adicione amostra por amostra. Para cada
  uma: código, resultado do plaqueamento e carga. Aceita `.nox` e Excel/CSV exportado do NOVA.
  Ao enviar, os arquivos são guardados (`dados/recebidos/`), lidos, passam pelo controle de qualidade e
  vão para o banco; estágio do sensor e réplica são deduzidos dos arquivos.
- **Amostras**: busca e filtros; o resultado do plaqueamento e a carga são editáveis direto na tabela.
- **Amostra**: voltamogramas por réplica (os três estágios sobrepostos), medições com o QC e o estágio
  editável, plaqueamento, histórico e o botão **Prever com o modelo**.
- **Previsão**: classifica arquivos sem gravar nada (e converte `.nox` para Excel). Mostra a base de
  cada previsão (todas as etapas ou só uma etapa, com a acurácia do modelo daquela etapa; abaixo de
  0,7 o resultado é "Inconclusivo") e a tabela de **picos** de cada arquivo — DPV/SWV e CV, inclusive
  arquivos que o modelo não usa — com média ± desvio por técnica e download em CSV.

## Segurança

- Senhas com bcrypt (custo 12), mínimo de 10 caracteres; a senha nunca volta do servidor.
- Sessão em cookie `httpOnly`, `SameSite=Strict` (e `Secure` com `FIEP_COOKIE_SEGURO=1`), assinada
  com `FIEP_SECRET`, validade de 8 h. Trocar a senha, mudar o perfil ou desativar a conta derruba as
  sessões abertas.
- Toda alteração exige o cabeçalho `X-Requested-With: fiep` (proteção contra CSRF).
- 5 tentativas de login erradas em 15 min (por e-mail ou IP) bloqueiam novas tentativas.
- Cabeçalhos de segurança (CSP, `X-Frame-Options`, `nosniff`); uploads limitados por tipo, tamanho
  (50 MB) e caminho (sem `..`).

Em produção: rode atrás de HTTPS, defina `FIEP_SECRET` (`openssl rand -base64 48`),
`FIEP_COOKIE_SEGURO=1` e, de preferência, Postgres em `FIEP_DB_URL`. Todas as variáveis estão em
`api/config.py`. Imagem Docker: `api/Dockerfile`.

## API

Documentação interativa em `/docs`. Principais rotas: `/api/auth/*`, `/api/usuarios`, `/api/empresas`,
`/api/coletas`, `/api/amostras`, `/api/medicoes/{id}`, `/api/prever`, `/api/excel`, `/api/painel`,
`/api/graficos?empresa_id=&protocolo=&qc=aprovadas|todas` (curvas médias, curvas individuais e
descritores por eletrodo), `/api/catalogo` (algoritmos e representações), `/api/modelos` (lista com métricas),
`/api/modelos/{id}` (cartão + comparação + regressão + por amostra), `/api/modelos/{id}/figuras/{nome}`,
`POST /api/modelos/{id}/ativar` (admin), `GET/POST /api/treinos` e `/api/treinos/{id}`.
