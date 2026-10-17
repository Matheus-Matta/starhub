"""Enderecos publicos exibidos na configuracao da integracao Shopify."""

from urllib.parse import urljoin

from django.urls import reverse


def adicionar_links_publicos(form, configuracao, endereco_atual):
    # O admin pode estar em localhost; a URL publica dos webhooks fornece o host
    # que o tema da loja realmente consegue acessar.
    base = configuracao.url_webhook or endereco_atual
    avaliacoes = urljoin(base, reverse("shopify_avaliacoes", args=[configuracao.pk]))
    form.fields["segredo_avaliacoes"].help_text += f" Endereco para o tema: {avaliacoes}"
    frete = urljoin(base, reverse("shopify_frete_publico", args=[configuracao.uuid]))
    form.fields["dominio_loja"].help_text += (
        " Dominios proprios usam os cadastrados na conta. "
        f"Link de consulta: {frete}?cep=24325-300"
    )
