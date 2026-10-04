"""Cadastro das tabelas de frete: a tela muda conforme a forma de cobranca.

Por distancia mostra CEP de origem, preco por km, taxa e limites; por faixa de CEP
mostra a lista de faixas (condicoes -> static/starhub/js/condicoes.js). O botao
"Simular cotacao" calcula para um CEP sem ligar a pedido nenhum.
"""

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.forms.models import BaseInlineFormSet
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.core.admin_base import TemaModelAdmin, TemaTabularInline
from apps.core.admin_utils import badge
from apps.core.ui.formatos import moeda
from apps.integracoes.admin_importar import ImportarPlanilhaMixin
from apps.integracoes.models import ExecucaoIntegracao
from apps.logistica.cotacao import FreteIndisponivel, cotar
from apps.logistica.models import FaixaCep, TabelaFrete

SO_DISTANCIA = {"campo": "tipo", "em": [TabelaFrete.Tipo.DISTANCIA]}


class FaixasFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        faixas = sorted(
            (f.cleaned_data["cep_inicial"], f.cleaned_data["cep_final"])
            for f in self.forms
            if getattr(f, "cleaned_data", None) and not f.cleaned_data.get("DELETE")
            and f.cleaned_data.get("cep_inicial") and f.cleaned_data.get("cep_final")
        )
        # Faixas que se cruzam cobrariam dois valores para o mesmo CEP: o lojista
        # corrige aqui em vez de descobrir no checkout qual delas venceu.
        for (inicio_a, fim_a), (inicio_b, fim_b) in zip(faixas, faixas[1:], strict=False):
            if inicio_b <= fim_a:
                raise ValidationError(
                    f"As faixas {inicio_a}-{fim_a} e {inicio_b}-{fim_b} se cruzam; "
                    "ajuste para cada CEP cair em uma faixa so.")
        if self.instance.tipo == TabelaFrete.Tipo.FAIXA_CEP and not faixas:
            raise ValidationError("Cadastre ao menos uma faixa de CEP.")


class FaixaCepInline(TemaTabularInline):
    model = FaixaCep
    formset = FaixasFormSet
    fields = ["cep_inicial", "cep_final", "valor", "prazo_dias"]
    extra = 1


class ImportarFaixasMixin(ImportarPlanilhaMixin):
    importar_tipo = ExecucaoIntegracao.Tipo.IMPORTAR_FRETE
    importar_tarefa = "apps.logistica.tasks.importar_faixas"
    importar_arquivo_modelo = "modelo-faixas-de-frete.csv"
    importar_descricao = "Cria as tabelas por faixa de CEP e as faixas de uma vez."
    importar_colunas = [
        ("tabela", True, "Nome da tabela. Se nao existir, e criada como \"Por faixa de CEP\"."),
        ("cep_inicial", True, "Primeiro CEP da faixa (00000-000)."),
        ("cep_final", True, "Ultimo CEP da faixa (00000-000)."),
        ("valor", True, "Frete da faixa, por exemplo 19,90."),
        ("prazo_dias", False, "Dias uteis de entrega; vazio = prazo da tabela."),
    ]
    importar_exemplo = ["Grande SP", "01000-000", "05999-999", "19,90", "2"]
    importar_regras = [
        "Mesma tabela e mesma faixa (CEP inicial e final) atualiza valor e prazo: importar "
        "de novo a planilha corrigida nao duplica.",
        "Faixa que cruza outra da mesma tabela e recusada, com o motivo.",
        "Linha com erro nao para as outras: a tarefa lista cada uma com o motivo.",
    ]
    importar_opcoes = [("substituir", "Substituir: apaga as faixas atuais das tabelas da "
                                      "planilha antes de importar (a planilha vira a tabela "
                                      "inteira).")]


@admin.register(TabelaFrete)
class TabelaFreteAdmin(ImportarFaixasMixin, TemaModelAdmin):
    list_display = ["nome", "tipo_fmt", "resumo", "prazo_dias", "ativa_fmt"]
    list_filter = ["tipo", "active"]
    search_fields = ["nome", "cep_origem"]
    inlines = [FaixaCepInline]
    fieldsets = [
        ("Tabela", {"fields": ["nome", "tipo", "prazo_dias", "active", "no_checkout"]}),
        ("Cobranca por distancia", {
            "classes": ["secao-distancia"],
            "fields": ["cep_origem", "preco_por_km", "taxa_fixa", "valor_minimo",
                       "distancia_maxima_km"],
        }),
    ]
    condicoes = {
        ".secao-distancia": SO_DISTANCIA,
        "#faixas-group": {"campo": "tipo", "em": [TabelaFrete.Tipo.FAIXA_CEP]},
    }

    def get_urls(self):
        rota = path("<path:object_id>/simular/", self.admin_site.admin_view(self.simular_view),
                    name="logistica_tabelafrete_simular")
        return [rota, *super().get_urls()]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        contexto = {**(extra_context or {}),
                    "url_simular": reverse("admin:logistica_tabelafrete_simular",
                                           args=[object_id])}
        return super().change_view(request, object_id, form_url, contexto)

    def simular_view(self, request, object_id):
        tabela = self.get_object(request, object_id)
        if tabela is None or not self.has_view_permission(request, tabela):
            raise PermissionDenied
        cep, cotacao, erro = request.GET.get("cep", ""), None, ""
        if cep:
            try:
                cotacao = cotar(tabela, cep)
            except FreteIndisponivel as falha:
                erro = str(falha)
        contexto = {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "title": f"Simular cotacao - {tabela}", "tabela": tabela, "cep": cep,
            "cotacao": cotacao, "valor": moeda(cotacao.valor) if cotacao else "", "erro": erro,
            "url_tabela": reverse("admin:logistica_tabelafrete_change", args=[tabela.pk]),
        }
        return TemplateResponse(request, "admin/logistica/tabelafrete/simular.html", contexto)

    @admin.display(description="forma de cobranca", ordering="tipo")
    def tipo_fmt(self, obj):
        tom = "primary" if obj.tipo == TabelaFrete.Tipo.DISTANCIA else "info"
        return badge(obj.get_tipo_display(), tom)

    @admin.display(description="regra")
    def resumo(self, obj):
        if obj.tipo == TabelaFrete.Tipo.DISTANCIA:
            cep = f"{obj.cep_origem[:5]}-{obj.cep_origem[5:]}" if obj.cep_origem else "-"
            return (f"{moeda(obj.preco_por_km)}/km + {moeda(obj.taxa_fixa)} "
                    f"(min. {moeda(obj.valor_minimo)}) a partir de {cep}")
        return f"{obj.faixas.count()} faixa(s) de CEP"

    @admin.display(description="ativa", ordering="active")
    def ativa_fmt(self, obj):
        return badge("Ativa", "success") if obj.active else badge("Desativada")
