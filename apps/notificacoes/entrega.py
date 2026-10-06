"""EnviadorNotificacao: entrega um aviso no navegador e no e-mail, pela config da conta.

    EnviadorNotificacao(conta_id, {"evento": "pedido.criado", "titulo": ..., "mensagem": ...,
                                   "link": ...}).enviar()   # {"navegador": 2, "email": 1}

- Configuracao: relida aqui (pode ter sido desligada entre o evento e a tarefa rodar);
  cada canal so sai com a chave geral e o switch do evento ligados.
- Navegador: uma Notificacao para cada usuario ativo da conta que tem permissao de ver
  o registro do evento (ex.: loja.view_pedido); quem nao ve pedidos nao recebe aviso de
  pedido. Empurrada pelo WebSocket do grupo do usuario.
- E-mail: so para os e-mails alvo da configuracao, pelo SMTP da conta. Sem e-mail alvo
  ou SMTP sem servidor, nao sai (e nem conecta).
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.integracoes.tempo_real import enviar_ao_grupo
from apps.notificacoes import email, eventos
from apps.notificacoes.models import ConfiguracaoEmail, ConfiguracaoNotificacao, Notificacao

logger = logging.getLogger(__name__)
GRUPO = "notificacoes-{}"
TIPO = "notificacao.nova"  # -> NotificacaoConsumer.notificacao_nova


def para_tela(notificacao):
    return {"id": notificacao.pk, "titulo": notificacao.titulo,
            "mensagem": notificacao.mensagem, "link": notificacao.link,
            "lida": notificacao.lida,
            "criada_em": notificacao.created_at.strftime("%d/%m %H:%M")}


class EnviadorNotificacao:
    def __init__(self, conta_id, aviso):
        self.conta_id = conta_id
        self.aviso = aviso
        self.configuracao = ConfiguracaoNotificacao.all_objects.filter(
            account_id=conta_id).first()

    def ligado(self, canal):
        return self.configuracao is not None and self.configuracao.canal(
            self.aviso["evento"], canal)

    def usuarios(self):
        """Usuarios ativos da conta com permissao de ver o registro do evento."""
        permissao = eventos.permissao(self.aviso["evento"])
        candidatos = get_user_model().objects.filter(account_id=self.conta_id,
                                                     is_active=True, is_staff=True)
        return [u for u in candidatos if permissao is None or u.has_perm(permissao)]

    def no_navegador(self):
        aviso = self.aviso
        criadas = Notificacao.objects.bulk_create([
            Notificacao(account_id=self.conta_id, usuario=usuario, evento=aviso["evento"],
                        titulo=aviso["titulo"], mensagem=aviso["mensagem"], link=aviso["link"])
            for usuario in self.usuarios()])
        for notificacao in criadas:
            try:
                enviar_ao_grupo(GRUPO.format(notificacao.usuario_id),
                                {"type": TIPO, "dados": para_tela(notificacao)})
            except Exception:  # sem tela aberta ou Redis fora: o sino le do banco ao abrir
                logger.warning("Notificacao %s nao foi empurrada", notificacao.pk,
                               exc_info=True)
        return len(criadas)

    def destinatarios(self):
        return email.destinatarios(self.configuracao.destinatarios)

    def por_email(self):
        para = self.destinatarios()
        smtp = ConfiguracaoEmail.all_objects.filter(account_id=self.conta_id).first()
        if not para or smtp is None or not smtp.configurado:
            logger.warning("E-mail do aviso %s nao saiu: sem e-mail alvo ou SMTP sem "
                           "servidor (conta %s)", self.aviso["evento"], self.conta_id)
            return 0
        base = settings.STARHUB_URL_PUBLICA.rstrip("/")
        link = f"\n\n{base}{self.aviso['link']}" if self.aviso["link"] and base else ""
        try:
            email.enviar(smtp, para, f"[StarHub] {self.aviso['titulo']}",
                         f"{self.aviso['titulo']}\n{self.aviso['mensagem']}{link}")
        except Exception:  # SMTP fora ou recusou: o aviso do navegador ja saiu
            logger.warning("E-mail do aviso %s nao saiu", self.aviso["evento"], exc_info=True)
            return 0
        return len(para)

    def enviar(self):
        return {"navegador": self.no_navegador() if self.ligado("navegador") else 0,
                "email": self.por_email() if self.ligado("email") else 0}


def entregar(conta_id, aviso):
    return EnviadorNotificacao(conta_id, aviso).enviar()
