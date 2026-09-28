"""Secao "Conta" do admin (conta e origem), igual para todo model que tem `account`.

Usuario comum: conta e origem nao existem no formulario (nem ocultos: input
oculto pode ser adulterado). O registro recebe a conta dele e a origem padrao
(StarHub) no save(). Listagem so da conta dele (o manager ja filtra).

Superusuario: ve todas as contas (TenantMiddleware), com coluna e filtro "Conta"
na listagem; escolhe conta e origem ao criar, na secao "Conta", e so as ve (sem
editar) depois: mover um registro de conta deixaria os filhos para tras, e a
origem conta de onde o registro veio. Inline nunca mostra: o filho herda do pai.
"""

from django.contrib.admin.options import InlineModelAdmin
from django.core.exceptions import FieldDoesNotExist

from apps.core.tenant.validators import conta_do_registro

CAMPO = "account"
DO_SISTEMA = (CAMPO, "origin")  # campos da secao "Conta"


def _tem(model, nome):
    try:
        model._meta.get_field(nome)
    except FieldDoesNotExist:
        return False
    return True


def _tem_conta(model):
    return _tem(model, CAMPO)


def _sem_conta(campos):
    saida = []
    for campo in campos:
        if isinstance(campo, (list, tuple)):
            linha = [c for c in campo if c not in DO_SISTEMA]
            if linha:
                saida.append(tuple(linha) if len(linha) > 1 else linha[0])
        elif campo not in DO_SISTEMA:
            saida.append(campo)
    return saida


def _secao_conta(model):
    campos = tuple(nome for nome in DO_SISTEMA if _tem(model, nome))
    return ("Conta", {"fields": [campos if len(campos) > 1 else campos[0]]})


def _contas_de(valor):
    if hasattr(valor, "account_id"):
        return {valor.account_id}
    if isinstance(valor, (list, tuple, set)) or hasattr(valor, "model"):
        return {obj.account_id for obj in valor if hasattr(obj, "account_id")}
    return set()


class ContaFormMixin:
    """Relacao com registro de outra conta vira erro no campo, nao erro 500 no save().

    Com o superusuario vendo todas as contas, o select de cliente/produto traz
    registros de todas; so os da conta do registro podem ser escolhidos.
    """

    campo_pai = None  # FK do inline para o registro principal (a conta vem dele)

    def _conta(self):
        if CAMPO in self.fields and self.cleaned_data.get(CAMPO):
            return self.cleaned_data[CAMPO].pk
        pai = getattr(self.instance, self.campo_pai, None) if self.campo_pai else None
        return getattr(pai, "account_id", None) or conta_do_registro(self.instance)

    def clean(self):
        dados = super().clean()
        conta = self._conta()
        for nome, valor in list(dados.items()):
            if nome in (CAMPO, self.campo_pai) or conta is None:
                continue
            if any(str(outra) != str(conta) for outra in _contas_de(valor)):
                self.add_error(nome, "Pertence a outra conta.")
        return dados


class ContaAdminMixin:
    def _eh_inline(self):
        return isinstance(self, InlineModelAdmin)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not _tem_conta(self.model):
            return fieldsets
        fieldsets = [
            (nome, {**opcoes, "fields": _sem_conta(opcoes["fields"])})
            for nome, opcoes in fieldsets
        ]
        fieldsets = [(nome, opcoes) for nome, opcoes in fieldsets if opcoes["fields"]]
        if request.user.is_superuser and not self._eh_inline():
            fieldsets = [_secao_conta(self.model), *fieldsets]
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if obj is not None and _tem_conta(self.model) and request.user.is_superuser:
            campos += [nome for nome in DO_SISTEMA if _tem(self.model, nome) and nome not in campos]
        return campos

    def get_list_display(self, request):
        colunas = list(super().get_list_display(request))
        if request.user.is_superuser and _tem_conta(self.model) and CAMPO not in colunas:
            colunas.append(CAMPO)
        return colunas

    def get_list_filter(self, request):
        filtros = list(super().get_list_filter(request))
        if request.user.is_superuser and _tem_conta(self.model) and CAMPO not in filtros:
            filtros.append(CAMPO)
        return filtros

    def get_changeform_initial_data(self, request):
        inicial = super().get_changeform_initial_data(request)
        if request.user.is_superuser and _tem_conta(self.model):
            inicial.setdefault(CAMPO, request.user.account_id)
        return inicial

    def get_form(self, request, obj=None, **kwargs):
        return _com_conta(super().get_form(request, obj, **kwargs))

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form = _com_conta(formset.form, campo_pai=formset.fk.name)
        return formset


def _com_conta(form, **atributos):
    # type(form): a classe nova nasce pela metaclasse do ModelForm, como a original.
    return type(form)(form.__name__, (ContaFormMixin, form), atributos)
