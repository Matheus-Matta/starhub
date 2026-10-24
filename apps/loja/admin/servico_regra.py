"""Form do modal da regra do servico (aberto pela pagina do servico, servicos.py).

A regra e por categoria OU por produto (campo tipo). As categorias e os produtos
entram um por linha, com "Adicionar", igual as opcoes no modal da variante: cada
linha e um registro da tabela M2M (RegraServico.categorias/produtos.through).
"""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from apps.core.admin_base import TemaModelAdmin, TemaTabularInline
from apps.loja.models import RegraServico, Servico
from apps.loja.services.servicos_regras import proxima_ordem

Tipo = RegraServico.Tipo


class LinhasDaRegra(BaseInlineFormSet):
    campo = ""  # "produto" | "categoria"
    tipo = ""  # Tipo que usa estas linhas

    def escolhidos(self):
        return [form.cleaned_data[self.campo] for form in self.forms
                if getattr(form, "cleaned_data", None) and not form.cleaned_data.get("DELETE")
                and form.cleaned_data.get(self.campo)]

    def clean(self):
        super().clean()
        if self.instance.tipo != self.tipo:
            return  # linhas do outro tipo saem ao salvar (RegraServicoAdmin.save_related)
        escolhidos = self.escolhidos()
        if len({obj.pk for obj in escolhidos}) != len(escolhidos):
            # O indice unico da tabela M2M recusaria; aqui o erro diz qual linha tirar.
            raise ValidationError(f"O mesmo {self.campo} aparece em duas linhas; tire uma.")
        try:
            self.instance.validar_criterios(
                produtos=escolhidos if self.tipo == Tipo.PRODUTO else [],
                categorias=escolhidos if self.tipo == Tipo.CATEGORIA else [])
        except ValidationError as erro:
            raise ValidationError(erro.messages) from None


class LinhasDeProduto(LinhasDaRegra):
    campo, tipo = "produto", Tipo.PRODUTO


class LinhasDeCategoria(LinhasDaRegra):
    campo, tipo = "categoria", Tipo.CATEGORIA


class LinhaDaRegraInline(TemaTabularInline):
    extra = 0

    # A linha e parte da regra: quem mexe na regra mexe nas linhas. Sem isto o Django
    # pede a permissao de alterar Produto/Categoria (regra da tabela M2M automatica).
    def _pode(self, request):
        return any(request.user.has_perm(f"loja.{acao}_regraservico")
                   for acao in ("add", "change"))

    def has_view_permission(self, request, obj=None):
        return self._pode(request) or request.user.has_perm("loja.view_regraservico")

    def has_add_permission(self, request, obj=None):
        return self._pode(request)

    def has_change_permission(self, request, obj=None):
        return self._pode(request)

    def has_delete_permission(self, request, obj=None):
        return self._pode(request)


class CategoriasDaRegraInline(LinhaDaRegraInline):
    model = RegraServico.categorias.through
    formset = LinhasDeCategoria
    fields = ["categoria"]
    autocomplete_fields = ["categoria"]
    relacao_so_adicionar = ["categoria"]
    verbose_name = "categoria"
    verbose_name_plural = "categorias"


class ProdutosDaRegraInline(LinhaDaRegraInline):
    model = RegraServico.produtos.through
    formset = LinhasDeProduto
    fields = ["produto"]
    autocomplete_fields = ["produto"]
    relacao_so_adicionar = ["produto"]
    verbose_name = "produto"
    verbose_name_plural = "produtos"


class RegraServicoForm(forms.ModelForm):
    class Meta:
        model = RegraServico
        fields = ["servico", "tipo", "ordem", "active", "preco", "preco_de", "preco_ate"]


@admin.register(RegraServico)
class RegraServicoAdmin(TemaModelAdmin):
    form = RegraServicoForm
    pai_da_lista = "servico"  # no modal da pagina do servico o campo some
    relatorio = False  # a regra e parte do servico, nao um cadastro a relatar
    autocomplete_fields = ["servico"]
    inlines = [CategoriasDaRegraInline, ProdutosDaRegraInline]
    larguras = {"tipo": 6, "ordem": 3, "active": 3, "preco": 6, "preco_de": 6, "preco_ate": 6}
    # O prefixo do inline da tabela M2M automatica e "<Model>_<campo>" (Django).
    condicoes = {
        "#RegraServico_categorias-group": {"campo": "tipo", "em": [Tipo.CATEGORIA]},
        "#RegraServico_produtos-group": {"campo": "tipo", "em": [Tipo.PRODUTO]},
        ".secao-faixa": {"campo": "tipo", "em": [Tipo.CATEGORIA]},
    }
    fieldsets = [
        ("Regra", {"fields": ["servico", ("tipo", "preco"), ("ordem", "active")]}),
        # "sh-final": depois das linhas de categoria/produto.
        ("Faixa de preco", {
            "classes": ["sh-final", "secao-faixa"], "fields": [("preco_de", "preco_ate")],
            "description": "Opcional: so os produtos das categorias nesta faixa de preco."}),
    ]

    def has_module_permission(self, request):
        # Fica fora do menu: a regra so existe dentro da pagina do servico.
        return False

    def get_changeform_initial_data(self, request):
        inicial = super().get_changeform_initial_data(request)
        servico = Servico.objects.filter(pk=request.GET.get("servico")).first()
        if servico is not None:
            inicial.setdefault("ordem", proxima_ordem(servico))
        return inicial

    def save_model(self, request, obj, form, change):
        if obj.tipo == Tipo.PRODUTO:
            obj.preco_de = obj.preco_ate = None  # a faixa so vale dentro das categorias
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # As linhas do outro tipo ficaram escondidas na tela: saem aqui, para a regra
        # nunca casar por um criterio que o operador nao ve.
        regra = form.instance
        if regra.tipo == Tipo.PRODUTO:
            regra.categorias.clear()
        else:
            regra.produtos.clear()
