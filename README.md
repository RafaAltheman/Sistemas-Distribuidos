# Projeto de Sistemas Distribuídos - Parte 1

## Descrição

Nesta etapa, o sistema permite:

- fazer login de usuário
- listar os canais existentes
- criar novos canais

O projeto foi feito para funcionar com clientes e servidores em linguagens diferentes, usando um broker para intermediar a comunicação.

---

## Linguagens usadas

As linguagens utilizadas no projeto foram:

- Python
- Java
- C

Temos clientes e servidores nessas linguagens, além do broker.

---

## O que foi implementado

Nesta primeira parte foram implementadas as seguintes funcionalidades:

- login de usuário usando apenas nome
- listagem de canais
- criação de canais
- armazenamento dos dados em disco
- replicação das informações entre os servidores
- mensagens com timestamp
- serialização binária

---

## Comunicação

A comunicação funciona assim:

### Login
O cliente envia um pedido de login com o nome do usuário.  
O servidor responde se deu certo ou não.

### Listar canais
O cliente pede a lista de canais.  
O servidor responde com os nomes dos canais já criados.

### Criar canal
O cliente envia o nome do canal.  
O servidor responde com sucesso ou erro.

---

## Serialização

As mensagens foram serializadas em **MessagePack**.

Escolhemos esse formato porque ele é binário, funciona em várias linguagens e atende ao que foi pedido no enunciado.

---

## Persistência

A persistência foi feita com **SQLite**.

Cada servidor tem seu próprio banco de dados, ou seja, cada um salva suas informações separadamente.

Nesta parte, são armazenados:

- os logins feitos pelos usuários com timestamp
- os canais criados

---

## Replicação

Os servidores trocam informações entre si para que todos fiquem atualizados.

Nesta etapa, são replicados:

- logins
- criação de canais

Assim, um canal criado em um servidor também aparece nos outros.

---

## Arquivos do projeto

O projeto contém:

- `README.md`
- `Dockerfile`
- `docker-compose.yml`
- código dos clientes
- código dos servidores
- código do broker

---

## Como executar

Para rodar o projeto, basta usar o comando:

```bash
docker compose up --build
