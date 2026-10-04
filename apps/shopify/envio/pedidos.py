"""Pedido do hub -> orderUpdate do Shopify: so observacao, e-mail e endereco de entrega.

Itens, valores e status de pagamento nao voltam para o Shopify (orderEdit e
outro fluxo); o pedido nasce la, por isso criar e excluir nao sao suportados.
O Pedido nao tem tags, entao tags nao sao enviadas.
"""

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import Pedido
from apps.shopify.envio.base import RecursoShopify
from apps.shopify.envio.clientes import telefone_e164

ATUALIZAR = """mutation($input: OrderInput!) {
  orderUpdate(input: $input) { order { id } userErrors { field message } }
}"""


def endereco_shopify(endereco):
    """Address do hub -> MailingAddressInput (rua e numero juntos, como o Shopify guarda).

    Campo vazio e omitido: `countryCode` e enum e `phone` e E.164, e um "" ou um
    telefone local faria o Shopify recusar o orderUpdate inteiro (nota e e-mail juntos).
    Omitir nao preserva o valor antigo: o shippingAddress enviado substitui o do Shopify.
    """
    rua = endereco.address_line_1
    if endereco.number:
        rua = f"{rua}, {endereco.number}".strip(", ")
    complemento = ", ".join(
        p for p in (endereco.complement or endereco.address_line_2, endereco.neighborhood) if p)
    nome = (endereco.recipient_name or endereco.name or "").split(None, 1)
    campos = {
        "firstName": nome[0] if nome else "", "lastName": nome[1] if len(nome) > 1 else "",
        "company": endereco.company, "phone": telefone_e164(endereco.phone),
        "address1": rua, "address2": complemento, "city": endereco.city,
        "provinceCode": endereco.state_code, "zip": endereco.postal_code,
        "countryCode": endereco.country_code,
    }
    return {campo: valor for campo, valor in campos.items() if valor}


class PedidoShopify(RecursoShopify):
    recurso = "pedidos"
    entidade = "pedidos"
    modelo = Pedido

    def criar(self, obj):
        raise EnvioNaoSuportado("pedido nasce no Shopify: o hub nao cria pedido la.")

    def excluir(self, external_id):
        raise EnvioNaoSuportado("pedido nao e excluido no Shopify pelo hub.")

    def atualizar(self, obj, external_id):
        entrada = {"id": self.gid("Order", external_id), "note": obj.notas}
        if obj.email:
            entrada["email"] = obj.email
        if obj.endereco_entrega_id:
            entrada["shippingAddress"] = endereco_shopify(obj.endereco_entrega)
        self.mutacao(ATUALIZAR, {"input": entrada}, "orderUpdate")
