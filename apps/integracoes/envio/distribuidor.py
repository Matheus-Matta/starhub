"""O unico ponto que decide o que vai para cada marketplace depois de uma gravacao.

Regra: a origem da alteracao nunca recebe o proprio eco. O que veio do Shopify
(webhook, sincronizacao) vai para os outros marketplaces, nao volta ao Shopify;
o que nasceu no hub (admin, API Woo, comando) vai para todos.

Nao passa por aqui (nao gera envio): `QuerySet.update()`, `bulk_create` e
`bulk_update`, que nao disparam signal; e filhos sem model no MAPA (item do
pedido, endereco do cliente, midia do produto) enquanto o pai nao for salvo.
"""

from django.core.exceptions import ValidationError

from apps.core import origem
from apps.integracoes.envio import registro, transacao
from apps.integracoes.models import ConfiguracaoIntegracao

# Campos que o hub mexe sozinho a cada save: mudar so eles nao e alteracao real.
IGNORADOS = {"updated_at", "updated_by", "created_at", "created_by"}

# Mudou so isto na variante: e baixa/entrada de estoque, nao edicao do produto.
# inventory_policy e manage_inventory ficam em "produtos": no marketplace sao
# campos da variante, nao quantidade no local.
CAMPOS_ESTOQUE = {"inventory_quantity", "stock_status", "low_stock_amount"}


def _mapa():
    from apps.loja.models import (
        Avaliacao,
        Categoria,
        Cliente,
        Cupom,
        Pedido,
        Produto,
        VarianteProduto,
    )

    return {
        Produto: "produtos",
        VarianteProduto: "variante",
        Categoria: "categorias",
        Cliente: "clientes",
        Pedido: "pedidos",
        Cupom: "cupons",
        Avaliacao: "avaliacoes",
    }


class Distribuidor:
    def __init__(self):
        self.mapa = _mapa()

    def modelos(self):
        return list(self.mapa)

    # Entrada pelos signals.

    def antes_de_salvar(self, instance, update_fields=None):
        """pre_save: guarda os destinos e como a linha esta no banco para comparar depois."""
        instance._envio_antes = None
        if getattr(instance, "_sem_envio", False):
            # Registro marcado para ficar so no hub (ex.: cliente criado pela planilha de
            # avaliacoes so para assinar a avaliacao: nao vira conta na loja).
            instance._envio_configs = []
            return
        # Sem destino (conta sem marketplace, ou so a propria origem, como na
        # sincronizacao do Shopify) nao gasta a consulta do retrato.
        instance._envio_configs = self.candidatos(instance.account_id)
        if not instance._envio_configs or instance._state.adding or instance.pk is None:
            return
        campos = self._campos(instance, update_fields)
        instance._envio_antes = (
            type(instance)._base_manager.filter(pk=instance.pk).values(*campos).first()
        )

    def depois_de_salvar(self, instance, created, update_fields=None):
        configuracoes = instance.__dict__.pop("_envio_configs", None)
        if configuracoes is None:
            configuracoes = self.candidatos(instance.account_id)
        if not configuracoes:
            return
        mudados = None
        if not created:
            mudados = self._mudados(instance, update_fields)
            if not mudados:
                return
        recurso, pk, operacao = self._alvo(instance, "create" if created else "update", mudados)
        self.distribuir(instance.account_id, recurso, operacao, pk, configuracoes)

    def depois_de_excluir(self, instance):
        recurso, pk, operacao = self._alvo(instance, "delete", None)
        self.distribuir(instance.account_id, recurso, operacao, pk)

    def m2m_do_produto(self, produto):
        """Categoria ou tag do produto mudou: o save do produto ja passou sem ela."""
        self.distribuir(produto.account_id, "produtos", "update", produto.pk)

    # Decisao.

    def _alvo(self, instance, operacao, mudados):
        recurso = self.mapa[type(instance)]
        if recurso != "variante":
            return recurso, instance.pk, operacao
        if operacao == "update" and mudados <= CAMPOS_ESTOQUE:
            return "estoque", instance.pk, "update"
        # Variante nova, excluida ou editada: no marketplace e o produto pai que muda.
        return "produtos", instance.produto_id, "update"

    def candidatos(self, conta_id):
        """Configuracoes ativas da conta com enviador registrado, menos a da origem."""
        if not conta_id:
            return []
        return list(ConfiguracaoIntegracao.all_objects.filter(
            account_id=conta_id, active=True, plataforma__in=registro.plataformas()
        ).exclude(plataforma=origem.atual()))

    def distribuir(self, conta_id, recurso, operacao, pk, configuracoes=None):
        if pk is None:
            return
        if configuracoes is None:
            configuracoes = self.candidatos(conta_id)
        for configuracao in configuracoes:
            if configuracao.habilitado("enviar", recurso, operacao):
                transacao.agendar(configuracao.pk, recurso, operacao, pk, _enfileirar)

    # Comparacao antes x depois.

    def _campos(self, instance, update_fields):
        campos = [
            f.attname for f in instance._meta.concrete_fields
            if f.attname not in IGNORADOS and not f.primary_key
        ]
        if update_fields is not None:
            campos = [c for c in campos if c in set(update_fields) or c[:-3] in update_fields]
        return campos

    def _mudados(self, instance, update_fields):
        antes = getattr(instance, "_envio_antes", None)
        if antes is None:
            # Sem retrato (linha sumiu ou pre_save nao rodou): na duvida, envia.
            return set(self._campos(instance, update_fields))
        campos = {f.attname: f for f in instance._meta.concrete_fields}
        return {
            nome for nome, valor in antes.items()
            if _normalizar(campos[nome], getattr(instance, nome)) != valor
        }


def _normalizar(campo, valor):
    # "19.90" digitado x Decimal("19.90") do banco nao e mudanca.
    try:
        return campo.to_python(valor)
    except (ValidationError, TypeError, ValueError):  # invalido: compara cru; o save reclama
        return valor


def _enfileirar(configuracao_id, recurso, operacao, pk):
    from apps.core.tarefas import enfileirar
    from apps.integracoes.tasks import enviar_alteracao

    enfileirar(enviar_alteracao, str(configuracao_id), recurso, operacao, str(pk))


distribuidor = None


def obter():
    global distribuidor
    if distribuidor is None:
        distribuidor = Distribuidor()
    return distribuidor

