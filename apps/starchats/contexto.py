from decimal import Decimal


def _texto_data(valor):
    return valor.isoformat() if valor else ""


def dados_cliente(cliente):
    return {
        "id": cliente.pk,
        "uuid": str(cliente.uuid),
        "nome": cliente.nome,
        "sobrenome": cliente.sobrenome,
        "nome_completo": cliente.nome_completo,
        "email": cliente.email,
        "telefone": cliente.telefone,
        "cpf": cliente.cpf,
        "cnpj": cliente.cnpj,
        "empresa": cliente.empresa,
        "nascimento": _texto_data(cliente.nascimento),
        "aceita_marketing": cliente.aceita_marketing,
        "cliente_pagante": cliente.cliente_pagante,
        "idioma": cliente.locale,
    }


def dados_pedido(pedido):
    if pedido is None:
        return {}
    return {
        "id": pedido.pk,
        "uuid": str(pedido.uuid),
        "numero": pedido.number,
        "status": pedido.status,
        "status_nome": pedido.get_status_display(),
        "status_pagamento": pedido.financial_status,
        "status_entrega": pedido.fulfillment_status,
        "total": pedido.total,
        "subtotal": pedido.subtotal,
        "frete": pedido.total_frete,
        "desconto": pedido.total_desconto,
        "forma_pagamento": pedido.forma_pagamento_titulo or pedido.forma_pagamento,
        "metodo_envio": pedido.shipping_method,
        "canal_origem": pedido.source_name,
    }


def montar(cliente, pedido=None):
    return {"cliente": dados_cliente(cliente), "pedido": dados_pedido(pedido)}


def resolver(contexto, caminho):
    valor = contexto
    for parte in caminho.split("."):
        valor = valor.get(parte) if isinstance(valor, dict) else None
    return valor


def para_texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, Decimal):
        return f"{valor:.2f}"
    return str(valor)
