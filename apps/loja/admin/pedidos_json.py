"""Botao "JSON" do pedido: o que o ERP recebe, os vinculos e os webhooks recebidos.

So leitura. O JSON da API e o mesmo do GET /wc/v3/orders/<id>; os webhooks sao as
tarefas "Receber webhook" de pedido cujo corpo traz o id externo de algum vinculo.
"""

import json

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.core.models import ExternalReference
from apps.integracoes import trafego
from apps.integracoes.models import ExecucaoIntegracao
from apps.woo_api.recursos.pedidos_saida import pedido_para_woo

# Os mais recentes bastam para conferir; pedido com centenas de updates travaria a tela.
LIMITE_WEBHOOKS = 20


def _legivel(valor):
    return json.dumps(valor, ensure_ascii=False, indent=2, default=str)


def _ids_no_corpo(external_id):
    """Shopify grava gid e o webhook manda numero; Woo manda numero; Suri, texto."""
    numero = external_id.rsplit("/", 1)[-1]
    valores = {external_id, numero}
    if numero.isdigit():
        valores.add(int(numero))
    return list(valores)


def webhooks_do_pedido(vinculos):
    filtro = Q()
    for vinculo in vinculos:
        filtro |= Q(configuracao__plataforma=vinculo.platform) & (
            Q(parametros__reenvio__dados__id__in=_ids_no_corpo(vinculo.external_id))
            | Q(parametros__reenvio__dados__admin_graphql_api_id=vinculo.external_id))
    if not filtro:
        return []
    tarefas = (ExecucaoIntegracao.objects
               .filter(filtro, tipo=ExecucaoIntegracao.Tipo.RECEBER,
                       parametros__reenvio__recurso="pedidos")
               .select_related("configuracao").order_by("-created_at")[:LIMITE_WEBHOOKS])
    return [{"tarefa": tarefa, "corpo": _corpo(tarefa.parametros),
             "url": reverse("admin:integracoes_execucaointegracao_change", args=[tarefa.pk])}
            for tarefa in tarefas]


def _corpo(parametros):
    # A requisicao vem antes: no Suri o reenvio guarda so {"id"}. Tarefa antiga, sem
    # requisicao guardada, ainda tem o corpo no reenvio.
    recebida = (trafego.para_tela(parametros).get("requisicao") or {}).get("corpo")
    return recebida or _legivel(parametros["reenvio"].get("dados"))


class PedidoJsonMixin:
    change_form_template = "admin/loja/pedido/change_form.html"

    def get_urls(self):
        rota = path("<path:object_id>/json/", self.admin_site.admin_view(self.json_view),
                    name="loja_pedido_json")
        return [rota, *super().get_urls()]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        contexto = {**(extra_context or {}),
                    "url_json": reverse("admin:loja_pedido_json", args=[object_id])}
        return super().change_view(request, object_id, form_url, contexto)

    def json_view(self, request, object_id):
        pedido = self.get_object(request, object_id)
        if pedido is None or not self.has_view_permission(request, pedido):
            raise PermissionDenied
        vinculos = list(ExternalReference.objects.filter(
            entity_type="pedidos", object_id=str(pedido.pk)).order_by("platform"))
        # O corpo do webhook e o da tela de Tarefas: mesma permissao dela.
        ver_tarefas = request.user.has_perm("integracoes.view_execucaointegracao")
        contexto = {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "title": f"JSON do pedido #{pedido.number}", "pedido": pedido,
            "url_pedido": reverse("admin:loja_pedido_change", args=[pedido.pk]),
            "json_api": _legivel(pedido_para_woo(pedido)),
            "rota_api": f"GET /wc/v3/orders/{pedido.pk}",
            "vinculos": [{"vinculo": v, "json": _legivel(v.metadata)} for v in vinculos],
            "ver_tarefas": ver_tarefas,
            "webhooks": webhooks_do_pedido(vinculos) if ver_tarefas else [],
            "limite_webhooks": LIMITE_WEBHOOKS,
        }
        return TemplateResponse(request, "admin/loja/pedido/json.html", contexto)
