# Banco de dados (SQLAlchemy ORM + migrations Alembic)

O **modelo ORM em `fiep/orm/` é a fonte da verdade**. As tabelas ficam separadas por domínio:

| Arquivo | Tabelas |
|---|---|
| `fiep/orm/auth.py` | `usuarios` |
| `fiep/orm/cadastro.py` | `empresas`, `coletas` (cada envio de dados), `arquivos` (originais, por SHA-256) |
| `fiep/orm/dados.py` | `amostras`, `plaqueamentos`, `medicoes`, `curvas` (pontos como vetores), `qc` |
| `fiep/orm/ml.py` | `modelos`, `predicoes` |

Views (criadas nas migrations): `v_medicoes`, `v_replicatas`, `v_qc_atual`, `v_predicoes`.

Padrão: SQLite em `dados/fiep.db`. Para Postgres: `pip install -e ".[postgres]"` e
`FIEP_DB_URL=postgresql+psycopg://usuario:senha@host/fiep`.

## Migrations

| Revisão | O que faz |
|---|---|
| `0001_esquema_inicial` | todas as tabelas |
| `0002_views` | views de consulta |
| `0003_dados_exemplo` | carrega `dados/exemplo_case` como a empresa "Exemplo (case sintético)" |

```bash
fiep db migrar                       # cria/atualiza o banco (com os dados de exemplo)
fiep db migrar --sem-exemplo         # sem os dados de exemplo
fiep db exemplo --remover            # tira os dados de exemplo (quando chegarem os reais)
fiep db exemplo                      # coloca de volta
```

### Mudando o banco

1. Edite os modelos em `fiep/orm/` (nova coluna, nova tabela, novo arquivo de domínio — importe-o em
   `fiep/orm/__init__.py`).
2. Gere a migration: `alembic revision --autogenerate -m "o que mudou"` (na raiz do repositório).
3. Confira o arquivo gerado em `fiep/migracoes/versions/` (o autogenerate não detecta tudo, ex.:
   renomear coluna vira apagar + criar) e aplique: `alembic upgrade head` ou `fiep db migrar`.
4. Para voltar: `alembic downgrade -1`.

O teste `test_migrations_sobem_descem_e_batem_com_o_orm` falha se o ORM e as migrations divergirem.
No SQLite, as migrations usam *batch mode* (o Alembic recria a tabela para `ALTER TABLE`).

Migrations de **dados** (como a 0003) declaram as tabelas que usam com `sa.table(...)` em vez de
importar os modelos: o ORM vai mudar e a migration precisa continuar funcionando como foi escrita.

## Comandos

```bash
fiep db importar --entrada dados [--empresa "Laticínio A"]   # lê .nox/tabelas, grava e roda o QC
fiep db resumo
fiep db sql "SELECT * FROM v_replicatas WHERE n_aprovadas < 3"
fiep db exportar --saida dados/fiep_banco.xlsx                # uma aba por tabela (+ pontos)
fiep experimento --db dados/fiep.db                           # treina com o banco
fiep usuario criar --email ... --papel admin                  # contas da plataforma
```

Reimportar não duplica: medições e amostras são atualizadas; arquivos repetidos (mesmo SHA-256) são
ignorados.

## Em Python

```python
from fiep import db
s = db.conectar()                                  # sessão SQLAlchemy (aplica migrations pendentes)
ds = db.carregar(s, "tecnica = ?", ("DPV",))       # Dataset pronto para treinar/prever
db.sql(s, "SELECT * FROM v_replicatas")            # DataFrame

from fiep.orm import Amostra
s.query(Amostra).filter(Amostra.contamination_status.is_(None)).count()
```
