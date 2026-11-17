"""Views genericas: listar/criar, ler/alterar/excluir e lote. O recurso decide o resto."""

from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from apps.core import origem
from apps.core.models import Origin
from apps.core.tenant.context import bind_tenant, reset_tenant
from apps.woo_api import registro_tarefa
from apps.woo_api.autenticacao import ChaveConsumidorAuthentication
from apps.woo_api.erros import WooErro, tratar_excecao
from apps.woo_api.paginacao import paginar
from apps.woo_api.parsers import JSONDecimalParser, JSONQualquerTipo
from apps.woo_api.permissoes import PodeUsarApiWoo
from apps.woo_api.recursos.base import booleano


def tratar_erro_woo(exc, context):
    if isinstance(exc, InvalidToken):
        # Mesmo codigo e status do plugin JWT do WordPress.
        exc = WooErro("jwt_auth_invalid_token", "Token invalido ou expirado. Gere outro.", 403)
    return tratar_excecao(exc, context)


class WooView(APIView):
    authentication_classes = [JWTAuthentication, ChaveConsumidorAuthentication]
    permission_classes = [PodeUsarApiWoo]
    parser_classes = [JSONDecimalParser, FormParser, MultiPartParser, JSONQualquerTipo]
    recurso_classe = None

    def get_exception_handler(self):
        return tratar_erro_woo

    def dispatch(self, request, *args, **kwargs):
        self._tokens_conta = self._token_origem = self._tarefa = None
        try:
            return super().dispatch(request, *args, **kwargs)
        finally:
            if self._tarefa is not None:  # 500 fora do tratador: finalize_response nao rodou
                registro_tarefa.sem_resposta(self._tarefa)
            if self._token_origem:
                origem.restaurar(self._token_origem)
            if self._tokens_conta:
                reset_tenant(self._tokens_conta)

    def registra_tarefa(self):
        """Pedido encaminhado a loja WooCommerce ja vira a tarefa "Encaminhar" (encaminhar.py)."""
        return True

    def initial(self, request, *args, **kwargs):
        # O DRF autentica no request.user, DEPOIS do TenantMiddleware do Django: quem
        # entrou por JWT ou chave ck_ so e conhecido agora. Sem conta, nada roda.
        account_id = getattr(request.user, "account_id", None)
        if account_id is not None:
            self._tokens_conta = bind_tenant(account_id, request.user)
            # Aberta antes da permissao e do processamento: recusa (403) e erro tambem
            # ficam registrados, e cada log da escrita aponta para ela.
            if self.registra_tarefa():
                self._tarefa = registro_tarefa.abrir(request, request.user)
            # Log do auditlog: "woo_api" e por onde (chave ck_ ou usuario do JWT, o autor).
            self._token_origem = origem.definir(
                origem.WOO_API, via=request.user, ator=request.user,
                tarefa=getattr(self._tarefa, "pk", None),
                requisicao=origem.requisicao_de(request._request))
        super().initial(request, *args, **kwargs)
        if account_id is None:
            raise PermissionDenied("O acesso nao pertence a nenhuma conta.")

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            registro_tarefa.fechar(tarefa, response)
        elif response.status_code >= 400 and self._tokens_conta and self.registra_tarefa():
            registro_tarefa.registrar_erro(request, request.user, response)
        return response

    def recurso(self):
        recurso = self.recurso_classe()
        recurso.request = self.request
        return recurso

    def corpo(self):
        if not isinstance(self.request.data, dict):
            raise WooErro("rest_invalid_json", "O corpo precisa ser um objeto JSON.", 400)
        return self.request.data


def gravar(recurso, obj, dados, criando):
    """Grava numa transacao. IntegrityError (indice unico) vira o erro do Woo.

    O except fica FORA do atomic: a transacao ja foi desfeita quando ele roda.
    """
    try:
        with transaction.atomic():
            if criando:
                obj.origin = Origin.API
            else:
                obj = recurso.obter_para_escrita(obj)
            return recurso.gravar(obj, dados, criando)
    except IntegrityError as erro:
        raise recurso.erro_integridade(erro) from erro


def excluir(recurso, pk, forcar):
    with transaction.atomic():
        return recurso.excluir(recurso.obter_para_escrita(pk), forcar)


class ListaView(WooView):
    def get(self, request):
        recurso = self.recurso()
        qs = recurso.filtrar(recurso.queryset(), request.query_params)
        itens, cabecalhos = paginar(request, qs)
        return Response(recurso.para_lista(itens), headers=cabecalhos)

    def post(self, request):
        recurso = self.recurso()
        obj = gravar(recurso, recurso.modelo(), self.corpo(), criando=True)
        return Response(recurso.para_woo(obj), status=201)


class DetalheView(WooView):
    def get(self, request, pk):
        recurso = self.recurso()
        return Response(recurso.para_woo(recurso.obter(pk)))

    def put(self, request, pk):
        recurso = self.recurso()
        recurso.obter(pk)  # 404 antes de abrir transacao
        obj = gravar(recurso, pk, self.corpo(), criando=False)
        return Response(recurso.para_woo(obj))

    patch = put
    post = put

    def delete(self, request, pk):
        recurso = self.recurso()
        forcar = request.query_params.get("force") or (
            request.data.get("force") if isinstance(request.data, dict) else None
        )
        return Response(excluir(recurso, pk, booleano(forcar or False, "force")))
