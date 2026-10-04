"""Moderacao das avaliacoes que os clientes enviam pelo tema da loja.

O texto do cliente nao e editado aqui: a tela da avaliacao e de leitura, com os
botoes Aprovar / Rejeitar / Voltar para pendente, que postam em <id>/moderar/.
Aprovar (ou rejeitar uma ja publicada) dispara o envio a loja pelo save (moderar()).
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from apps.core.admin_base import TemaModelAdmin
from apps.core.admin_utils import badge
from apps.core.filtros import FiltroPeriodo
from apps.loja.admin.avaliacoes_importar import ImportarAvaliacoesMixin
from apps.loja.models import Avaliacao
from apps.loja.services.avaliacoes import AvaliacaoConflito, moderar

TONS = {"aprovada": "success", "pendente": "warning", "rejeitada": "destructive"}


@admin.register(Avaliacao)
class AvaliacaoAdmin(ImportarAvaliacoesMixin, TemaModelAdmin):
    list_display = [
        "nome_publico", "produto", "estrelas", "resumo", "compra_fmt", "status_fmt",
        "publicada_em", "created_at",
    ]
    list_display_links = ["nome_publico"]
    list_filter = ["status", "nota", "compra_verificada", ("created_at", FiltroPeriodo)]
    search_fields = ["nome_publico", "comentario", "produto__nome", "cliente__email"]
    list_select_related = ["produto"]
    change_form_template = "admin/loja/avaliacao/change_form.html"
    # Tudo leitura: um POST no formulario padrao nao muda status sem passar por moderar().
    fields = readonly_fields = [
        "status", "motivo_rejeicao", "produto", "cliente", "nome_publico", "nota", "comentario",
        "compra_verificada", "pedido", "moderado_em", "moderado_por", "publicada_em",
        "created_at",
    ]
    actions = ["aprovar", "rejeitar"]

    def has_add_permission(self, request):
        # Avaliacao nasce do cliente na loja; criada no admin nao teria compra nem autor.
        return False

    def get_urls(self):
        rota = path("<path:object_id>/moderar/", self.admin_site.admin_view(self.moderar_view),
                    name="loja_avaliacao_moderar")
        return [rota, *super().get_urls()]

    def _proxima_pendente(self, request, atual_pk):
        # A mais antiga primeiro: quem espera ha mais tempo e moderado antes.
        pk = (self.get_queryset(request).filter(status=Avaliacao.Status.PENDENTE)
              .exclude(pk=atual_pk).order_by("created_at", "pk").values_list("pk", flat=True)
              .first())
        return reverse("admin:loja_avaliacao_change", args=[pk]) if pk else ""

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id)
        contexto = {**(extra_context or {}), "estrelas": range(1, 6)}
        if obj is not None:
            contexto.update({
                "tom_status": TONS.get(obj.status, "secondary"),
                "url_moderar": reverse("admin:loja_avaliacao_moderar", args=[obj.pk]),
                "url_proxima": self._proxima_pendente(request, obj.pk),
            })
        return super().change_view(request, object_id, form_url, contexto)

    @staticmethod
    def _mensagem(status, publicada):
        if status == Avaliacao.Status.APROVADA:
            return "Avaliacao aprovada. Ela aparece na loja assim que o envio terminar."
        if status == Avaliacao.Status.REJEITADA:
            return ("Avaliacao rejeitada e retirada da loja." if publicada
                    else "Avaliacao rejeitada; ela nao vai para a loja.")
        return "Avaliacao voltou para pendente" + (" e saiu da loja." if publicada else ".")

    def moderar_view(self, request, object_id):
        return require_POST(self._moderar)(request, object_id)

    def _moderar(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404("Avaliacao nao encontrada.")
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        status = {"aprovar": Avaliacao.Status.APROVADA, "rejeitar": Avaliacao.Status.REJEITADA,
                  "pendente": Avaliacao.Status.PENDENTE}.get(request.POST.get("acao"))
        if status is None:
            messages.error(request, "Acao desconhecida: use Aprovar, Rejeitar ou Pendente.")
        else:
            motivo = request.POST.get("motivo", "").strip()[:255]
            try:
                moderar(obj.pk, status, request.user, motivo)
            except AvaliacaoConflito as erro:
                messages.error(request, str(erro))
            else:
                messages.success(request, self._mensagem(status, obj.publicada_em is not None))
        destino = request.POST.get("proxima") and self._proxima_pendente(request, obj.pk)
        return HttpResponseRedirect(destino or reverse("admin:loja_avaliacao_change",
                                                       args=[obj.pk]))

    def _moderar_lote(self, request, queryset, status):
        # Um por um (e nao update()): o save e que leva a mudanca para a loja.
        ids = list(queryset.exclude(status=status).values_list("pk", flat=True))
        mudaram = conflitos = 0
        for pk in ids:
            try:
                moderar(pk, status, request.user)
                mudaram += 1
            except AvaliacaoConflito:
                conflitos += 1
        if conflitos:
            messages.error(request, f"{conflitos} avaliacao(oes) nao mudaram: o cliente ja tem "
                                    "outra avaliacao do produto; exclua uma delas antes.")
        if mudaram:
            rotulo = Avaliacao.Status(status).label.lower()
            messages.success(request, f"{mudaram} avaliacao(oes) {rotulo}(s).")
        elif not conflitos:
            messages.warning(request, "Nenhuma avaliacao mudou: todas ja estavam assim.")

    @admin.action(description="Aprovar e publicar na loja", permissions=["change"])
    def aprovar(self, request, queryset):
        self._moderar_lote(request, queryset, Avaliacao.Status.APROVADA)

    @admin.action(description="Rejeitar (retira da loja se ja publicada)", permissions=["change"])
    def rejeitar(self, request, queryset):
        self._moderar_lote(request, queryset, Avaliacao.Status.REJEITADA)

    @admin.display(description="nota", ordering="nota")
    def estrelas(self, obj):
        return format_html('<span class="nowrap" title="{} de 5">{}</span>',
                           obj.nota, "★" * obj.nota + "☆" * (5 - obj.nota))

    @admin.display(description="comentario")
    def resumo(self, obj):
        texto = obj.comentario
        return texto if len(texto) <= 80 else f"{texto[:77]}..."

    @admin.display(description="compra", ordering="compra_verificada")
    def compra_fmt(self, obj):
        return badge("Verificada", "success") if obj.compra_verificada else badge("Nao verificada")

    @admin.display(description="status", ordering="status")
    def status_fmt(self, obj):
        return badge(obj.get_status_display(), TONS.get(obj.status, "secondary"))
