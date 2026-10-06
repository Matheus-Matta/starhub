"""Toda conta tem o seu SMTP e a sua configuracao de notificacao (tudo desligado).

Criados quando a conta nasce (post_save da Account) e, para as contas que ja
existiam, pela migration de dados. O indice unico por conta segura duas criacoes ao
mesmo tempo: get_or_create.
"""

from apps.core.tenant.context import tenant_context


def garantir(conta_id):
    from apps.notificacoes.models import ConfiguracaoEmail, ConfiguracaoNotificacao

    # Gravar registro de outra conta exige o contexto dela (BaseModel.save confere).
    with tenant_context(conta_id):
        email, _ = ConfiguracaoEmail.all_objects.get_or_create(account_id=conta_id)
        notificacao, _ = ConfiguracaoNotificacao.all_objects.get_or_create(account_id=conta_id)
    return email, notificacao


def conta_criada(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        garantir(instance.pk)
