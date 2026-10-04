"""Webhook REST customers/create|update -> o formato da busca GraphQL.

Assim importar_cliente le um formato so. Chave que o webhook nao trouxe fica de
fora (e o hub nao mexe naquele campo): o payload da doc 2026-07 nao traz
orders_count, total_spent, tags, locale nem email_marketing_consent, mas lojas
em versao antiga trazem, e entao eles valem.
"""


def _endereco(item):
    return {
        "id": item.get("admin_graphql_api_id") or item.get("id"),
        "firstName": item.get("first_name"), "lastName": item.get("last_name"),
        "company": item.get("company"), "address1": item.get("address1"),
        "address2": item.get("address2"), "city": item.get("city"),
        "province": item.get("province"), "provinceCode": item.get("province_code"),
        "zip": item.get("zip"), "country": item.get("country"),
        "countryCodeV2": item.get("country_code"), "phone": item.get("phone"),
    }


def _marketing(dados):
    consentimento = dados.get("email_marketing_consent")
    if isinstance(consentimento, dict) and consentimento.get("state"):
        return str(consentimento["state"]).upper()
    if "accepts_marketing" in dados:  # campo antigo do REST
        return "SUBSCRIBED" if dados["accepts_marketing"] else "NOT_SUBSCRIBED"
    return None


def _tags(texto):
    if isinstance(texto, list):
        return texto
    return [tag.strip() for tag in str(texto or "").split(",") if tag.strip()]


def de_webhook(dados, externo_id):
    saida = {"id": externo_id}
    for rest, graphql in (("first_name", "firstName"), ("last_name", "lastName"),
                          ("phone", "phone"), ("note", "note"), ("locale", "locale"),
                          ("tax_exempt", "taxExempt"), ("created_at", "createdAt"),
                          ("state", "state"), ("orders_count", "numberOfOrders")):
        if rest in dados:
            saida[graphql] = dados[rest]
    if "email" in dados:
        saida["email"] = dados["email"]
    estado = _marketing(dados)
    if estado:
        saida["defaultEmailAddress"] = {"emailAddress": dados.get("email") or "",
                                        "marketingState": estado}
    if "tags" in dados:
        saida["tags"] = _tags(dados["tags"])
    if dados.get("total_spent") is not None:
        saida["amountSpent"] = {"amount": dados["total_spent"],
                                "currencyCode": dados.get("currency") or ""}
    if "addresses" in dados:
        saida["addressesV2"] = {"nodes": [_endereco(item) for item in dados["addresses"] or []]}
    if "default_address" in dados:
        padrao = dados["default_address"]
        saida["defaultAddress"] = _endereco(padrao) if padrao else None
    return saida
