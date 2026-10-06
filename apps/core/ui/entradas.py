"""Placeholder, mascara e largura de cada campo dos formularios do admin.

O TemaMixin aplica sozinho em todo form; o ModelAdmin so declara o que foge do
padrao (`larguras`). Chave "Model.campo" vale mais que so "campo".

    placeholder: exemplo do que digitar ("00000-000"), nunca o rotulo repetido;
    mascara:     static/starhub/js/mascaras.js (cep, cpf, cnpj, telefone...);
    largura:     colunas numa grade de 12 (padrao 6 = meia linha).
"""

import re

from django import forms
from django.db import models

PLACEHOLDERS = {
    # contato e documentos
    "email": "nome@empresa.com.br", "phone": "(00) 00000-0000", "telefone": "(00) 00000-0000",
    "cpf": "000.000.000-00", "cnpj": "00.000.000/0000-00", "document": "CPF ou CNPJ",
    "username": "joao.silva", "usuario": "ana.silva", "legal_name": "Razao social do CNPJ",
    "company": "Nome da empresa", "empresa": "Nome da empresa", "avatar_url": "https://",
    # endereco
    "recipient_name": "Quem recebe a entrega", "address_line_1": "Rua, avenida...",
    "address_line_2": "Bloco, apto, fundos...", "number": "123", "complement": "Apto 12",
    "neighborhood": "Centro", "city": "Recife", "state": "Pernambuco", "state_code": "PE",
    "postal_code": "00000-000", "country": "Brasil", "country_code": "BR",
    "reference": "Perto de...", "latitude": "-8.0476", "longitude": "-34.8770",
    # conta
    "Account.name": "Minha Loja", "slug": "gerado a partir do nome",
    "Account.dominio_avaliacoes": "minhaloja.com.br",
    "timezone": "America/Sao_Paulo", "currency": "BRL", "moeda": "BRL", "locale": "pt-BR",
    "AccessProfile.name": "Operador de pedidos", "code": "operador",
    "Address.name": "Casa, Trabalho...", "SalesChannel.name": "Shopify Loja Principal",
    "PublicationPolicy.name": "Produtos para a Shopify", "priority": "0 = primeiro",
    # integracao
    "entity_type": "product", "object_id": "123", "external_id": "gid://shopify/Product/123",
    "external_parent_id": "id do pai na plataforma", "external_store_id": "id da loja",
    "last_error": "Mensagem do ultimo erro", "payload_hash": "sha256 do conteudo enviado",
    "ConfiguracaoIntegracao.nome": "Shopify principal",
    "dominio_loja": "sua-loja.myshopify.com", "versao_api": "2026-07",
    "url_webhook": "https://hub.exemplo.com/integracoes/shopify/webhook",
    "motivo_rejeicao": "Ex.: fala de outro produto",
    # logistica
    "TabelaFrete.nome": "Entrega propria Grande SP", "cep_origem": "00000-000",
    "cep_inicial": "00000-000", "cep_final": "00000-000",
    "ChaveApi.descricao": "ERP da loja",
    # catalogo
    "Produto.nome": "Camiseta basica azul", "Categoria.nome": "Camisetas", "Tag.nome": "Promocao",
    "TipoVariante.nome": "Cor", "valor": "Preto", "titulo": "Preto / M", "sku": "CAM-AZUL-M",
    "barcode": "7891234567895", "fornecedor": "Nome do fornecedor", "marca": "Marca",
    "descricao": "Texto exibido na loja", "descricao_curta": "Resumo perto do preco",
    "seo_titulo": "Titulo para o Google", "seo_descricao": "Descricao para o Google",
    "url_externa": "https://", "texto_botao": "Comprar", "id_pai": "0 = sem pai",
    "nota_compra": "Mensagem enviada depois da compra", "weight_unit": "kg",
    "tax_class": "padrao", "shipping_class": "volumoso", "alt_text": "Descreva a imagem",
    "url": "https://", "low_stock_amount": "5", "posicao": "0", "ordem": "0",
    "ordem_menu": "0", "inventory_quantity": "0",
    # cupom
    "Cupom.name": "Black Friday", "Cupom.value": "10.00",
    "Cupom.description": "Uso interno", "usage_limit": "sem limite",
    "usage_limit_per_customer": "sem limite", "minimum_subtotal": "0.00",
    "minimum_quantity": "1",
    # cliente e pedido
    "Cliente.nome": "Ana", "sobrenome": "Silva", "papel": "customer",
    "notas": "Observacoes internas", "observacao_cliente": "Recado do cliente",
    "Pedido.number": "SH-0001", "external_number": "#1001 na plataforma",
    "forma_pagamento": "pix", "forma_pagamento_titulo": "Pix", "shipping_method": "Sedex",
    "source_name": "rest-api", "source_reference": "id do pedido na origem",
    "ItemPedido.nome": "Nome do produto vendido", "quantidade": "1", "quantity": "1",
    "ItemPedido.subtotal": "calculado pelo preco", "ItemPedido.total": "calculado pelo preco",
    "provider": "mercado_pago", "transaction_id": "id na operadora", "installments": "1",
    "tracking_company": "Correios", "tracking_number": "AA123456789BR", "tracking_url": "https://",
}
POR_TIPO = [
    (models.URLField, "https://"), (models.EmailField, "nome@empresa.com.br"),
    (models.DecimalField, "0.00"), (models.IntegerField, "0"),
    (models.CharField, None), (models.TextField, None),
]
MASCARAS = {
    "cpf": "cpf", "cnpj": "cnpj", "document": "cpf-cnpj", "postal_code": "cep",
    "phone": "telefone", "telefone": "telefone", "state_code": "uf", "country_code": "pais",
    "barcode": "digitos", "currency": "moeda", "moeda": "moeda",
    "cep_origem": "cep", "cep_inicial": "cep", "cep_final": "cep",
}
LARGURAS = {
    "postal_code": 3, "number": 2, "state_code": 2, "country_code": 2, "currency": 3,
    "moeda": 3, "weight_unit": 3, "installments": 3, "posicao": 3,
}
# Gravados so com digitos: com a mascara o texto nao cabe no max_length (CPF = 11,
# CEP = 8).
SO_DIGITOS = {"cpf", "cnpj", "cep_origem", "cep_inicial", "cep_final"}


class CampoSoDigitos(forms.CharField):
    """Aceita "123.456.789-09" na tela e entrega "12345678909" ao model."""

    def to_python(self, value):
        return re.sub(r"\D", "", super().to_python(value) or "")


def _chave(mapa, db_field):
    return mapa.get(f"{db_field.model.__name__}.{db_field.name}", mapa.get(db_field.name))


def form_class(db_field):
    return CampoSoDigitos if db_field.name in SO_DIGITOS else None


def preparar(db_field, campo, larguras):
    """Poe placeholder, mascara e largura no widget do campo (atributos data-*)."""
    widget = getattr(campo.widget, "widget", campo.widget)  # FK vem embrulhada
    attrs = widget.attrs
    placeholder = _chave(PLACEHOLDERS, db_field)
    if placeholder is None:
        placeholder = next((t for tipo, t in POR_TIPO if isinstance(db_field, tipo)), None)
    if placeholder and "placeholder" not in attrs:
        attrs["placeholder"] = placeholder
    mascara = _chave(MASCARAS, db_field)
    if mascara:
        attrs["data-mascara"] = mascara
        if mascara not in ("uf", "pais", "moeda"):
            attrs["inputmode"] = "numeric"
    # No form field (nao no widget): FK vem embrulhada e o template le daqui.
    campo.colunas = larguras.get(db_field.name) or _chave(LARGURAS, db_field)
    return campo
