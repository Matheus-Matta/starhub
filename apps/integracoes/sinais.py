"""O unico receiver que leva alteracoes do hub aos marketplaces (ver envio/distribuidor.py)."""

from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save

from apps.integracoes.envio.distribuidor import obter


def _antes(sender, instance, raw=False, update_fields=None, **kwargs):
    if not raw:  # raw = loaddata: fixture nao e alteracao para enviar
        obter().antes_de_salvar(instance, update_fields)


def _depois(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if not raw:
        obter().depois_de_salvar(instance, created, update_fields)


def _excluido(sender, instance, **kwargs):
    obter().depois_de_excluir(instance)


def _m2m_produto(sender, instance, action, reverse, **kwargs):
    # reverse: tag.produtos.add(...) mexe em varios produtos; fica sem envio (raro no hub).
    if action in {"post_add", "post_remove", "post_clear"} and not reverse:
        obter().m2m_do_produto(instance)


def _opcao_da_variante(sender, instance, raw=False, **kwargs):
    """Opcao da variante (Cor: Azul -> Verde) mudou: o produto vai de novo. Sem isso o
    save da variante sem outro campo mudado nao gerava envio e a loja ficava com Azul."""
    if raw:
        return
    from apps.loja.models import Produto, VarianteProduto

    try:
        produto = VarianteProduto.all_objects.get(pk=instance.variante_id).produto
    except (VarianteProduto.DoesNotExist, Produto.DoesNotExist):
        return  # variante/produto sendo excluido: a exclusao ja gera o envio dela
    obter().filhos_do_produto(produto)


def conectar():
    distribuidor = obter()
    for modelo in distribuidor.modelos():
        rotulo = modelo._meta.label
        pre_save.connect(_antes, sender=modelo, dispatch_uid=f"envio-antes-{rotulo}")
        post_save.connect(_depois, sender=modelo, dispatch_uid=f"envio-depois-{rotulo}")
        post_delete.connect(_excluido, sender=modelo, dispatch_uid=f"envio-excluido-{rotulo}")
    from apps.loja.models import Produto, ValorDaVarianteProduto

    for sinal, nome in ((post_save, "salva"), (post_delete, "excluida")):
        sinal.connect(_opcao_da_variante, sender=ValorDaVarianteProduto,
                      dispatch_uid=f"envio-opcao-{nome}")
    for campo in ("categorias", "tags"):
        through = getattr(Produto, campo).through
        m2m_changed.connect(_m2m_produto, sender=through, dispatch_uid=f"envio-m2m-{campo}")
