"""O mesmo cliente do Shopify nos dois formatos: busca GraphQL e webhook REST."""

GID = "gid://shopify/Customer/7001"


def _endereco_graphql(id_, rua, numero, bairro, cep, nome="Ana"):
    return {
        "id": f"gid://shopify/MailingAddress/{id_}?model_name=CustomerAddress",
        "firstName": nome, "lastName": "Souza", "company": "Ana ME",
        "address1": f"{rua}, {numero}", "address2": f"Apto 1, {bairro}",
        "city": "Recife", "province": "Pernambuco", "provinceCode": "PE",
        "zip": cep, "country": "Brazil", "countryCodeV2": "BR", "phone": "+5581999990000",
    }


def graphql(**extra):
    casa = _endereco_graphql(11, "Rua das Flores", "100", "Boa Vista", "50030-230")
    trabalho = _endereco_graphql(12, "Av. Norte", "55", "Casa Amarela", "52070-000")
    dados = {
        "id": GID, "firstName": "Ana", "lastName": "Souza",
        "defaultEmailAddress": {"emailAddress": "ana@exemplo.com", "marketingState": "SUBSCRIBED"},
        "defaultPhoneNumber": {"phoneNumber": "+5581988887777"},
        "note": "Cliente VIP", "tags": ["vip", "atacado"], "locale": "pt-BR",
        "state": "ENABLED", "taxExempt": False, "createdAt": "2024-03-10T12:00:00Z",
        "numberOfOrders": "3", "amountSpent": {"amount": "250.40", "currencyCode": "BRL"},
        "defaultAddress": trabalho,
        "addressesV2": {"nodes": [casa, trabalho], "pageInfo": {"hasNextPage": False}},
    }
    dados.update(extra)
    return dados


def _endereco_rest(id_, rua, numero, bairro, cep, padrao=False):
    return {
        "id": id_, "customer_id": 7001, "first_name": "Ana", "last_name": "Souza",
        "company": "Ana ME", "address1": f"{rua}, {numero}", "address2": f"Apto 1, {bairro}",
        "city": "Recife", "province": "Pernambuco", "province_code": "PE", "zip": cep,
        "country": "Brazil", "country_code": "BR", "phone": "+5581999990000",
        "default": padrao,
    }


def rest(**extra):
    casa = _endereco_rest(11, "Rua das Flores", "100", "Boa Vista", "50030-230")
    trabalho = _endereco_rest(12, "Av. Norte", "55", "Casa Amarela", "52070-000", padrao=True)
    dados = {
        "id": 7001, "admin_graphql_api_id": GID, "email": "ana@exemplo.com",
        "first_name": "Ana", "last_name": "Souza", "phone": "+5581988887777",
        "note": "Cliente VIP", "tags": "vip, atacado", "locale": "pt-BR", "state": "enabled",
        "tax_exempt": False, "created_at": "2024-03-10T09:00:00-03:00",
        "orders_count": 3, "total_spent": "250.40", "currency": "BRL",
        "email_marketing_consent": {"state": "subscribed", "opt_in_level": "single_opt_in"},
        "addresses": [casa, trabalho], "default_address": trabalho,
    }
    dados.update(extra)
    return dados
