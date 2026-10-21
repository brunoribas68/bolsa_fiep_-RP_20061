# Plataforma FIEP (frontend React + API FastAPI) em uma imagem.
#   docker build -f api/Dockerfile -t fiep .
#   docker run -p 8000:8000 -e FIEP_SECRET="$(openssl rand -base64 48)" \
#     -e FIEP_ADMIN_EMAIL=voce@exemplo.org -e FIEP_ADMIN_SENHA='troque-esta-senha' \
#     -v "$PWD/dados:/app/dados" -v "$PWD/modelos:/app/modelos" fiep
# Em produção, atrás de HTTPS: -e FIEP_COOKIE_SEGURO=1 e, de preferência, Postgres em FIEP_DB_URL.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY fiep ./fiep
COPY configs ./configs
COPY api ./api
COPY dados/exemplo_case ./dados/exemplo_case
COPY --from=web /web/dist ./web/dist
RUN pip install --no-cache-dir ".[api]" && useradd -m fiep && mkdir -p dados modelos && chown -R fiep dados modelos
USER fiep
ENV FIEP_MODELOS=/app/modelos
EXPOSE 8000
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
