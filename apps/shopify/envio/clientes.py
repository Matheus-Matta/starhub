"""Cliente do hub -> Customer do Shopify (customerCreate/Update/Delete)."""

import re

from apps.loja.models import Cliente
from apps.shopify.envio.base import RecursoShopify

CRIAR = """mutation($input: CustomerInput!) {
  customerCreate(input: $input) { customer { id } userErrors { field message } }
}"""
ATUALIZAR = """mutation($input: CustomerInput!) {
  customerUpdate(input: $input) { customer { id } userErrors { field message } }
}"""
CONSENTIMENTO = """mutation($input: CustomerEmailMarketingConsentUpdateInput!) {
  customerEmailMarketingConsentUpdate(input: $input) {
    customer { id } userErrors { field message }
  }
}"""
EXCLUIR = """mutation($input: CustomerDeleteInput!) {
  customerDelete(input: $input) { deletedCustomerId userErrors { field message } }
}"""


def telefone_e164(telefone):
    """O Shopify recusa telefone fora do formato E.164; sem DDI assumimos Brasil.

    Telefone que nao vira numero valido e omitido: melhor enviar o cliente sem
    telefone do que perder o envio inteiro por causa dele.
    """
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return None
    if (telefone or "").strip().startswith("+"):
        return f"+{digitos}" if 8 <= len(digitos) <= 15 else None
    if len(digitos) in (10, 11):
        return f"+55{digitos}"
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        return f"+{digitos}"
    return None


class ClienteShopify(RecursoShopify):
    recurso = "clientes"
    entidade = "clientes"
    modelo = Cliente

    @staticmethod
    def _consentimento(cliente):
        return {
            "marketingState": "SUBSCRIBED" if cliente.aceita_marketing else "UNSUBSCRIBED",
            "marketingOptInLevel": "SINGLE_OPT_IN",
        }

    def _entrada(self, cliente):
        entrada = {
            "email": cliente.email, "firstName": cliente.nome, "lastName": cliente.sobrenome,
            "note": cliente.notas,
        }
        telefone = telefone_e164(cliente.telefone)
        if telefone:
            entrada["phone"] = telefone
        return entrada

    def criar(self, obj):
        entrada = self._entrada(obj)
        if obj.email:  # a doc exige o e-mail para criar com consentimento
            entrada["emailMarketingConsent"] = self._consentimento(obj)
        dados = self.mutacao(CRIAR, {"input": entrada}, "customerCreate")
        return dados["customer"]["id"]

    def atualizar(self, obj, external_id):
        entrada = {"id": self.gid("Customer", external_id), **self._entrada(obj)}
        self.mutacao(ATUALIZAR, {"input": entrada}, "customerUpdate")
        # O customerUpdate nao aceita consentimento de marketing (doc 2026-07): tem
        # mutation propria, e ela exige que o cliente tenha e-mail.
        if obj.email:
            consentimento = {"customerId": entrada["id"],
                             "emailMarketingConsent": self._consentimento(obj)}
            self.mutacao(CONSENTIMENTO, {"input": consentimento},
                         "customerEmailMarketingConsentUpdate")

    def excluir(self, external_id):
        self.mutacao(EXCLUIR, {"input": {"id": self.gid("Customer", external_id)}},
                     "customerDelete")
