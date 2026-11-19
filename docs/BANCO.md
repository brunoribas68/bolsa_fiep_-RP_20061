# Banco de dados (SQLAlchemy ORM + migrations Alembic)

O **modelo ORM em `fiep/orm/` é a fonte da verdade**. Uma tabela por assunto:

| Arquivo | Tabelas |
|---|---|
| `fiep/orm/auth.py` | `usuarios` |
| `fiep/orm/cadastro.py` | `empresas`, `coletas` (cada envio de `.nox`) |
| `fiep/orm/genossensor.py` | `ensaios`: um voltamograma por linha (branco ou RNA), com o pico e a curva — [dicionário](DICIONARIO_DADOS.md) |
| `fiep/orm/ml.py` | `modelos` (cartão de cada modelo treinado), `predicoes` |

Padrão: SQLite em `dados/fiep.db`. Para Postgres: `pip install -e ".[postgres]"` e
`FIEP_DB_URL=postgresql+psycopg://usuario:senha@host/fiep`.

## Migrations

| Revisão | O que faz |
|---|---|
| `r001_esquema_do_genossensor` | todas as tabelas |

As migrations da versão anterior (0001–0005, com o case de exemplo) foram substituídas por esta. Um
banco daquela versão é recusado com a orientação de rodar `fiep db zerar`, que guarda uma cópia em
`dados/backup/`, recria o banco e mantém as contas de usuário (com as mesmas senhas).

### Mudando o banco

1. Edite os modelos em `fiep/orm/` (nova coluna, nova tabela, novo arquivo — importe-o em
   `fiep/orm/__init__.py`).
2. Gere a migration: `alembic revision --autogenerate -m "o que mudou"` (na raiz do repositório).
3. Confira o arquivo gerado em `fiep/migracoes/versions/` (o autogenerate não detecta tudo, ex.:
   renomear coluna vira apagar + criar) e aplique: `fiep db migrar`.
4. Para voltar: `alembic downgrade -1`.

O teste `test_migrations_sobem_descem_e_batem_com_o_orm` falha se o ORM e as migrations divergirem.
No SQLite, as migrations usam *batch mode* (o Alembic recria a tabela para `ALTER TABLE`).

## Consultas úteis

```bash
fiep db sql "SELECT tipo, concentracao, COUNT(*) n, COUNT(DISTINCT eletrodo_id) eletrodos FROM ensaios GROUP BY 1, 2"
fiep db sql "SELECT eletrodo_id, SUM(tipo = 'branco') brancos, SUM(tipo = 'rna') rna FROM ensaios GROUP BY 1"
fiep db sql "SELECT arquivo FROM ensaios WHERE tipo = 'rna' AND branco_id IS NULL"      # RNA sem branco
fiep db sql "SELECT id, algoritmo, representacao, balanced_accuracy, referencia FROM modelos"
fiep db sql "SELECT previsto_em, arquivo, resultado, prob_contaminado FROM predicoes ORDER BY 1 DESC LIMIT 20"
fiep rna tabela --saida dados/base.xlsx       # a base inteira, com a queda do pico, em Excel
```

## Em Python

```python
from fiep import db, genossensor as g
s = db.conectar()                           # sessão SQLAlchemy (aplica migrations pendentes)
base = g.tabela(s)                          # DataFrame com as colunas calculadas (queda_pct...)
db.sql(s, "SELECT * FROM coletas")          # consulta livre

from fiep.orm import Ensaio
s.query(Ensaio).filter(Ensaio.tipo == "branco").count()
```
