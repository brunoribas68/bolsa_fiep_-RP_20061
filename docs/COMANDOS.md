# Comandos `fiep`

Gerado por `fiep docs` a partir da ajuda dos comandos — não edite à mão. Sem instalar o pacote, use `python -m fiep` na raiz do repositório.

| Comando | Para quê |
|---|---|
| [`fiep rna`](#fiep-rna) | genossensor: pastas, importar, tabela, treinar, prever |
| [`fiep modelos`](#fiep-modelos) | modelos treinados: listar, mostrar, ativar, catalogo |
| [`fiep excel`](#fiep-excel) | converte .nox para Excel no formato do NOVA |
| [`fiep db`](#fiep-db) | banco de dados: migrar, sql, zerar |
| [`fiep servir`](#fiep-servir) | abre a plataforma web (login, coletas, gráficos, modelos, previsão) |
| [`fiep usuario`](#fiep-usuario) | contas da plataforma: criar, listar, senha, desativar |
| [`fiep verificar`](#fiep-verificar) | diagnóstico da instalação (dependências, banco, modelo, frontend) |
| [`fiep docs`](#fiep-docs) | regera docs/COMANDOS.md a partir desta ajuda |

## fiep rna

```
uso: fiep rna [-h] [--entrada ENTRADA] [--db DB] [--empresa EMPRESA] [--elemento ELEMENTO]
                [--eletrodo ELETRODO] [--bacteria BACTERIA] [--algoritmos ALG [ALG ...]]
                [--representacoes {curva,forma,derivada,base_vales,base_als,pico} [{curva,forma,derivada,base_vales,base_als,pico} ...]]
                [--seed SEED] [--rapido] [--sem-ativar] [--modelos MODELOS] [--id ID] [--salvar]
                [--saida SAIDA]
                {pastas,importar,tabela,treinar,prever}

Ações:
  pastas    cria contaminado/ (só RNA) e nao_contaminado/ (só branco) em --entrada
  importar  lê os .nox DPV de --entrada: do nome do arquivo (dpv-branco-E1, dpv-RNA-0,1-E1) tira o tipo,
            a concentração (ng/mL) e o eletrodo; do procedimento do NOVA, o elemento de captura. Mede o
            pico e liga cada RNA ao branco do mesmo eletrodo. Arquivo na pasta errada, de outra etapa
            (bare, tratado...) ou sem eletrodo não é gravado. Correções: ensaios.csv na pasta
  tabela    mostra a base (pico, queda em relação ao branco, calibração); --saida base.xlsx/.csv salva
  treinar   compara 6 representações da curva x 15 algoritmos (validação por eletrodo), mede o melhor
            no teste (se houver eletrodos suficientes) e o registra como modelo em uso
  prever    classifica os .nox de --entrada (arquivo ou pasta) com o modelo em uso
Dicionário de dados: docs/DICIONARIO_DADOS.md

argumentos:
  {pastas,importar,tabela,treinar,prever}
                                  o que fazer

opções:
  -h, --help                      mostra esta ajuda
  --entrada ENTRADA               pastas/importar: pasta dos .nox; prever: um .nox ou uma pasta
  --db DB                         arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou
                                  dados/fiep.db)
  --empresa EMPRESA               importar: empresa/laboratório dos dados
  --elemento ELEMENTO             importar: elemento de captura de quem não tiver no procedimento
  --eletrodo ELETRODO             importar: ID do eletrodo de quem não tiver E1, E2.. no nome
  --bacteria BACTERIA             importar: bactéria de origem do RNA (ex.: E. coli)
  --algoritmos ALG [ALG ...]      treinar: só estes algoritmos (padrão: os 15; lista em fiep modelos catalogo)
  --representacoes {curva,forma,derivada,base_vales,base_als,pico} [{curva,forma,derivada,base_vales,base_als,pico} ...]
                                  treinar: só estas representações da curva (padrão: todas)
  --seed SEED                     treinar: semente dos sorteios (padrão: 42)
  --rapido                        treinar: só 3 algoritmos (teste rápido)
  --sem-ativar                    treinar: registra sem trocar o modelo em uso
  --modelos MODELOS               pasta dos modelos (padrão: modelos)
  --id ID                         prever: usar este modelo em vez do que está em uso
  --salvar                        prever: grava as previsões no banco
  --saida SAIDA                   tabela: .xlsx/.csv da base; treinar: .json com o cartão do modelo
```

## fiep modelos

```
uso: fiep modelos [-h] [--id ID] [--modelos MODELOS] {listar,mostrar,ativar,catalogo}

Ações:
  listar    modelos registrados, com a acurácia balanceada de referência (* = em uso)
  mostrar   dados, validação e a comparação completa de um modelo (--id)
  ativar    passa a usar o modelo --id na plataforma e no fiep rna prever
  catalogo  representações da curva e algoritmos comparados no treino

argumentos:
  {listar,mostrar,ativar,catalogo}
                                  o que fazer

opções:
  -h, --help                      mostra esta ajuda
  --id ID                         id do modelo (ex.: 20261119-153012)
  --modelos MODELOS               pasta dos modelos (padrão: modelos)
```

## fiep excel

```
uso: fiep excel [-h] --entrada ENTRADA [--saida SAIDA] [--refazer]

converte .nox para Excel no formato do NOVA

opções:
  -h, --help         mostra esta ajuda
  --entrada ENTRADA  pasta com .nox
  --saida SAIDA      pasta de saída (padrão: dados/excel/<lote>)
  --refazer          converte de novo mesmo se o Excel já existir
```

## fiep db

```
uso: fiep db [-h] [--db DB] [--saida SAIDA] [--sem-usuarios] [--sim] {migrar,sql,zerar} [consulta]

Ações:
  migrar  cria/atualiza o banco
  sql     consulta livre, ex.: fiep db sql "SELECT tipo, COUNT(*) FROM ensaios GROUP BY tipo"
  zerar   apaga todos os dados e recria o banco (guarda uma cópia em dados/backup/; mantém as contas de
          usuário, salvo --sem-usuarios; pede confirmação, salvo --sim). Também é o caminho para sair
          de um banco da versão anterior (com o case de exemplo)

argumentos:
  {migrar,sql,zerar}  o que fazer
  consulta            consulta SQL (ação sql)

opções:
  -h, --help          mostra esta ajuda
  --db DB             arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou dados/fiep.db)
  --saida SAIDA       sql: salva o resultado em .csv
  --sem-usuarios      zerar: apagar também as contas de usuário
  --sim               zerar: não pedir confirmação (scripts)
```

## fiep servir

```
uso: fiep servir [-h] [--db DB] [--modelos MODELOS] [--host HOST] [--porta PORTA] [--sem-compilar]

Serve o frontend compilado (web/dist) e a API. Primeiro acesso: fiep usuario criar --papel admin. Variáveis de ambiente: ver docs/PLATAFORMA.md.

opções:
  -h, --help         mostra esta ajuda
  --db DB            arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou dados/fiep.db)
  --modelos MODELOS  pasta dos modelos (padrão: modelos)
  --host HOST        endereço (0.0.0.0 para a rede local)
  --porta PORTA      porta (padrão: 8000)
  --sem-compilar     não compilar a tela automaticamente quando ela estiver desatualizada
```

## fiep usuario

```
uso: fiep usuario [-h] [--email EMAIL] [--nome NOME] [--papel {admin,colaborador,leitor}]
                    [--instituicao INSTITUICAO] [--db DB]
                    {criar,listar,senha,desativar}

criar e senha pedem a senha no terminal (ou leem FIEP_SENHA_NOVA). Perfis: admin (tudo), colaborador (envia e edita dados), leitor (consulta).

argumentos:
  {criar,listar,senha,desativar}  o que fazer

opções:
  -h, --help                      mostra esta ajuda
  --email EMAIL                   e-mail (login) da conta
  --nome NOME                     nome completo (criar)
  --papel {admin,colaborador,leitor}
                                  perfil (criar; padrão: colaborador)
  --instituicao INSTITUICAO       instituição (criar)
  --db DB                         arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou
                                  dados/fiep.db)
```

## fiep verificar

```
uso: fiep verificar [-h] [--db DB] [--modelos MODELOS]

diagnóstico da instalação (dependências, banco, modelo, frontend)

opções:
  -h, --help         mostra esta ajuda
  --db DB            arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou dados/fiep.db)
  --modelos MODELOS  pasta dos modelos (padrão: modelos)
```

## fiep docs

```
uso: fiep docs [-h] [--saida SAIDA]

regera docs/COMANDOS.md a partir desta ajuda

opções:
  -h, --help     mostra esta ajuda
  --saida SAIDA  arquivo (padrão: docs/COMANDOS.md)
```
