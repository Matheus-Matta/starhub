"""Avaliacoes enviadas pelo tema da loja Shopify (cliente logado na vitrine).

    POST /integracoes/shopify/avaliacoes/<id da configuracao>/   (multipart)
        payload, sig, nota, comentario, fotos (ate 3)
        201 criada (pendente) | 400 entrada errada | 401 token | 404 produto
        409 ja avaliou, produto fechado ou cliente que o hub ainda nao conhece
    GET  /integracoes/shopify/avaliacoes/<id da configuracao>/?payload=...&sig=...
        200 {"avaliou": true, "status": "pendente"}: o tema esconde o formulario
        (rejeitada ou excluida no hub nao conta: o cliente pode avaliar de novo)

O token diz quem e o cliente e qual o produto (avaliacoes_token.py); nada disso
vem de campo livre. A publicacao na loja e a moderacao ficam fora daqui.
"""

from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.models import ExternalReference, Origin
from apps.core.origem import origem
from apps.core.tenant.context import tenant_context
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Avaliacao, Cliente, Produto
from apps.loja.services.avaliacoes import AvaliacaoConflito, AvaliacaoInvalida, criar_avaliacao
from apps.shopify import avaliacoes_token

ORIGEM = "tema_shopify"


def _erro(status, codigo, mensagem, campo=""):
    corpo = {"erro": codigo, "mensagem": mensagem}
    if campo:
        corpo["campo"] = campo
    return Response(corpo, status=status)


def _registro(modelo, entidade, tipo_gid, external_id):
    gid = f"gid://shopify/{tipo_gid}/{external_id}"
    object_id = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=entidade, external_id=gid
    ).values_list("object_id", flat=True).first()
    return modelo.objects.filter(pk=object_id).first() if object_id else None


class AvaliacaoView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "avaliacoes"

    def get_throttles(self):
        # So o envio: o GET roda a cada pagina de produto aberta pelo cliente logado.
        return [ScopedRateThrottle()] if self.request.method == "POST" else []

    def _contexto(self, configuracao_id, dados):
        """(configuracao, ids da Shopify) ou a Response de erro."""
        configuracao = ConfiguracaoIntegracao.all_objects.filter(
            pk=configuracao_id, plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY,
            active=True,
        ).first()
        if configuracao is None:
            return None, _erro(404, "loja_nao_encontrada", "Loja nao encontrada no hub.")
        try:
            ids = avaliacoes_token.conferir(
                configuracao.segredo_avaliacoes, dados.get("payload"), dados.get("sig")
            )
        except avaliacoes_token.TokenInvalido as erro:
            return None, _erro(401, "token_invalido", str(erro))
        return (configuracao, ids), None

    def get(self, request, configuracao_id):
        contexto, erro = self._contexto(configuracao_id, request.query_params)
        if erro:
            return erro
        configuracao, (cliente_id, produto_id) = contexto
        with tenant_context(configuracao.account_id):
            cliente = _registro(Cliente, "clientes", "Customer", cliente_id)
            produto = _registro(Produto, "produtos", "Product", produto_id)
            # Rejeitada nao conta: o cliente pode avaliar de novo.
            status = Avaliacao.objects.filter(cliente=cliente, produto=produto).exclude(
                status=Avaliacao.Status.REJEITADA
            ).values_list("status", flat=True).first() if cliente and produto else None
        return Response({"avaliou": status is not None, "status": status})

    def post(self, request, configuracao_id):
        contexto, erro = self._contexto(configuracao_id, request.data)
        if erro:
            return erro
        configuracao, (cliente_id, produto_id) = contexto
        fotos = request.FILES.getlist("fotos") or request.FILES.getlist("fotos[]")
        with tenant_context(configuracao.account_id), origem(ORIGEM, via=configuracao.nome):
            produto = _registro(Produto, "produtos", "Product", produto_id)
            if produto is None:
                return _erro(404, "produto_nao_encontrado",
                             "Produto nao encontrado no hub; sincronize os produtos da loja.")
            cliente = _registro(Cliente, "clientes", "Customer", cliente_id)
            if cliente is None:
                return _erro(409, "cliente_nao_sincronizado",
                             "Seu cadastro ainda nao chegou ao hub. Tente de novo em alguns "
                             "minutos.")
            try:
                avaliacao = criar_avaliacao(
                    cliente=cliente, produto=produto, nota=request.data.get("nota"),
                    comentario=request.data.get("comentario"), fotos=fotos,
                    origin=Origin.SHOPIFY,
                )
            except AvaliacaoInvalida as falha:
                return _erro(400, "avaliacao_invalida", str(falha), falha.campo)
            except AvaliacaoConflito as falha:
                return _erro(409, falha.codigo, str(falha))
        return Response({
            "id": avaliacao.pk, "status": avaliacao.status,
            "compra_verificada": avaliacao.compra_verificada,
            "mensagem": "Recebemos sua avaliacao. Ela aparece na loja depois de aprovada.",
        }, status=201)
