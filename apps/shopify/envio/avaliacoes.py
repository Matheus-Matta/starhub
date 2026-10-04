"""Avaliacao do hub -> metaobject avaliacao_produto na loja Shopify.

So a APROVADA fica na loja. Pendente nao sai; rejeitada (ou excluida no hub) que
ja estava publicada sai da loja, com as fotos. Depois de cada mudanca a media, o
total e a lista do produto sao recalculados (avaliacoes_loja.atualizar_produto).

O metaobject e gravado com metaobjectUpsert pelo handle "avaliacao-<uuid>": envio
repetido (retry, dois workers) atualiza o mesmo, nunca cria outro.
"""

import json

from django.utils import timezone

from apps.core.models import ExternalReference
from apps.loja.models import Avaliacao
from apps.shopify import consultas_avaliacoes as q
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio import avaliacoes_loja as loja
from apps.shopify.envio.base import RecursoShopify


class AvaliacaoShopify(RecursoShopify):
    recurso = "avaliacoes"
    modelo = Avaliacao

    def enviar(self, operacao, pk):
        if operacao == "delete":
            return self._retirar(pk, "excluido")
        avaliacao = self._carregar(pk)
        if avaliacao is None:
            return "ignorado: o registro nao existe mais no hub"
        if avaliacao.status != Avaliacao.Status.APROVADA:
            return self._retirar(pk, "retirada da loja")
        if (not self.referencia(pk) and operacao != "create"
                and not self.marketplace.habilitado(self.recurso, "create")):
            return ("ignorado: a avaliacao ainda nao esta na loja e 'criar' esta desligado; "
                    "ligue Enviar > Avaliacoes > Criar.")
        gid = self.publicar(avaliacao)
        return f"publicada {gid}"

    def _produto_gid(self, produto_id):
        gid = ExternalReference.all_objects.filter(
            account_id=self.configuracao.account_id, platform=self.plataforma,
            entity_type="produtos", object_id=str(produto_id),
        ).values_list("external_id", flat=True).first()
        if not gid:
            raise ShopifyErro(
                f"O produto {produto_id} nao esta ligado a um produto da loja; "
                "sincronize os produtos e envie a avaliacao de novo."
            )
        return gid

    def publicar(self, avaliacao):
        loja.preparar_loja(self)
        produto_gid = self._produto_gid(avaliacao.produto_id)
        campos = {
            "product": produto_gid,
            "author": avaliacao.nome_publico,
            "rating": str(avaliacao.nota),
            "body": avaliacao.comentario,
            "verified": "true" if avaliacao.compra_verificada else "false",
            "date": timezone.localdate(avaliacao.created_at).isoformat(),
        }
        fotos = loja.enviar_fotos(self, avaliacao)
        if fotos:
            campos["photos"] = json.dumps(fotos)
        dados = self.mutacao(q.UPSERT, {
            "handle": {"type": q.TIPO, "handle": f"avaliacao-{avaliacao.uuid}"},
            "metaobject": {
                "fields": [{"key": chave, "value": valor} for chave, valor in campos.items()],
                "capabilities": {"publishable": {"status": "ACTIVE"}},
            },
        }, "metaobjectUpsert")
        gid = dados["metaobject"]["id"]
        ExternalReference.all_objects.update_or_create(
            account_id=self.configuracao.account_id, platform=self.plataforma,
            entity_type=self.recurso, object_id=str(avaliacao.pk),
            defaults={"external_id": gid, "external_parent_id": produto_gid,
                      "origin": self.plataforma},
        )
        loja.atualizar_produto(self, avaliacao.produto_id, produto_gid)
        # update(): so a data; o save dispararia outro envio desta mesma avaliacao.
        Avaliacao.all_objects.filter(pk=avaliacao.pk).update(publicada_em=timezone.now())
        return gid

    def _retirar(self, pk, feito):
        referencia = self._referencias().filter(object_id=str(pk)).first()
        if referencia is None:
            return "ignorado: avaliacao nao aprovada nao vai para a loja"
        self.mutacao(q.EXCLUIR, {"id": referencia.external_id}, "metaobjectDelete")
        loja.apagar_fotos(self, int(pk))
        produto_gid = referencia.external_parent_id
        referencia.delete()
        Avaliacao.all_objects.filter(pk=pk).update(publicada_em=None)
        produto_id = ExternalReference.all_objects.filter(
            account_id=self.configuracao.account_id, platform=self.plataforma,
            entity_type="produtos", external_id=produto_gid,
        ).values_list("object_id", flat=True).first()
        loja.atualizar_produto(self, produto_id, produto_gid)
        return feito
