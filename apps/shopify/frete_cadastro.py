"""Cadastra (ou atualiza) o StarHub como calculadora de frete da loja (CarrierService).

Roda numa tarefa (botao "Cadastrar frete no checkout" em Integracoes > Shopify). Uma
vez por loja: depois a Shopify chama /integracoes/shopify/frete/<uuid>/ sozinha em
todo checkout. Rodar de novo atualiza o mesmo cadastro (o id fica no vinculo
"carrier_service"); se o vinculo sumiu, acha pelo nome antes de criar outro.

Exige o escopo write_shipping no app e, na loja, calculadora de frete de terceiros
liberada (plano Advanced/Plus, ou pedido ao suporte da Shopify nos planos menores).
"""

from urllib.parse import urljoin

from django.urls import reverse

from apps.core.models import ExternalReference, Origin
from apps.shopify.cliente import ShopifyClient, ShopifyErro

NOME = "StarHub Frete"
ENTIDADE = "carrier_service"
CAMPOS = "carrierService { id name callbackUrl active } userErrors { field message }"
LISTAR = "query { carrierServices(first: 50) { nodes { id name callbackUrl } } }"
CRIAR = ("mutation ($input: DeliveryCarrierServiceCreateInput!) { "
         f"carrierServiceCreate(input: $input) {{ {CAMPOS} }} }}")
ATUALIZAR = ("mutation ($input: DeliveryCarrierServiceUpdateInput!) { "
             f"carrierServiceUpdate(input: $input) {{ {CAMPOS} }} }}")


def url_de_cotacao(configuracao):
    if not configuracao.url_webhook.startswith("https://"):
        raise ValueError("A Shopify so chama endereco https: preencha a URL publica dos "
                         "webhooks (https://...) em Integracoes > Shopify.")
    caminho = reverse("shopify_frete", args=[configuracao.uuid])
    return urljoin(configuracao.url_webhook, caminho)


def _vinculo(configuracao):
    return ExternalReference.all_objects.filter(
        account_id=configuracao.account_id, platform=Origin.SHOPIFY, entity_type=ENTIDADE,
        object_id=str(configuracao.pk)).first()


def _mutacao(cliente, query, entrada, campo):
    dados = (cliente.graphql(query, {"input": entrada}) or {}).get(campo) or {}
    erros = dados.get("userErrors") or []
    if erros:
        raise ShopifyErro("; ".join(erro.get("message", str(erro)) for erro in erros))
    return dados["carrierService"]


def cadastrar_frete(configuracao, progresso):
    url = url_de_cotacao(configuracao)
    cliente = ShopifyClient(configuracao)
    vinculo = _vinculo(configuracao)
    existente = vinculo.external_id if vinculo else next(
        (no["id"] for no in (cliente.graphql(LISTAR).get("carrierServices") or {}).get("nodes", [])
         if no.get("name") == NOME), None)
    progresso(0, 1, "Cadastrando o frete no checkout")
    # active segue o liga/desliga do hub: inativo, a Shopify para de chamar a cotacao.
    entrada = {"name": NOME, "callbackUrl": url, "active": configuracao.frete_ativo,
               "supportsServiceDiscovery": True}
    if existente:
        servico = _mutacao(cliente, ATUALIZAR, {"id": existente, **entrada},
                           "carrierServiceUpdate")
        feito = "atualizado"
    else:
        servico = _mutacao(cliente, CRIAR, entrada, "carrierServiceCreate")
        feito = "cadastrado"
    ExternalReference.all_objects.update_or_create(
        account_id=configuracao.account_id, platform=Origin.SHOPIFY, entity_type=ENTIDADE,
        object_id=str(configuracao.pk),
        defaults={"external_id": servico["id"], "origin": Origin.SHOPIFY,
                  "metadata": {"callback_url": url}})
    if not configuracao.frete_ativo:
        feito += " (desligado: a Shopify nao chama a cotacao)"
    progresso(1, 1, "Frete no checkout " + feito)
    return (f"Frete do StarHub {feito} na loja. A Shopify passa a cotar em {url}; marque "
            "\"oferecer no checkout\" nas tabelas de frete que devem aparecer.")
