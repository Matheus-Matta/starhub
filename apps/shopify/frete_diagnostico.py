"""Verifica na loja o que o frete no checkout precisa (tarefa "Verificar frete no checkout").

Cada consulta e independente: se uma falha (campo que mudou na API, escopo faltando),
aquele item vira "nao deu para verificar" com o motivo e os outros seguem. O resultado
fica no vinculo "frete_checkout" (metadata) e a tela da Shopify o mostra
(frete_checklist.py). Nada e alterado na loja.
"""

from django.utils import timezone

from apps.core.models import ExternalReference, Origin
from apps.shopify.cliente import ShopifyClient, ShopifyErro
from apps.shopify.frete_cadastro import url_de_cotacao

ENTIDADE = "frete_checkout"
ESCOPOS = ("read_shipping", "write_shipping")
ESCOPOS_Q = "query { currentAppInstallation { accessScopes { handle } } }"
PLANO_Q = "query { shop { plan { publicDisplayName partnerDevelopment shopifyPlus } } }"
SERVICOS_Q = "query { carrierServices(first: 50) { nodes { id name callbackUrl active } } }"
LOCAIS_Q = ("query { locations(first: 20) { nodes { name isActive "
            "address { zip city province } } } }")
PERFIS_Q = """query { deliveryProfiles(first: 10) { nodes { name default
  profileLocationGroups { locationGroupZones(first: 50) { nodes { zone { name }
    methodDefinitions(first: 50) { nodes { name active rateProvider {
      ... on DeliveryParticipant { carrierService { id } } } } } } } } } } }"""


def _consulta(cliente, query):
    """(dados, erro): erro e o texto para a tela quando a consulta falha."""
    try:
        return cliente.graphql(query) or {}, ""
    except ShopifyErro as erro:
        return {}, str(erro)[:300]


def _escopos(cliente):
    dados, erro = _consulta(cliente, ESCOPOS_Q)
    tem = {e.get("handle") for e in ((dados.get("currentAppInstallation") or {})
                                     .get("accessScopes") or [])}
    return {"faltam": [e for e in ESCOPOS if e not in tem], "erro": erro}


def _plano(cliente):
    dados, erro = _consulta(cliente, PLANO_Q)
    plano = (dados.get("shop") or {}).get("plan") or {}
    nome = plano.get("publicDisplayName") or ""
    # Advanced, Plus e loja de desenvolvimento ja liberam frete de terceiros; plano
    # anual tambem, mas a API nao diz o ciclo de cobranca (fica para conferir a mao).
    liberado = (plano.get("shopifyPlus") or plano.get("partnerDevelopment")
                or any(p in nome.lower() for p in ("advanced", "plus")))
    return {"nome": nome, "erro": erro, "liberado_de_cara": bool(liberado)}


def _servico(cliente, url):
    dados, erro = _consulta(cliente, SERVICOS_Q)
    nos = (dados.get("carrierServices") or {}).get("nodes") or []
    nosso = next((n for n in nos if n.get("callbackUrl") == url), None)
    return {"id": (nosso or {}).get("id", ""), "ativo": bool(nosso and nosso.get("active")),
            "url": url, "erro": erro}


def _locais(cliente):
    dados, erro = _consulta(cliente, LOCAIS_Q)
    nos = (dados.get("locations") or {}).get("nodes") or []
    return {"erro": erro, "lista": [
        {"nome": n.get("name", ""), "cep": ((n.get("address") or {}).get("zip") or ""),
         "cidade": ((n.get("address") or {}).get("city") or "")}
        for n in nos if n.get("isActive", True)]}


def _zonas_com_o_servico(cliente, servico_id):
    dados, erro = _consulta(cliente, PERFIS_Q)
    zonas = []
    for perfil in (dados.get("deliveryProfiles") or {}).get("nodes") or []:
        for grupo in perfil.get("profileLocationGroups") or []:
            for zona in (grupo.get("locationGroupZones") or {}).get("nodes") or []:
                metodos = (zona.get("methodDefinitions") or {}).get("nodes") or []
                if any(((m.get("rateProvider") or {}).get("carrierService") or {}).get("id")
                       == servico_id and m.get("active") for m in metodos):
                    nome_zona = (zona.get("zone") or {}).get("name", "")
                    zonas.append(f"{perfil.get('name', '')} / {nome_zona}")
    return {"zonas": zonas, "erro": erro}


def verificar(configuracao, progresso):
    cliente = ShopifyClient(configuracao)
    try:
        url = url_de_cotacao(configuracao)
    except ValueError as erro:
        url, erro_url = "", str(erro)
    else:
        erro_url = ""
    progresso(0, 5, "Conferindo escopos e plano")
    resultado = {"escopos": _escopos(cliente), "plano": _plano(cliente)}
    progresso(2, 5, "Conferindo o cadastro do frete")
    resultado["servico"] = {**_servico(cliente, url), "erro_url": erro_url}
    progresso(3, 5, "Conferindo locais e zonas de envio")
    resultado["locais"] = _locais(cliente)
    servico_id = resultado["servico"]["id"]
    resultado["zonas"] = (_zonas_com_o_servico(cliente, servico_id) if servico_id
                          else {"zonas": [], "erro": ""})
    resultado["verificado_em"] = timezone.now().isoformat()
    ExternalReference.all_objects.update_or_create(
        account_id=configuracao.account_id, platform=Origin.SHOPIFY, entity_type=ENTIDADE,
        object_id=str(configuracao.pk),
        defaults={"external_id": str(configuracao.uuid), "metadata": resultado,
                  "origin": Origin.SHOPIFY})
    progresso(5, 5, "Verificacao concluida")
    return "Verificacao do frete no checkout concluida; veja o checklist em Integracoes > Shopify."
