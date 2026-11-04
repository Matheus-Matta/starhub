"""Token que o tema da loja gera no Liquid para dizer quem esta avaliando.

Sem app de vitrine, o hub nao ve a sessao do cliente na Shopify. O Liquid roda no
servidor da Shopify e assina os ids, a data e o nome da conta com o filtro hmac_sha256
(hex) e um segredo das configuracoes do tema; o HTML so leva a assinatura:

    {%- assign ts = 'now' | date: '%s' -%}
    {%- assign nome = customer.first_name | default: '' | url_encode -%}
    {%- assign sobrenome = customer.last_name | default: '' | url_encode -%}
    {%- capture payload -%}
      {{- customer.id -}}:{{ product.id }}:{{ ts }}:{{ nome }}:{{ sobrenome -}}
    {%- endcapture -%}
    data-payload="{{ payload }}" data-sig="{{ payload | hmac_sha256: settings.reviews_secret }}"

O hub recalcula com o mesmo segredo (ConfiguracaoIntegracao.segredo_avaliacoes).
Token vazado vale so para aquele cliente e produto e so ate expirar.
O formato antigo, sem nome e sobrenome, continua aceito durante a troca do tema.
"""

import hashlib
import hmac
import time
from urllib.parse import unquote

VALIDADE = 2 * 60 * 60  # segundos: a pagina aberta ha mais tempo pede recarregar
# Relogio do hub um pouco atras do da Shopify nao pode recusar um token recem-gerado.
FOLGA_FUTURO = 5 * 60


class TokenInvalido(Exception):
    pass


def assinar(segredo, payload):
    return hmac.new(segredo.encode(), payload.encode(), hashlib.sha256).hexdigest()


def conferir(segredo, payload, assinatura, agora=None):
    """Ids e nome da conta na Shopify; nome/sobrenome sao None no token antigo."""
    if not segredo:
        raise TokenInvalido(
            "As avaliacoes nao estao configuradas no hub: falta o segredo das avaliacoes."
        )
    payload = str(payload or "")
    esperado = assinar(segredo, payload)
    if not hmac.compare_digest(esperado, str(assinatura or "").strip().lower()):
        raise TokenInvalido("Assinatura invalida. Recarregue a pagina e envie de novo.")
    partes = payload.split(":")
    if len(partes) not in (3, 5) or not all(parte.isdigit() for parte in partes[:3]):
        raise TokenInvalido("Token fora do formato cliente:produto:data:nome:sobrenome.")
    cliente_id, produto_id, carimbo = partes[:3]
    agora = time.time() if agora is None else agora
    idade = agora - int(carimbo)
    if idade > VALIDADE or idade < -FOLGA_FUTURO:
        raise TokenInvalido("A pagina expirou. Recarregue a pagina e envie de novo.")
    if len(partes) == 3:
        return cliente_id, produto_id, None, None
    return cliente_id, produto_id, unquote(partes[3]), unquote(partes[4])
