"""Normaliza e aplica os webhooks recebidos do Shopify."""

from apps.shopify.atualizar import ATUALIZADORES
from apps.shopify.clientes_webhook import de_webhook
from apps.shopify.cupons import buscar_desconto
from apps.shopify.produtos_busca import buscar_produto
from apps.shopify.recursos import SINCRONIZADORES, desativar

TIPOS_GID = {
    "produtos": "Product",
    "categorias": "Collection",
    "clientes": "Customer",
    "pedidos": "Order",
    "cupons": "DiscountCodeNode",
    "estoque": "ProductVariant",
    "imagens": "ProductImage",
}


def _gid(recurso, id_):
    texto = str(id_ or "")
    if texto.startswith("gid://"):
        return texto
    return f"gid://shopify/{TIPOS_GID[recurso]}/{texto}"


def _normalizar(recurso, dados):
    externo_id = dados.get("admin_graphql_api_id") or dados.get("id")
    if recurso == "pedidos":
        # Pedido segue no formato REST do webhook: importar_pedido le esse formato.
        return dict(dados)
    normalizado = {**dados, "id": _gid(recurso, externo_id)}
    if recurso == "produtos":
        # O corpo REST nao traz SEO nem colecoes: com a loja no contexto, o produto
        # vem inteiro pela GraphQL; sem ela (ou se ja sumiu da loja), fica o corpo.
        completo = buscar_produto(normalizado["id"])
        if completo:
            return completo
        opcoes = sorted(dados.get("options") or [], key=lambda item: item.get("position", 0))
        normalizado["variants"] = {"nodes": [
            {
                "id": _gid("estoque", item.get("admin_graphql_api_id") or item.get("id")),
                "title": item.get("title"),
                "sku": item.get("sku", ""),
                "barcode": item.get("barcode"),
                "price": item.get("price"),
                "compareAtPrice": item.get("compare_at_price"),
                "inventoryQuantity": item.get("inventory_quantity"),
                "inventoryPolicy": item.get("inventory_policy"),
                "inventoryManagement": item.get("inventory_management", True),
                "taxable": item.get("taxable", True),
                "requiresShipping": item.get("requires_shipping", True),
                "position": item.get("position"),
                "selectedOptions": [
                    {"name": opcao.get("name"), "value": item.get(f"option{indice}")}
                    for indice, opcao in enumerate(opcoes, start=1)
                    if item.get(f"option{indice}") is not None
                ],
            }
            for item in dados.get("variants", [])
        ]}
        normalizado["images"] = [
            {
                "id": _gid("imagens", item.get("admin_graphql_api_id") or item.get("id")),
                "src": item.get("src") or item.get("url"),
                "alt": item.get("alt") or item.get("altText"),
                "variantIds": [
                    _gid("estoque", variante_id) for variante_id in item.get("variant_ids", [])
                ],
            }
            for item in dados.get("images", [])
        ]
        normalizado["bodyHtml"] = dados.get("body_html", "")
    elif recurso == "clientes":
        return de_webhook(dados, normalizado["id"])
    elif recurso == "categorias":
        normalizado.update({
            "descriptionHtml": dados.get("body_html", ""),
            "image": dados.get("image"),
        })
    elif recurso == "cupons":
        # O corpo do webhook de desconto nao traz codigo, valor nem regras: com a
        # loja no contexto, busca o desconto completo; sem ela, fica o basico.
        completo = buscar_desconto(normalizado["id"])
        if completo:
            return completo
        normalizado["codeDiscount"] = {
            "title": dados.get("title") or dados.get("code"),
            "status": dados.get("status"),
            "codes": {"nodes": [{"code": dados.get("code", "")}]},
        }
    return normalizado


def processar_webhook(configuracao, recurso, operacao, dados, progresso):
    progresso(0, 1, f"Webhook {recurso}: {operacao}")
    if operacao == "delete":
        externo_id = dados.get("admin_graphql_api_id") or dados.get("id")
        alterou = desativar(recurso, _gid(recurso, externo_id))
        mensagem = "Registro desativado." if alterou else "Registro ja nao existia."
    elif operacao == "update":
        normalizado = _normalizar(recurso, dados)
        obj, alterou = ATUALIZADORES[recurso](normalizado)
        if alterou:
            mensagem = "Registro atualizado."
        elif configuracao and configuracao.habilitado("receber", recurso, "create"):
            obj, criado = SINCRONIZADORES[recurso](normalizado)
            if obj is None:
                mensagem = "Registro nao encontrado."
            elif criado:
                mensagem = "Registro criado a partir da atualizacao."
            else:
                mensagem = "Registro vinculado a partir da atualizacao."
        else:
            mensagem = "Registro nao encontrado."
    else:
        _obj, criado = SINCRONIZADORES[recurso](_normalizar(recurso, dados))
        mensagem = "Registro criado." if criado else "Registro ja existia."
    progresso(1, 1, "Webhook processado")
    return mensagem
