"""Botao "Historico" da edicao: versoes do simple_history, com o que mudou e reverter.

O historico padrao do Django so conhece o que foi salvo pelo admin; alteracao da API
Woo, de webhook e de tarefa nao aparecia, embora a versao estivesse gravada. Aqui
aparece tudo, do registro e do que pertence a ele (variantes do produto, itens do
pedido: apps/core/registros.py), e cada versao tem "Reverter" com confirmacao.
"""

from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.core import historico, registros
from apps.core.tenant.exceptions import TenantMismatchError


class HistoricoMixin:
    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        rota = path("<path:object_id>/history/<int:tipo>/<int:versao>/reverter/",
                    self.admin_site.admin_view(self.reverter_view),
                    name="%s_%s_reverter" % info)
        return [rota, *super().get_urls()]

    def _registro(self, request, object_id):
        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            raise Http404("Registro nao encontrado ou de outra conta.")
        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied
        return obj

    def history_view(self, request, object_id, extra_context=None):
        if historico.manager(self.model) is None:
            return super().history_view(request, object_id, extra_context)
        obj = self._registro(request, object_id)
        com_relacionados = request.GET.get("so") != "1"
        chave = registros.chave(obj)
        alvo = registros.alvo(chave if com_relacionados else registros.SO + chave)
        pagina = int(request.GET["p"]) if request.GET.get("p", "").isdigit() else 1
        linhas, tem_mais = historico.versoes(alvo, max(pagina, 1))
        for linha in linhas:
            linha["url_reverter"] = self._url_reverter(request, obj, linha)
        contexto = {
            **self.admin_site.each_context(request),
            "title": f"Historico de {obj}", "opts": self.model._meta, "original": obj,
            "linhas": linhas, "pagina": pagina, "tem_mais": tem_mais,
            "com_relacionados": com_relacionados,
            "url_edicao": reverse(f"admin:{self._rota('change')}", args=[obj.pk]),
            **(extra_context or {}),
        }
        return TemplateResponse(request, "admin/historico.html", contexto)

    def _rota(self, nome):
        return f"{self.model._meta.app_label}_{self.model._meta.model_name}_{nome}"

    def _url_reverter(self, request, obj, linha):
        modelo = linha["versao"].instance_type
        permissao = f"{modelo._meta.app_label}.change_{modelo._meta.model_name}"
        if not request.user.has_perm(permissao):
            return ""
        return reverse(f"admin:{self._rota('reverter')}",
                       args=[obj.pk, linha["tipo"], linha["versao"].history_id])

    def reverter_view(self, request, object_id, tipo, versao):
        obj = self._registro(request, object_id)
        modelo = ContentType.objects.get_for_id(tipo).model_class()
        manager = historico.manager(modelo)
        escolhida = manager.filter(history_id=versao).first() if manager else None
        alvo = registros.alvo(registros.chave(obj))
        # So versao do proprio registro ou do que e dele: o id na URL nao abre outro.
        pk = str(getattr(escolhida, modelo._meta.pk.attname, "")) if escolhida else ""
        if escolhida is None or pk not in alvo.get(tipo, ()):
            raise Http404("Versao nao encontrada para este registro.")
        if not request.user.has_perm(f"{modelo._meta.app_label}.change_{modelo._meta.model_name}"):
            raise PermissionDenied
        atual = modelo._default_manager.filter(pk=pk).first()
        voltar = reverse(f"admin:{self._rota('history')}", args=[obj.pk])
        if request.method == "POST":
            try:
                historico.reverter(modelo, escolhida, modelo._default_manager)
            except (IntegrityError, ValidationError, TenantMismatchError) as erro:
                messages.error(request, f"Nao foi possivel reverter: {erro}. Corrija o "
                               "registro pela edicao ou escolha outra versao.")
            else:
                messages.success(request, f"{escolhida.instance} voltou para a versao de "
                                 f"{escolhida.history_date:%d/%m/%Y %H:%M:%S}.")
            return HttpResponseRedirect(voltar)
        contexto = {
            **self.admin_site.each_context(request),
            "title": f"Reverter {escolhida.instance}", "opts": self.model._meta,
            "original": obj, "versao": escolhida, "restaurando": atual is None,
            "titulo_versao": f"Versao de {escolhida.history_date:%d/%m/%Y %H:%M:%S}",
            "mudancas": historico.comparar(modelo, atual, escolhida), "url_voltar": voltar,
        }
        return TemplateResponse(request, "admin/historico_reverter.html", contexto)
