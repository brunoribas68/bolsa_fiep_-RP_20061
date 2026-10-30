# Comandos `fiep`

Gerado por `fiep docs` a partir da ajuda dos comandos — não edite à mão. Sem instalar o pacote, use `python -m fiep` na raiz do repositório.

| Comando | Para quê |
|---|---|
| [`fiep planilha`](#fiep-planilha) | gera amostras.csv (1 linha por amostra) e metadados_nox.csv já preenchidos |
| [`fiep excel`](#fiep-excel) | converte .nox para Excel no formato do NOVA |
| [`fiep db`](#fiep-db) | banco de dados: migrar, importar, resumo, sql, exportar, exemplo, zerar |
| [`fiep experimento`](#fiep-experimento) | divide 50/25/25, compara representações x modelos e registra o melhor |
| [`fiep prever`](#fiep-prever) | classifica dados novos com o modelo registrado (por amostra e por eletrodo) |
| [`fiep modelos`](#fiep-modelos) | modelos treinados: listar, mostrar, ativar, catalogo |
| [`fiep servir`](#fiep-servir) | abre a plataforma web (login, coletas, amostras, previsão) |
| [`fiep usuario`](#fiep-usuario) | contas da plataforma: criar, listar, senha, desativar |
| [`fiep verificar`](#fiep-verificar) | diagnóstico da instalação (dependências, banco, modelo, frontend) |
| [`fiep docs`](#fiep-docs) | regera docs/COMANDOS.md a partir desta ajuda |
| [`fiep ingerir`](#fiep-ingerir) | (avançado) lê .nox/tabelas e grava CSVs canônicos, sem banco |
| [`fiep qc`](#fiep-qc) | (avançado) controle de qualidade dos CSVs canônicos |
| [`fiep treinar`](#fiep-treinar) | (avançado) treino rápido com a configuração, sem comparar variantes |
| [`fiep tudo`](#fiep-tudo) | (avançado) ingerir + treinar |

## fiep planilha

```
uso: fiep planilha [-h] --entrada ENTRADA [--config CONFIG]

Lê os .nox/Excel de uma pasta e deduz amostra (pasta), eletrodo (E1.. no nome ou canal), etapa do sensor e data. Cria metadados_nox.csv (conferência, 1 linha por arquivo) e amostras.csv (rótulo e carga, 1 linha por amostra). Rodar de novo só acrescenta o que é novo.

opções:
  -h, --help         mostra esta ajuda
  --entrada ENTRADA  pasta do lote (ex.: dados/empresa1)
  --config CONFIG    arquivo de configuração (padrão: variável FIEP_CONFIG ou configs/default.toml)
```

## fiep excel

```
uso: fiep excel [-h] --entrada ENTRADA [--saida SAIDA] [--refazer]

converte .nox para Excel no formato do NOVA

opções:
  -h, --help         mostra esta ajuda
  --entrada ENTRADA  pasta com .nox (ex.: dados/empresa1)
  --saida SAIDA      pasta de saída (padrão: dados/excel/<lote>)
  --refazer          converte de novo mesmo se o Excel já existir
```

## fiep db

```
uso: fiep db [-h] [--db DB] [--entrada ENTRADA] [--empresa EMPRESA] [--conjunto {treino,validacao,teste}]
               [--sem-excel] [--sem-exemplo] [--sem-usuarios] [--sim] [--remover] [--formato {xlsx,csv}]
               [--saida SAIDA] [--config CONFIG]
               {migrar,importar,resumo,exportar,sql,exemplo,zerar} [consulta]

Ações:
  migrar    cria/atualiza o banco pelas migrations (com os dados de exemplo, salvo --sem-exemplo)
  importar  lê --entrada (.nox, Excel/CSV do NOVA, planilhas), roda o QC e grava; com a pasta dados/,
            o que está em treino/ validacao/ teste/ é gravado com o seu conjunto
  resumo    contagens (amostras, medições, réplicas completas, QC...)
  sql       consulta livre, ex.: fiep db sql "SELECT * FROM v_replicatas WHERE n_aprovadas < 3"
  exportar  tudo para Excel (uma aba por tabela) ou CSV
  exemplo   carrega o case de demonstração (--remover para apagar)
  zerar     apaga todos os dados e recria o banco (guarda uma cópia em dados/backup/; mantém as
            contas de usuário, salvo --sem-usuarios; pede confirmação, salvo --sim)

argumentos:
  {migrar,importar,resumo,exportar,sql,exemplo,zerar}
                                  o que fazer
  consulta                        consulta SQL (ação sql)

opções:
  -h, --help                      mostra esta ajuda
  --db DB                         arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou
                                  dados/fiep.db)
  --entrada ENTRADA               importar: pasta com os dados (ex.: dados)
  --empresa EMPRESA               importar: nome da empresa dos dados
  --conjunto {treino,validacao,teste}
                                  importar: grava tudo como deste conjunto (padrão: sorteio, ou o da subpasta)
  --sem-excel                     importar: não gerar a cópia em Excel (dados/excel/)
  --sem-exemplo                   migrar/zerar: não carregar os dados de exemplo
  --sem-usuarios                  zerar: apagar também as contas de usuário
  --sim                           zerar: não pedir confirmação (scripts)
  --remover                       exemplo: apagar os dados de exemplo
  --formato {xlsx,csv}            exportar: formato (padrão xlsx)
  --saida SAIDA                   exportar/sql: arquivo ou pasta de saída
  --config CONFIG                 arquivo de configuração (padrão: variável FIEP_CONFIG ou
                                  configs/default.toml)
```

## fiep experimento

```
uso: fiep experimento [-h] [--dados DADOS] [--db DB] [--filtro FILTRO] [--filtro-treino FILTRO_TREINO]
                        [--filtro-validacao FILTRO_VALIDACAO] [--filtro-teste FILTRO_TESTE] [--com-exemplo]
                        [--saida SAIDA] [--modelos MODELOS] [--rapido] [--algoritmos ALGORITMOS]
                        [--variantes VARIANTES] [--nao-ativar] [--artigo] [--artigo-pasta ARTIGO_PASTA]
                        [--config CONFIG]

Divide as amostras em treino/validação/teste (padrão 50/25/25, por amostra, estratificado), ajusta 5 representações x 15 algoritmos no treino (lista: fiep modelos catalogo), escolhe pela validação, re-treina com treino+validação e mede uma vez no teste. Registra o melhor em modelos/ (usado pela plataforma) e gera figuras/tabelas.

opções:
  -h, --help                      mostra esta ajuda
  --dados DADOS                   pasta de dados (padrão: dados). Solto em dados/ = sorteio; dados/treino,
                                  dados/validacao e dados/teste = somados ao conjunto
  --db DB                         usar o banco em vez das pastas (arquivo SQLite ou URL do banco (padrão:
                                  variável FIEP_DB_URL ou dados/fiep.db))
  --filtro FILTRO                 com --db: filtro SQL das medições, ex.: "empresa_id = 2"
  --filtro-treino FILTRO_TREINO   com --db: filtro SQL de amostras que vão inteiras para o treino
  --filtro-validacao FILTRO_VALIDACAO
                                  com --db: idem, para a validação
  --filtro-teste FILTRO_TESTE     com --db: idem, para o teste (ex.: outra empresa)
  --com-exemplo                   com --db: inclui os dados de exemplo mesmo havendo dados reais
  --saida SAIDA                   pasta dos resultados (padrão: resultados)
  --modelos MODELOS               pasta onde o modelo é registrado (padrão: modelos)
  --rapido                        menos variantes e modelos (para testar)
  --algoritmos ALGORITMOS         só estes classificadores, separados por vírgula (lista: fiep modelos
                                  catalogo)
  --variantes VARIANTES           só estas representações, separadas por vírgula (lista: fiep modelos
                                  catalogo)
  --nao-ativar                    registra o modelo sem trocar o que está em uso (para comparar)
  --artigo                        copia figuras, tabelas e números para o artigo
  --artigo-pasta ARTIGO_PASTA     destino do --artigo (padrão: artigo/gerado)
  --config CONFIG                 arquivo de configuração (padrão: variável FIEP_CONFIG ou
                                  configs/default.toml)
```

## fiep prever

```
uso: fiep prever [-h] --entrada ENTRADA [--modelo MODELO] [--saida SAIDA] [--db DB] [--config CONFIG]

classifica dados novos com o modelo registrado (por amostra e por eletrodo)

opções:
  -h, --help         mostra esta ajuda
  --entrada ENTRADA  pasta com .nox/Excel (uma subpasta por amostra)
  --modelo MODELO    pasta de modelos (usa ATUAL) ou a pasta de um modelo
  --saida SAIDA      CSV com o resultado por eletrodo (+ <nome>_amostras.csv)
  --db DB            gravar as previsões neste banco
  --config CONFIG    arquivo de configuração (padrão: variável FIEP_CONFIG ou configs/default.toml); usa os
                     [niveis] de contaminação dela
```

## fiep modelos

```
uso: fiep modelos [-h] [--id ID] [--modelos MODELOS] [--resultados RESULTADOS]
                    {listar,mostrar,ativar,catalogo}

Ações:
  listar    modelos registrados, com as métricas no teste (* = em uso)
  mostrar   métricas e comparação de um modelo (--id)
  ativar    passa a usar o modelo --id na plataforma e no fiep prever
  catalogo  algoritmos e representações disponíveis para o fiep experimento

argumentos:
  {listar,mostrar,ativar,catalogo}
                                  o que fazer

opções:
  -h, --help                      mostra esta ajuda
  --id ID                         id do modelo (ex.: 20261022-102514)
  --modelos MODELOS               pasta de modelos (padrão: modelos)
  --resultados RESULTADOS         pasta dos experimentos (padrão: resultados)
```

## fiep servir

```
uso: fiep servir [-h] [--db DB] [--modelos MODELOS] [--host HOST] [--porta PORTA] [--sem-compilar]

Serve o frontend compilado (web/dist) e a API. Primeiro acesso: fiep usuario criar --papel admin. Variáveis de ambiente: ver docs/PLATAFORMA.md.

opções:
  -h, --help         mostra esta ajuda
  --db DB            arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou dados/fiep.db)
  --modelos MODELOS  pasta de modelos (padrão: modelos)
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
  --modelos MODELOS  pasta de modelos (padrão: modelos)
```

## fiep docs

```
uso: fiep docs [-h] [--saida SAIDA]

regera docs/COMANDOS.md a partir desta ajuda

opções:
  -h, --help     mostra esta ajuda
  --saida SAIDA  arquivo (padrão: docs/COMANDOS.md)
```

## fiep ingerir

```
uso: fiep ingerir [-h] --entrada ENTRADA [--saida SAIDA] [--config CONFIG]

(avançado) lê .nox/tabelas e grava CSVs canônicos, sem banco

opções:
  -h, --help         mostra esta ajuda
  --entrada ENTRADA  pasta com os dados
  --saida SAIDA      pasta de saída (padrão: dados/processados)
  --config CONFIG    arquivo de configuração (padrão: variável FIEP_CONFIG ou configs/default.toml)
```

## fiep qc

```
uso: fiep qc [-h] [--dados DADOS] [--config CONFIG]

(avançado) controle de qualidade dos CSVs canônicos

opções:
  -h, --help       mostra esta ajuda
  --dados DADOS    pasta do ingerir (padrão: dados/processados)
  --config CONFIG  arquivo de configuração (padrão: variável FIEP_CONFIG ou configs/default.toml)
```

## fiep treinar

```
uso: fiep treinar [-h] [--dados DADOS] [--db DB] [--filtro FILTRO] [--modelos MODELOS] [--config CONFIG]

(avançado) treino rápido com a configuração, sem comparar variantes

opções:
  -h, --help         mostra esta ajuda
  --dados DADOS      pasta do ingerir (padrão: dados/processados)
  --db DB            treinar com o banco (arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou
                     dados/fiep.db))
  --filtro FILTRO    com --db: filtro SQL das medições
  --modelos MODELOS  pasta de modelos (padrão: modelos)
  --config CONFIG    arquivo de configuração (padrão: variável FIEP_CONFIG ou configs/default.toml)
```

## fiep tudo

```
uso: fiep tudo [-h] --entrada ENTRADA [--dados DADOS] [--db DB] [--filtro FILTRO] [--modelos MODELOS]
                 [--config CONFIG]

(avançado) ingerir + treinar

opções:
  -h, --help         mostra esta ajuda
  --entrada ENTRADA  pasta com os dados
  --dados DADOS      pasta intermediária (padrão: dados/processados)
  --db DB            também importar para este banco e treinar a partir dele
  --filtro FILTRO    com --db: filtro SQL das medições
  --modelos MODELOS  pasta de modelos (padrão: modelos)
  --config CONFIG    arquivo de configuração (padrão: variável FIEP_CONFIG ou configs/default.toml)
```
