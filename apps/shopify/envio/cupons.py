"""Cupom do hub -> desconto com codigo do Shopify: so atualizar e excluir.

O codigo que o cliente digita nunca e enviado (nem no update): o hub guarda um
codigo interno aleatorio e sobrescrever o do Shopify quebraria as campanhas.
"""

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import Cupom
from apps.shopify.cliente import ShopifyErro
from apps.shopify.cupons_vinculo import dados, gravar, vinculo
from apps.shopify.envio.base import RecursoShopify

CONSULTAR_STATUS = """query($id: ID!) {
  codeDiscountNode(id: $id) { codeDiscount {
    ... on DiscountCodeBasic { status } ... on DiscountCodeFreeShipping { status }
  } }
}"""

ATUALIZAR_BASICO = """mutation($id: ID!, $desconto: DiscountCodeBasicInput!) {
  discountCodeBasicUpdate(id: $id, basicCodeDiscount: $desconto) {
    codeDiscountNode { id } userErrors { field message }
  }
}"""
ATUALIZAR_FRETE = """mutation($id: ID!, $desconto: DiscountCodeFreeShippingInput!) {
  discountCodeFreeShippingUpdate(id: $id, freeShippingCodeDiscount: $desconto) {
    codeDiscountNode { id } userErrors { field message }
  }
}"""
ATIVAR = """mutation($id: ID!) {
  discountCodeActivate(id: $id) { codeDiscountNode { id } userErrors { field message } }
}"""
DESATIVAR = """mutation($id: ID!) {
  discountCodeDeactivate(id: $id) { codeDiscountNode { id } userErrors { field message } }
}"""
EXCLUIR = """mutation($id: ID!) {
  discountCodeDelete(id: $id) { deletedCodeDiscountId userErrors { field message } }
}"""

BASICO, FRETE = "DiscountCodeBasic", "DiscountCodeFreeShipping"


def _tipo(cupom):
    conhecido = dados(cupom).get("tipo")
    if conhecido:
        return conhecido
    return FRETE if cupom.discount_type == Cupom.TipoDesconto.FRETE_GRATIS else BASICO


class CupomShopify(RecursoShopify):
    recurso = "cupons"
    entidade = "cupons"
    modelo = Cupom

    def criar(self, obj):
        raise EnvioNaoSuportado(
            "cupom criado no hub nao tem codigo para o cliente digitar no Shopify: "
            "crie o desconto no Shopify e sincronize."
        )

    def _entrada(self, cupom):
        entrada = {
            "title": cupom.name,
            # None remove o termino; sem isso o Shopify manteria uma data antiga.
            "endsAt": cupom.ends_at.isoformat() if cupom.ends_at else None,
            "usageLimit": cupom.usage_limit,
            "appliesOncePerCustomer": bool(cupom.usage_limit_per_customer),
        }
        if cupom.starts_at:
            entrada["startsAt"] = cupom.starts_at.isoformat()
        return entrada

    def atualizar(self, obj, external_id):
        tipo = _tipo(obj)
        if tipo not in (BASICO, FRETE):
            raise EnvioNaoSuportado(f"desconto do tipo {tipo} nao e editado pelo hub.")
        id_shopify = self.gid("DiscountCodeNode", external_id)
        ativo = obj.status == Cupom.Status.ATIVO
        atual = self._status_no_shopify(id_shopify)
        # O status do Shopify espelha o do hub, mas so vira mutation se o de AGORA
        # for diferente: desativar o que ja esta desativado volta userErrors e o envio
        # apareceria como Falhou sem ter falhado. SCHEDULED nao e ativado aqui: o
        # update abaixo manda o startsAt do hub e o Shopify ativa na data.
        ativar = ativo and atual == "EXPIRED"
        desativar = not ativo and atual in ("ACTIVE", "SCHEDULED")
        # Reativar antes do update: o Shopify mexe em endsAt ao ativar/desativar, e o
        # update (com as datas do hub) precisa ser a ultima palavra sobre as datas.
        if ativar:
            self.mutacao(ATIVAR, {"id": id_shopify}, "discountCodeActivate")
        query, campo = ((ATUALIZAR_FRETE, "discountCodeFreeShippingUpdate") if tipo == FRETE
                        else (ATUALIZAR_BASICO, "discountCodeBasicUpdate"))
        self.mutacao(query, {"id": id_shopify, "desconto": self._entrada(obj)}, campo)
        if desativar:
            self.mutacao(DESATIVAR, {"id": id_shopify}, "discountCodeDeactivate")
        if ativar or desativar:
            # Ativar deixa ACTIVE; desativar fixa o termino em "agora" (EXPIRED).
            atual = "ACTIVE" if ativar else "EXPIRED"
        # Grava no vinculo do Shopify, nao no cupom: o cupom do hub nao leva dado de
        # marketplace e o vinculo nao gera eco de volta para o Shopify.
        gravar(vinculo(obj), {"status": atual})

    def _status_no_shopify(self, id_shopify):
        no = (self.cliente.graphql(CONSULTAR_STATUS, {"id": id_shopify}) or {}
              ).get("codeDiscountNode") or {}
        status = ((no.get("codeDiscount") or {}).get("status") or "").upper()
        if not status:
            raise ShopifyErro(
                "O Shopify nao devolveu o status do desconto: confira se ele ainda existe "
                "e sincronize os cupons antes de enviar de novo.")
        return status

    def excluir(self, external_id):
        self.mutacao(EXCLUIR, {"id": self.gid("DiscountCodeNode", external_id)},
                     "discountCodeDelete")
