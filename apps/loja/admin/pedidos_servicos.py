"""Card "Servicos do pedido" na tela do pedido (regra em services/servicos_pedido.py).

Uma linha por servico: item do pedido, servico do cadastro, opcao e preco. O item
novo da mesma tela ainda nao tem id: salve o item antes de ligar servico nele.
"""

from django import forms
from django.contrib import messages
from django.db.models import Q

from apps.core.json_widgets import CampoJSON, ListaTema
from apps.loja.models import Pedido, Servico
from apps.loja.services import servicos_pedido

AJUDA = ("Servico adicionado ou com preco alterado aqui soma no total do item, como o "
         "que veio da loja. Servico so informado pela loja continua fora do total.")


def _colunas(pedido):
    itens = list(pedido.itens.order_by("pk")) if pedido.pk else []
    # Vazio primeiro: linha nova nasce sem item e o operador escolhe; salvar sem
    # escolher e recusado (o servico sem item some do line_item que o ERP le).
    opcoes_itens = [{"valor": "", "rotulo": "Escolha o item"}] + [
        {"valor": str(i.pk), "rotulo": f"{i.nome} ({i.sku})" if i.sku else i.nome}
        for i in itens]
    # Desativado no cadastro mas ja no pedido continua na lista: senao o select travava.
    usados = [linha["servico_id"] for linha in servicos_pedido.linhas_da_tela(pedido)
              if linha["servico_id"].isdigit()]
    cadastros = [{"valor": str(s.pk), "rotulo": s.nome} for s in Servico.objects.filter(
        Q(active=True) | Q(pk__in=usados)).order_by("nome", "pk")]
    sem_cadastro = [{"valor": "", "rotulo": "Sem cadastro (como veio da loja)"}]
    return [
        {"campo": "item_id", "rotulo": "Item", "tipo": "escolha", "opcoes": opcoes_itens},
        {"campo": "servico_id", "rotulo": "Servico", "tipo": "escolha",
         "opcoes": cadastros + sem_cadastro},
        {"campo": "opcao", "rotulo": "Opcao", "tipo": "texto", "placeholder": "Sim"},
        {"campo": "preco", "rotulo": "Preco (R$)", "tipo": "dinheiro"},
    ]


class ServicosDoPedidoForm(forms.ModelForm):
    servicos_do_pedido = CampoJSON(label="Servicos do pedido", required=False, help_text=AJUDA)
    servicos_versao = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campo = self.fields["servicos_do_pedido"]
        campo.widget = ListaTema(_colunas(self.instance), botao="Adicionar servico")
        if self.instance.pk:
            self.initial["servicos_do_pedido"] = servicos_pedido.linhas_da_tela(self.instance)
            self.initial["servicos_versao"] = servicos_pedido.versao(self.instance)

    def clean(self):
        dados = super().clean()
        linhas = dados.get("servicos_do_pedido") or []
        if not self.instance.pk:
            return dados
        mudou = "servicos_do_pedido" in self.changed_data
        if mudou and dados.get("servicos_versao") != servicos_pedido.versao(self.instance):
            self.add_error("servicos_do_pedido", "Os servicos mudaram depois que a tela abriu "
                           "(webhook ou outra aba). Recarregue a pagina e refaca a alteracao.")
            return dados
        itens = {i.pk: i for i in self.instance.itens.all()}
        try:
            servicos_pedido.preparar(self.instance, linhas, itens)
        except servicos_pedido.ServicoInvalido as erro:
            self.add_error("servicos_do_pedido", str(erro))
        return dados


def _avisar_sem_item(request, pedido):
    """Item excluido na mesma tela deixa servico sem vinculo: o operador liga de novo."""
    sem_item = [linha for linha in servicos_pedido.linhas_da_tela(pedido) if not linha["item_id"]]
    if sem_item:
        messages.warning(request, f"{len(sem_item)} servico(s) ficaram sem item porque o item "
                         "foi removido. Escolha o item no card Servicos do pedido e salve.")


def salvar_servicos(request, form):
    """Depois dos itens (save_related): o servico aponta para o item ja gravado."""
    if "servicos_do_pedido" in form.changed_data:
        try:
            servicos_pedido.aplicar(form.instance.pk, form.cleaned_data["servicos_do_pedido"] or [],
                                    form.cleaned_data["servicos_versao"])
        except (servicos_pedido.ServicosMudaram, servicos_pedido.ServicoInvalido) as erro:
            # Corrida de milissegundos com o webhook (a tela ja conferiu no clean): o resto
            # do pedido salvou; so os servicos ficam como estavam.
            motivo = str(erro) or "os servicos mudaram enquanto salvava"
            messages.error(request, f"Servicos nao salvos: {motivo}. Recarregue e refaca.")
    # Relido: o form.instance ainda tem os metadados de antes do aplicar.
    _avisar_sem_item(request, Pedido.objects.get(pk=form.instance.pk))
