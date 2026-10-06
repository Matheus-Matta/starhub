"""E-mail da conta pelo SMTP dela (ConfiguracaoEmail), nunca pelo EMAIL_* do settings.

    enviar(configuracao, ["ana@loja.com"], "Pedido novo", "Pedido #SH-1 ...")

Cada conta manda pelo proprio servidor: o remetente e a reputacao sao dela.
"""

from email.utils import formataddr

from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend

TEMPO = 20


class SmtpNaoConfigurado(Exception):
    """Sem servidor ou remetente: o e-mail nao sai e a tela diz o que preencher."""


def conexao(configuracao):
    return EmailBackend(host=configuracao.host, port=configuracao.porta,
                        username=configuracao.usuario or None,
                        password=configuracao.senha or None,
                        use_tls=configuracao.seguranca == "tls",
                        use_ssl=configuracao.seguranca == "ssl",
                        timeout=TEMPO, fail_silently=False)


def destinatarios(texto):
    partes = (texto or "").replace(";", ",").replace("\n", ",").split(",")
    return [p.strip() for p in partes if p.strip()]


def enviar(configuracao, para, assunto, texto):
    if not configuracao.configurado:
        raise SmtpNaoConfigurado("Preencha o servidor SMTP e o e-mail do remetente em "
                                 "Nucleo > E-mail (SMTP).")
    remetente = formataddr((configuracao.remetente_nome or "", configuracao.remetente_email))
    mensagem = EmailMessage(assunto, texto, from_email=remetente, to=list(para),
                            connection=conexao(configuracao))
    return mensagem.send()
