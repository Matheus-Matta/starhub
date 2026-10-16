from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, post_save

from apps.loja.models import Cliente, Pedido


def _agendar(instance, evento):
    from apps.starchats.models import ConjuntoEnvio

    if not ConjuntoEnvio.all_objects.filter(
        account_id=instance.account_id, active=True, evento=evento
    ).exists():
        return
    from apps.starchats.agenda import agendar

    tipo = "cliente" if isinstance(instance, Cliente) else "pedido"
    agendar(instance.account_id, tipo, instance.pk, evento)


def cliente_salvo(sender, instance, created, raw=False, **kwargs):
    if not raw:
        acao = "criado" if created else "alterado"
        _agendar(instance, f"cliente.{acao}")


def pedido_salvo(sender, instance, created, raw=False, **kwargs):
    if not raw:
        acao = "criado" if created else "alterado"
        _agendar(instance, f"pedido.{acao}")


def validar_regra_da_conta(sender, instance, action, reverse, pk_set, **kwargs):
    if action != "pre_add" or not pk_set:
        return
    from apps.starchats.models import ConjuntoEnvio, RegraEnvio

    modelo = ConjuntoEnvio if reverse else RegraEnvio
    if modelo.all_objects.filter(pk__in=pk_set).exclude(account_id=instance.account_id).exists():
        raise ValidationError("Regras e conjuntos precisam pertencer a mesma conta.")


def conectar():
    post_save.connect(cliente_salvo, sender=Cliente, dispatch_uid="starchats_cliente_salvo")
    post_save.connect(pedido_salvo, sender=Pedido, dispatch_uid="starchats_pedido_salvo")
    from apps.starchats.models import ConjuntoEnvio

    m2m_changed.connect(
        validar_regra_da_conta,
        sender=ConjuntoEnvio.regras.through,
        dispatch_uid="starchats_regra_mesma_conta",
    )
