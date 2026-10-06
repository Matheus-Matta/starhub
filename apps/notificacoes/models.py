"""E-mail (SMTP) e notificacoes de cada conta.

Toda conta nasce com uma ConfiguracaoEmail e uma ConfiguracaoNotificacao (contas.py):
o SMTP e quem manda os e-mails da conta; a configuracao de notificacao diz o que avisa
e por onde (navegador, e-mail). Tudo desligado ate o operador ligar.
"""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.integracoes import segredos


class ConfiguracaoEmail(BaseModel):
    class Seguranca(models.TextChoices):
        TLS = "tls", "STARTTLS (porta 587)"
        SSL = "ssl", "SSL (porta 465)"
        NENHUMA = "nenhuma", "Sem criptografia (porta 25)"

    host = models.CharField("servidor SMTP", max_length=255, blank=True,
                            help_text="Ex.: smtp.gmail.com, smtp.office365.com, email-smtp...")
    porta = models.PositiveIntegerField("porta", default=587)
    seguranca = models.CharField("seguranca", max_length=10, choices=Seguranca,
                                 default=Seguranca.TLS)
    usuario = models.CharField("usuario", max_length=255, blank=True)
    senha_criptografada = models.TextField(editable=False, blank=True)
    remetente_email = models.EmailField(
        "e-mail do remetente", blank=True,
        help_text="Quem aparece como remetente. Muitos servidores exigem o mesmo do usuario.")
    remetente_nome = models.CharField("nome do remetente", max_length=150, blank=True,
                                      default="StarHub")

    class Meta:
        verbose_name = "e-mail (SMTP)"
        verbose_name_plural = "E-mail (SMTP)"
        constraints = [models.UniqueConstraint(fields=["account"],
                                               name="email_smtp_um_por_conta")]

    def __str__(self):
        return self.host or "SMTP nao configurado"

    @property
    def senha(self):
        return segredos.descriptografar(self.senha_criptografada)

    @senha.setter
    def senha(self, valor):
        self.senha_criptografada = segredos.criptografar(valor)

    @property
    def configurado(self):
        return bool(self.host and self.remetente_email)


class ConfiguracaoNotificacao(BaseModel):
    ligado = models.BooleanField(
        "notificacoes ligadas", default=False,
        help_text="Chave geral: desligada, nenhum evento avisa, mesmo com os switches abaixo.")
    destinatarios = models.TextField(
        "e-mails alvo", blank=True,
        help_text="Quem recebe os e-mails das notificacoes: so estes enderecos. Um por "
                  "linha ou separados por virgula. Obrigatorio com algum switch de e-mail.")
    # {"pedido.criado": {"navegador": true, "email": false}, ...}; evento ausente = desligado.
    regras = models.JSONField("regras", default=dict, blank=True)

    class Meta:
        verbose_name = "configuracao de notificacao"
        verbose_name_plural = "Notificacoes"
        constraints = [models.UniqueConstraint(fields=["account"],
                                               name="notificacao_config_um_por_conta")]

    def __str__(self):
        return "Ligadas" if self.ligado else "Desligadas"  # trilha: Notificacoes > Desligadas

    def canal(self, evento, canal):
        return bool(self.ligado and (self.regras or {}).get(evento, {}).get(canal))


class Notificacao(BaseModel):
    """Aviso no navegador de um usuario (sino do cabecalho)."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="usuario",
                                on_delete=models.CASCADE, related_name="notificacoes")
    evento = models.CharField("evento", max_length=50)
    titulo = models.CharField("titulo", max_length=200)
    mensagem = models.CharField("mensagem", max_length=500, blank=True)
    link = models.CharField("link", max_length=300, blank=True)
    lida = models.BooleanField("lida", default=False, db_index=True)

    class Meta:
        verbose_name = "notificacao"
        verbose_name_plural = "notificacoes recebidas"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["usuario", "lida"], name="notificacao_usuario_lida")]

    def __str__(self):
        return self.titulo
