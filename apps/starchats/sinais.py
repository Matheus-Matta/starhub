from django.db.models.signals import post_save

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
    # Desativado nao manda mensagem; a reativacao (_sem_envio) tambem nao e novidade
    # para o cliente.
    if not raw and instance.active and not getattr(instance, "_sem_envio", False):
        acao = "criado" if created else "alterado"
        _agendar(instance, f"pedido.{acao}")


def conectar():
    post_save.connect(cliente_salvo, sender=Cliente, dispatch_uid="starchats_cliente_salvo")
    post_save.connect(pedido_salvo, sender=Pedido, dispatch_uid="starchats_pedido_salvo")
