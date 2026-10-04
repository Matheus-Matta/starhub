"""Apoio do envio de avaliacoes: definicoes na loja, fotos e media do produto.

A media e a contagem sao recalculadas do HUB (fonte da verdade) a cada envio, com
as avaliacoes aprovadas que ja estao na loja; somar +1/-1 na loja erraria no
primeiro envio repetido.
"""

import json
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from apps.core.models import ExternalReference
from apps.loja.models import Avaliacao, Produto
from apps.loja.services.midias_avaliacao import e_video
from apps.shopify import consultas_avaliacoes as q
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio import avaliacoes_video
from apps.shopify.midias import url_publica

FOTOS = "foto_avaliacao"
NAMESPACE = "custom"
# Lista que o tema percorre na pagina do produto: as mais novas primeiro. O resto
# continua contando na media e no total.
LISTA_MAXIMO = 50


def _referencias(enviador, entidade):
    return ExternalReference.all_objects.filter(
        account_id=enviador.configuracao.account_id, platform=enviador.plataforma,
        entity_type=entidade,
    )


def definicao_avaliacao(enviador):
    """Id da definicao avaliacao_produto na loja; cria na primeira vez."""
    dados = enviador.cliente.graphql(q.DEFINICAO_POR_TIPO, {"type": q.TIPO}) or {}
    existente = (dados.get("metaobjectDefinitionByType") or {}).get("id")
    if existente:
        return existente
    criada = enviador.mutacao(q.CRIAR_DEFINICAO, {"definition": q.definicao()},
                              "metaobjectDefinitionCreate")
    return criada["metaobjectDefinition"]["id"]


def _definicao_metafield(enviador, chave, nome, tipo, validacoes=()):
    dados = enviador.cliente.graphql(
        q.DEFINICAO_METAFIELD, {"namespace": NAMESPACE, "key": chave}) or {}
    if (dados.get("metafieldDefinitions") or {}).get("nodes"):
        return
    enviador.mutacao(q.CRIAR_DEFINICAO_METAFIELD, {"definition": {
        "name": nome, "namespace": NAMESPACE, "key": chave, "ownerType": "PRODUCT",
        "type": tipo, "validations": list(validacoes),
        "access": {"storefront": "PUBLIC_READ"},
    }}, "metafieldDefinitionCreate")


def preparar_loja(enviador):
    """Definicoes do metaobject e dos metafields do produto, uma vez por enviador."""
    if getattr(enviador, "_loja_pronta", False):
        return
    definicao = definicao_avaliacao(enviador)
    # Lista de metaobject so existe com definicao que diz o tipo do metaobject.
    _definicao_metafield(enviador, "reviews", "Avaliacoes", "list.metaobject_reference",
                         [{"name": "metaobject_definition_id", "value": definicao}])
    _definicao_metafield(enviador, "rating_value", "Nota media", "number_decimal")
    _definicao_metafield(enviador, "review_count", "Total de avaliacoes", "number_integer")
    enviador._loja_pronta = True


def enviar_fotos(enviador, avaliacao):
    """Gids das fotos na loja (Files), na ordem; envia so as que ainda nao foram."""
    ligadas = dict(_referencias(enviador, FOTOS).filter(
        object_id__in=[str(f.pk) for f in avaliacao.fotos.all()]
    ).values_list("object_id", "external_id"))
    gids = []
    for foto in avaliacao.fotos.all():
        if str(foto.pk) not in ligadas:
            ligadas[str(foto.pk)] = _criar_arquivo(enviador, avaliacao, foto)
            ExternalReference.all_objects.create(
                account_id=avaliacao.account_id, platform=enviador.plataforma,
                entity_type=FOTOS, object_id=str(foto.pk),
                external_id=ligadas[str(foto.pk)], origin=enviador.plataforma,
                metadata={"avaliacao_id": avaliacao.pk},
            )
        gids.append(ligadas[str(foto.pk)])
    return gids


def _criar_arquivo(enviador, avaliacao, foto):
    if e_video(foto.imagem.name):
        return avaliacoes_video.criar(
            enviador, foto, f"Video da avaliacao de {avaliacao.nome_publico}")
    url = url_publica(enviador.configuracao, foto.imagem.url)
    if not url:
        raise ShopifyErro(
            "A Shopify precisa baixar as fotos da avaliacao e o hub nao tem URL "
            "publica: preencha a URL dos webhooks em Integracoes > Shopify."
        )
    criados = enviador.mutacao(q.CRIAR_ARQUIVOS, {"files": [{
        "originalSource": url, "contentType": "IMAGE",
        "alt": f"Foto da avaliacao de {avaliacao.nome_publico}",
    }]}, "fileCreate")
    return criados["files"][0]["id"]


def apagar_fotos(enviador, avaliacao_id):
    referencias = _referencias(enviador, FOTOS).filter(metadata__avaliacao_id=avaliacao_id)
    gids = list(referencias.values_list("external_id", flat=True))
    if gids:
        enviador.mutacao(q.EXCLUIR_ARQUIVOS, {"fileIds": gids}, "fileDelete")
        referencias.delete()


def _media(notas):
    media = Decimal(sum(notas)) / Decimal(len(notas))
    return str(media.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def atualizar_produto(enviador, produto_id, produto_gid):
    """Grava media, total e lista no produto da loja a partir do que o hub publicou."""
    with transaction.atomic():
        # Lock no produto: duas aprovacoes ao mesmo tempo nao podem gravar uma media
        # calculada antes da outra terminar (a ultima a gravar teria o retrato velho).
        Produto.all_objects.select_for_update().filter(pk=produto_id).first()
        publicadas = dict(_referencias(enviador, "avaliacoes").filter(
            external_parent_id=produto_gid).values_list("object_id", "external_id"))
        aprovadas = list(Avaliacao.all_objects.filter(
            pk__in=publicadas, status=Avaliacao.Status.APROVADA
        ).order_by("-created_at").values_list("pk", "nota"))
        dono = {"ownerId": produto_gid, "namespace": NAMESPACE}
        if not aprovadas:
            enviador.mutacao(q.APAGAR_METAFIELDS, {"metafields": [
                {**dono, "key": chave} for chave in ("reviews", "rating_value", "review_count")
            ]}, "metafieldsDelete")
            return
        lista = [publicadas[str(pk)] for pk, _ in aprovadas[:LISTA_MAXIMO]]
        enviador.mutacao(q.GRAVAR_METAFIELDS, {"metafields": [
            {**dono, "key": "reviews", "type": "list.metaobject_reference",
             "value": json.dumps(lista)},
            {**dono, "key": "rating_value", "type": "number_decimal",
             "value": _media([nota for _, nota in aprovadas])},
            {**dono, "key": "review_count", "type": "number_integer",
             "value": str(len(aprovadas))},
        ]}, "metafieldsSet")
