"""Modo "encaminhar pedidos a loja WooCommerce", por cima das views de pedido.

Desligado (o padrao), nada muda: o hub responde os pedidos com os dados dele. Ligado
(Integracoes > WooCommerce, so o superusuario ve), depois de autenticar o ERP como
sempre, a requisicao de pedido vai inteira para a loja Woo (apps/woocommerce/
encaminhar.py) e a resposta da loja volta ao ERP como veio, inclusive erro. Cada
encaminhamento vira uma tarefa com a requisicao e a resposta (tela de Tarefas).
"""

from django.http import HttpResponse
from django.utils import timezone

from apps.integracoes import trafego
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao

METODOS = ("get", "post", "put", "patch", "delete", "head", "options")
PREFIXO = "/wp-json/"


def loja_que_encaminha():
    return ConfiguracaoIntegracao.objects.filter(
        plataforma=ConfiguracaoIntegracao.Plataforma.WOOCOMMERCE, active=True,
        encaminhar_pedidos=True).first()


def _registrar(configuracao, request, corpo, status, resposta, cabecalhos, inicio):
    Status = ExecucaoIntegracao.Status
    ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.ENCAMINHAR,
        status=Status.CONCLUIDA if status < 400 else Status.FALHOU,
        etapa=f"HTTP {status}", progresso=100, iniciada_em=inicio,
        concluida_em=timezone.now(),
        mensagem=f"{request.method} {request.path} -> loja WooCommerce HTTP {status}",
        parametros={"requisicao": trafego.requisicao(request, corpo),
                    "resposta": trafego.resposta(status, resposta, cabecalhos)})


def encaminhar_requisicao(configuracao, request):
    from apps.woocommerce.encaminhar import encaminhar

    inicio = timezone.now()
    corpo = request.body
    caminho = request.path.removeprefix(PREFIXO)
    base_hub = request.build_absolute_uri(PREFIXO)
    status, resposta, cabecalhos = encaminhar(
        configuracao, request.method, caminho, request.META.get("QUERY_STRING", ""), corpo,
        request.content_type if corpo else "", base_hub)
    _registrar(configuracao, request, corpo, status, resposta, cabecalhos, inicio)
    saida = HttpResponse(resposta, status=status,
                         content_type=cabecalhos.get("Content-Type", "application/json"))
    for nome, valor in cabecalhos.items():
        if nome != "Content-Type":
            saida[nome] = valor
    return saida


class EncaminharPedidoMixin:
    """Depois da autenticacao do DRF, troca o handler pelo encaminhamento se ligado."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        configuracao = loja_que_encaminha()
        if configuracao is None:
            return
        # O dispatch do DRF pega o handler DEPOIS do initial: o do objeto vence o da classe.
        for metodo in METODOS:
            setattr(self, metodo,
                    lambda req, *a, **k: encaminhar_requisicao(configuracao, req._request))
