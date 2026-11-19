# Plataforma web (login, coletas, base de ensaios, modelos)

Frontend em React com Material UI (`web/`; tema em `web/src/tema.ts`) e backend em FastAPI (`api/`),
sobre o mesmo banco e os mesmos modelos da linha de comando. É por aqui que a equipe envia os `.nox`.

## Primeira vez

```bash
pip install -e ".[api]"
cd web && npm install && npm run build && cd ..        # compila a tela (web/dist)

fiep usuario criar --email voce@exemplo.org --nome "Seu Nome" --papel admin   # pede a senha
fiep servir                                            # http://127.0.0.1:8000
```

O banco é criado vazio na primeira execução. Desenvolvimento da tela com recarga automática:
`fiep servir` num terminal e `cd web && npm run dev` noutro (http://localhost:5173, com proxy para a API).

## Perfis

| Perfil | Pode |
|---|---|
| Administrador | tudo, inclusive criar/desativar contas, redefinir senhas e apagar coletas |
| Colaborador | enviar coletas, cadastrar empresas, editar ensaios, treinar modelos, prever |
| Leitor | consultar e prever |

Não há cadastro aberto: o admin cria as contas (página **Usuários** ou `fiep usuario criar`).

## Telas

- **Painel**: quantos brancos, RNA e eletrodos há na base, o modelo em uso (ou quantos ensaios faltam
  para treinar), coletas recentes e ensaios por concentração.
- **Coletas**: cada envio, com quem enviou, quantos brancos e RNA e os avisos. A coleta abre com os
  ensaios dela e os avisos (arquivos que não entraram, RNA acima do branco, RNA sem branco do eletrodo).
- **Nova coleta**: empresa, descrição, data, elemento de captura (se o procedimento do NOVA não disser)
  e bactéria; arraste os `.nox` ou a pasta com `contaminado/` e `nao_contaminado/`. **Antes de enviar**,
  a tela mostra como cada arquivo será lido (branco ou RNA, concentração, eletrodo) e avisa os que não vão
  entrar (pasta errada, outra etapa, nome fora do padrão). Os `.nox` ficam guardados em `dados/recebidos/`.
- **Ensaios**: a base inteira, com filtros por empresa, tipo e eletrodo; contagens de brancos e RNA
  aprovados e a calibração (R², % de queda por década, limite de detecção). Clique numa linha para ver a
  curva junto do branco do mesmo eletrodo, as medidas do pico e editar tipo, concentração, eletrodo,
  elemento de captura, bactéria, QC (reprovado fica fora do treino) e observações. CSV da base.
- **Gráficos**: *linha* com a média ± desvio das curvas de cada concentração (curvas individuais ao
  fundo), todas as curvas, ou as de um eletrodo; *dispersão* com qualquer par entre log₁₀ concentração,
  queda do pico, altura, corrente, potencial, base, largura e área, com reta, correlação e a curva de
  calibração. Branco em cinza; RNA numa escala de laranja (mais escuro = mais concentrado). PNG e CSV.
- **Modelos**: o modelo em uso — algoritmo e representação com nomes legíveis (passe o mouse para a
  explicação), acurácia balanceada, sensibilidade, especificidade e AUC no teste (ou na validação
  cruzada, quando não há teste, com aviso) — e as abas *Comparação de algoritmos* (melhor de cada
  algoritmo e todas as combinações), *Teste* (matriz de confusão), *Histórico* (o admin escolhe qual
  usar) e *Treinos*. **Treinar modelos** escolhe algoritmos, representações e empresas; roda em segundo
  plano, um por vez.
- **Previsão**: classifica `.nox` com o modelo em uso, sem gravar na base (opcional: registrar no
  histórico de previsões); mostra o que o nome do arquivo diz (para conferir), o resultado, a
  probabilidade, o pico e as curvas; CSV. Converte `.nox` para Excel.
- **Empresas**, **Usuários** (admin) e **Minha conta**.

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

Documentação interativa em `/docs`. Rotas: `/api/auth/*`, `/api/usuarios`, `/api/empresas`,
`/api/coletas` (lista, `POST` com os `.nox`, detalhe com os ensaios, `DELETE`), `/api/ensaios`
(lista com a calibração; `/api/ensaios/{id}` com a curva e o branco; `PATCH` e `DELETE`),
`/api/graficos?empresa_id=` (curvas e medidas do pico), `/api/painel`, `/api/catalogo` (algoritmos e
representações), `/api/modelos` e `/api/modelos/{id}` (cartões), `POST /api/modelos/{id}/ativar`
(admin), `GET/POST /api/treinos` e `/api/treinos/{id}`, `/api/modelo` (cartão do modelo em uso),
`POST /api/prever`, `POST /api/excel`, `/api/saude`.
