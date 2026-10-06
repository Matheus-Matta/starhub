# Portainer Agent (Docker Standalone)

Esse Compose fica separado da stack do StarHub. Rode os comandos abaixo dentro desta pasta.

## 1. Configure o acesso na AWS

No Security Group da instancia que roda o Agent, adicione uma regra de entrada:

- Tipo: Custom TCP
- Porta: `9001`
- Origem: `34.231.182.73/32` (servidor Portainer)

Nao libere a porta 9001 para `0.0.0.0/0`. O Agent acessa o socket do Docker e permite ao Portainer administrar o host. Se UFW estiver ativo, aplique a mesma restricao nele.

## 2. Inicie o Agent

```bash
cd docker/portainer-agent
docker compose pull
docker compose up -d
docker compose ps
```

Se o Portainer Server tiver sido configurado com um `AGENT_SECRET` proprio, coloque o mesmo valor em `.env` nesta pasta. O padrao do Portainer nao exige esse segredo.

## 3. Conecte pelo Portainer

No Portainer, abra **Environments > Add environment > Docker Standalone > Agent**. Informe como endereco o IP publico ou DNS da instancia que roda este Agent, seguido de `:9001`, sem `http://` ou `https://`.

`34.231.182.73` e o IP de origem autorizado na AWS. O endereco do Agent e o IP/DNS da instancia StarHub. Se as duas instancias estiverem na mesma VPC, prefira usar o IP privado do Agent e uma regra de Security Group referenciando o Security Group do Portainer.

O Agent tradicional precisa aceitar conexoes na porta 9001. A documentacao do Portainer recomenda o Edge Agent quando essa conexao de entrada nao puder ser aberta; o assistente **Add environment** gera a configuracao apropriada.