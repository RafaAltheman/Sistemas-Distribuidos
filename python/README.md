# Sistema de Mensagens Instantâneas com ZeroMQ

Projeto da **Parte 1** de Sistemas Distribuídos implementado em **Python**, com foco em:

- login automático de bots
- criação de canais
- listagem de canais
- serialização binária com **MessagePack**
- troca de mensagens com **ZeroMQ**
- persistência em disco com **SQLite**
- execução com **Docker Compose**
- replicação básica de dados entre 2 servidores sem compartilhar o mesmo arquivo de dados

## Aviso importante sobre o enunciado

Este projeto está **100% em Python**, seguindo o que foi pedido aqui na conversa. Porém, o enunciado informa que, **se o trabalho for individual, devem existir pelo menos 2 linguagens diferentes**.

Então esta entrega funciona tecnicamente para a Parte 1, mas **pode precisar de uma segunda linguagem** para ficar 100% aderente ao critério de avaliação do professor.

---

## Estrutura do projeto

```text
.
├── broker.py
├── cliente.py
├── servidor.py
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Escolhas de projeto

### 1) Comunicação

Foi utilizado **ZeroMQ** com o seguinte desenho:

- **cliente** usa socket `REQ`
- **broker** usa `ROUTER` na frente e `DEALER` atrás
- **servidor** usa `REP`

Fluxo:

```text
cliente -> broker(5555) -> broker(5556) -> servidor
servidor -> broker -> cliente
```

Isso permite distribuir requisições entre múltiplos servidores.

### 2) Serialização binária

Foi escolhido **MessagePack**, pois:

- é binário
- é simples de usar em Python
- atende ao enunciado, que proíbe JSON/XML/texto simples

### 3) Persistência

Cada servidor mantém seu próprio banco **SQLite** em disco:

- `servidor1` grava em `/app/data/server1.db`
- `servidor2` grava em `/app/data/server2.db`

Dados persistidos:

- logins realizados (`logins`)
- canais criados (`channels`)
- eventos processados (`processed_events`)

### 4) Replicação entre servidores

O enunciado exige que:

- cada servidor mantenha seu próprio conjunto de dados
- canais criados possam ser usados por outros usuários

Para atender isso sem compartilhar o mesmo arquivo, cada servidor:

- publica eventos locais em um socket `PUB`
- escuta eventos do outro servidor com `SUB`
- replica localmente logins e canais

Assim, os dois servidores mantêm arquivos independentes, mas os dados acabam convergindo.

---

## Formato das mensagens

### Requisição

Exemplo lógico de mensagem de requisição:

```python
{
  "type": "request",
  "operation": "login",
  "request_id": "uuid",
  "timestamp": "2026-03-16T00:00:00+00:00",
  "user": "bot_alpha",
  "data": {}
}
```

### Resposta

```python
{
  "type": "response",
  "operation": "login",
  "request_id": "uuid",
  "timestamp": "2026-03-16T00:00:01+00:00",
  "server_id": "servidor1",
  "status": "ok",
  "data": {"message": "login realizado para bot_alpha"},
  "error": null
}
```

### Operações implementadas

- `login`
- `create_channel`
- `list_channels`

---

## Regras adotadas

### Login

- nome de usuário deve seguir regex: `^[a-zA-Z0-9_-]{3,32}$`
- logins repetidos são aceitos
- cada login é armazenado com timestamp

### Canal

- nome do canal deve seguir regex: `^[a-zA-Z0-9_-]{3,32}$`
- canal duplicado retorna erro `channel_exists`

### Erros possíveis

- `invalid_username`
- `invalid_channel_name`
- `channel_exists`
- `unknown_operation`

---

## Execução

Na pasta do projeto, rode:

```bash
docker compose up --build
```

Isso irá subir:

- 1 broker
- 2 servidores
- 2 clientes bots

Os clientes executam automaticamente:

1. login
2. listagem de canais
3. criação de canal, se necessário
4. nova listagem

---

## O que será exibido nos logs

O projeto imprime no terminal:

- mensagens enviadas e recebidas pelos clientes
- requisições e respostas processadas pelos servidores
- mensagens encaminhadas pelo broker
- eventos de replicação entre servidores

Isso atende ao requisito de mostrar claramente o conteúdo trocado.

---

## Observações finais

Este projeto cobre a **Parte 1** do enunciado com:

- bots sem interação manual
- execução por orquestrador
- persistência em disco
- login
- criação de canais
- listagem de canais
- 2 clientes e 2 servidores

Para as próximas partes, pode-se expandir o mesmo protocolo para:

- postagem em canais
- recuperação de histórico
- envio/replicação de mensagens entre servidores