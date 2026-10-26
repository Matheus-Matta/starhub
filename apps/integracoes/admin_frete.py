"""Card "Frete do hub" das telas do WooCommerce e do Suri Shop (o do Shopify e outro).

    contexto(plataforma, configuracao)   # None quando a plataforma nao tem este card
    ligar(request, plataforma, configuracao, True)

Woo: ligar envia as zonas de entrega (tarefa); desligar tira as zonas do StarHub da
loja. Suri: ligar so marca no hub; o orcamento sai quando o pedido em montagem chega.
"""

from urllib.parse import urljoin

from django.contrib import messages
from django.urls import reverse

from apps.logistica.models import TabelaFrete

TEXTOS = {
    "woocommerce": (
        "As tabelas por faixa de CEP marcadas \"oferecer no checkout\" viram zonas de "
        "entrega \"StarHub ...\" na loja, uma opcao por tabela com o preco do hub. Mudou "
        "uma tabela ou faixa: as zonas sao reenviadas sozinhas. Tabela por distancia "
        "fica de fora (o Woo so compara CEP)."),
    "suri": (
        "A API abaixo devolve ao checkout do Suri todas as tabelas que atendem o CEP. "
        "O fluxo de orcamento do pedido em montagem continua disponivel como alternativa. "
        "Ambos usam as tabelas marcadas \"oferecer no checkout\"."),
}


def _estado(plataforma, configuracao):
    if configuracao is None:
        return False
    if plataforma == "woocommerce":
        from apps.woocommerce.frete_envio import frete_ligado
    else:
        from apps.suri.frete import frete_ligado
    return frete_ligado(configuracao)


def _tabelas(plataforma):
    saida = []
    for tabela in TabelaFrete.objects.filter(active=True, no_checkout=True).order_by("nome"):
        fora = plataforma == "woocommerce" and tabela.tipo == TabelaFrete.Tipo.DISTANCIA
        saida.append({"nome": tabela.nome, "tipo": tabela.get_tipo_display(), "fora": fora})
    return saida


def contexto(plataforma, configuracao, endereco_atual=""):
    if plataforma not in TEXTOS:
        return None
    api = None
    if plataforma == "suri" and configuracao is not None:
        base = configuracao.url_webhook or endereco_atual
        api = {"url": urljoin(base, reverse("suri_logistica", args=[configuracao.uuid])),
               "header_key": "Authorization",
               "header_value": "Bearer SEU_TOKEN_DA_API_DO_SURI"}
    return {"ligado": _estado(plataforma, configuracao), "texto": TEXTOS[plataforma],
            "tabelas": _tabelas(plataforma), "salvo": configuracao is not None, "api": api}


def ligar(request, plataforma, configuracao, ligado):
    if plataforma == "woocommerce":
        from apps.woocommerce.frete_sinais import enfileirar_frete

        enfileirar_frete(configuracao, remover=not ligado)
        texto = ("Envio das zonas de frete para a loja foi para a fila." if ligado else
                 "Remocao das zonas de frete do StarHub foi para a fila.")
    else:
        from apps.suri.frete import ligar_frete

        ligar_frete(configuracao, ligado)
        texto = f"Frete do hub no Suri {'ligado' if ligado else 'desligado'}."
    messages.success(request, texto)
