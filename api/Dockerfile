# Imagem da API/página FIEP.
#   docker build -f api/Dockerfile -t fiep-api .
#   docker run -p 8000:8000 -v "$PWD/modelos:/app/modelos" -v "$PWD/dados:/app/dados" \
#              -e FIEP_DB=/app/dados/fiep.db fiep-api
# O modelo NÃO vai dentro da imagem: monte a pasta modelos/ (gerada por `fiep experimento`).
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY fiep ./fiep
COPY configs ./configs
COPY api ./api
RUN pip install --no-cache-dir ".[api]"
ENV FIEP_MODELOS=/app/modelos
EXPOSE 8000
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
