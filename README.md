# Sistema de mensagens instantâneas — Python + Java + C

Projeto da Parte 1 de Sistemas Distribuídos, com **três linguagens** se comunicando ao mesmo tempo:

- **Python**: cliente e servidor
- **Java**: cliente e servidor
- **C**: cliente e servidor
- **Broker**: Python com ZeroMQ

## O que o projeto implementa

- login de usuário
- listagem de canais
- criação de canais
- persistência em disco por servidor
- replicação simples entre servidores de linguagens diferentes
- execução com `docker compose up --build`

## Regras do enunciado atendidas

- **ZeroMQ** para troca de mensagens

- **containers** com Docker Compose
- **timestamp** em todas as mensagens
- **serialização binária** com **MessagePack**
- **clientes e servidores mostram no terminal** todas as mensagens enviadas/recebidas
- **cada servidor mantém seu próprio banco SQLite**
- **clientes e servidores de linguagens diferentes conversam entre si**


## Arquitetura

### Requisições de cliente para servidor

- cliente usa **REQ** para `broker:5555`
- broker usa **ROUTER/DEALER** para balancear
- servidor usa **REP** para `broker:5556`

Assim, qualquer cliente pode ser atendido por qualquer servidor, independente da linguagem.

### Replicação entre servidores

Cada servidor:

- publica eventos em um socket **PUB** próprio
- assina os sockets **SUB** dos outros servidores

Eventos replicados:

- `login`
- `create_channel`

## Formato das mensagens

### Requisição

Campos principais:

- `type`
- `operation`
- `request_id`
- `timestamp`
- `user`
- `data`

### Resposta

Campos principais:

- `type`
- `operation`
- `request_id`
- `timestamp`
- `server_id`
- `status`
- `data`
- `error`

### Evento de replicação

Campos principais:

- `event_type`
- `event_id`
- `timestamp`
- `origin_server`
- `user`
- `channel` (quando aplicável)

## Persistência

Cada servidor grava seu próprio banco SQLite em disco:

- `logins`
- `channels`
- `replication_events`

Pastas persistidas:

- `./data/python`
- `./data/java`
- `./data/c`

## Como executar

Na raiz do projeto:

```bash
docker compose up --build
```

## Fluxo esperado na demonstração

- `client_python` faz login e cria `geral`
- `client_java` faz login e cria `java_room`
- `client_c` faz login e cria `c_room`
- os servidores replicam os eventos
- qualquer servidor pode listar todos os canais já replicados

## Observação importante

A parte em **C** foi implementada para conversar com Python e Java usando o mesmo protocolo MessagePack e SQLite. O ponto mais sensível costuma ser a build de dependências nativas no ambiente Docker. Se alguma imagem falhar no `docker compose up --build`, o ajuste mais provável será somente de pacote/compilação do container C.
