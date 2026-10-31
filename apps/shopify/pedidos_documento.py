"""CPF/CNPJ do checkout brasileiro do Shopify.

O checkout guarda o documento em Order.localizationExtensions (purpose TAX,
countryCode BR), que nem o webhook orders/create nem a pagina da sincronizacao
trazem: sem buscar, o pedido chegava ao ERP sem CPF e ele nao conseguia
cadastrar o cliente. A consulta e a que ja funcionava no fluxo antigo (n8n), na
versao 2024-01 da API: localizationExtensions e da API antiga, e a versao da
configuracao (2026-07) e usada para todo o resto.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.loja.models import Cliente
from apps.shopify.cliente import ShopifyClient, ShopifyErro
from apps.shopify.contexto import avisar, configuracao_atual

VERSAO_DOCUMENTO = "2024-01"
CHAVE = "localization_extensions"
CONSULTA_DOCUMENTO = """
  query ($id: ID!) { order(id: $id) { id name
    localizationExtensions(first: 10) { nodes { purpose countryCode title value } } } }
"""


def documento_localizado(dados):
    for campo in dados.get(CHAVE) or []:
        e_documento = campo.get("purpose") == "TAX" and campo.get("countryCode") in ("BR", None)
        if e_documento and str(campo.get("value") or "").strip():
            return str(campo["value"]).strip()
    return ""


def completar_documento(dados):
    """Le o documento do checkout pela GraphQL; sem loja no contexto nao consulta.

    Falha do Shopify vira aviso na tarefa e o pedido entra sem documento: perder o
    pedido inteiro por causa do CPF seria pior que o ERP pedir o CPF depois.
    """
    configuracao = configuracao_atual()
    gid = dados.get("admin_graphql_api_id")
    if configuracao is None or not gid or CHAVE in dados:
        return dados
    try:
        resposta = ShopifyClient(configuracao, versao=VERSAO_DOCUMENTO).graphql(
            CONSULTA_DOCUMENTO, {"id": gid})
    except ShopifyErro as erro:
        avisar(f"CPF/CNPJ do checkout nao lido: {erro}. Reprocesse o webhook depois.",
               recurso="pedidos", descricao=str(dados.get("name") or ""), id_externo=gid)
        return dados
    extensoes = ((resposta or {}).get("order") or {}).get("localizationExtensions") or {}
    return {**dados, CHAVE: extensoes.get("nodes") or []}


def gravar_documento_do_cliente(cliente, doc, pedido_nome=""):
    """Leva o CPF/CNPJ do checkout ao cadastro do cliente, so se o cadastro nao tem.

    Documento ja preenchido fica: o operador pode ter corrigido. CPF de outro
    cliente (indice unico) ou invalido vira aviso; o pedido segue com o CPF dele.
    """
    campo = {11: "cpf", 14: "cnpj"}.get(len(doc or ""))
    if cliente is None or campo is None:
        return
    # Lock e releitura: dois pedidos do mesmo cliente chegam juntos no webhook.
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
    if getattr(cliente, campo):
        return
    setattr(cliente, campo, doc)
    cliente.tipo_documento = cliente.tipo_documento or campo
    try:
        with transaction.atomic():
            cliente.save(update_fields=[campo, "tipo_documento", "updated_at"])
    except IntegrityError:
        avisar(f"{campo.upper()} {doc} do pedido {pedido_nome} ja e de outro cliente; "
               "o cadastro deste ficou sem documento. Junte os cadastros se for a mesma pessoa.",
               recurso="clientes", id=cliente.pk, descricao=cliente.email)
    except ValidationError as erro:
        avisar(f"{campo.upper()} do pedido {pedido_nome} nao gravado no cliente: "
               f"{'; '.join(erro.messages)}", recurso="clientes", id=cliente.pk,
               descricao=cliente.email)
