from celery import shared_task

from apps.core.tenant.context import tenant_context
from apps.integracoes.tempo_real import enviar_ao_grupo
from apps.notificacoes import email
from apps.notificacoes.entrega import GRUPO, TIPO, entregar, para_tela
from apps.notificacoes.models import ConfiguracaoEmail, Notificacao


@shared_task
def notificar(conta_id, aviso):
    with tenant_context(conta_id):
        return entregar(conta_id, aviso)


@shared_task
def testar_email(conta_id, usuario_id, para):
    """E-mail de teste do SMTP da conta; o resultado chega no sino de quem pediu."""
    with tenant_context(conta_id):
        smtp = ConfiguracaoEmail.objects.filter(account_id=conta_id).first()
        try:
            email.enviar(smtp, [para], "[StarHub] E-mail de teste",
                         "Se voce recebeu esta mensagem, o SMTP da conta esta funcionando.")
            titulo, mensagem = "E-mail de teste enviado", f"Confira a caixa de {para}."
        except Exception as erro:  # o operador precisa ver o motivo exato do servidor
            titulo, mensagem = "E-mail de teste falhou", str(erro)[:500]
        notificacao = Notificacao.objects.create(account_id=conta_id, usuario_id=usuario_id,
                                                 evento="email.teste", titulo=titulo,
                                                 mensagem=mensagem)
        enviar_ao_grupo(GRUPO.format(usuario_id), {"type": TIPO,
                                                   "dados": para_tela(notificacao)})
        return titulo
