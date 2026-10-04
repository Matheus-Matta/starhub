from django.urls import path

from apps.shopify.avaliacoes_api import AvaliacaoView
from apps.shopify.frete_api import cotar_frete
from apps.shopify.views import webhook

urlpatterns = [
    # uuid no webhook: o id inteiro deixaria testar as lojas em sequencia (1, 2, 3...).
    path("avaliacoes/<int:configuracao_id>/", AvaliacaoView.as_view(), name="shopify_avaliacoes"),
    path("webhook/<uuid:configuracao_uuid>/<str:recurso>/", webhook, name="webhook"),
    # Cotacao de frete do checkout (CarrierService): a Shopify chama a cada CEP digitado.
    path("frete/<uuid:configuracao_uuid>/", cotar_frete, name="shopify_frete"),
    # Endereco antigo, com o id: webhooks ja cadastrados na Shopify continuam chegando ate
    # o operador recadastrar (o recadastro troca pelo de uuid).
    path("webhook/<int:configuracao_id>/<str:recurso>/", webhook, name="webhook_legado"),
]
