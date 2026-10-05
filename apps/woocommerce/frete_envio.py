"""Leva as zonas de entrega do hub (frete.py) para a loja WooCommerce.

    enviar_frete(configuracao, progresso)    # cria/atualiza as zonas "StarHub ..."
    remover_frete(configuracao, progresso)   # tira so as zonas do StarHub

So mexe em zona com nome "StarHub <cep>-<cep>": as zonas que o lojista criou na mao
ficam. Zona que continua igual de nome tem os metodos trocados no lugar (o cliente
nao fica sem frete entre apagar e criar). O vinculo "frete" (com o id da
configuracao) marca que o frete esta ligado: e ele que faz a mudanca de tabela
reenviar as zonas sozinha (frete_sinais.py).
"""

from apps.core.models import ExternalReference, Origin
from apps.woocommerce.cliente import WooClient
from apps.woocommerce.contexto import avisar
from apps.woocommerce.frete import zonas_desejadas

PREFIXO = "StarHub "


def nome_da_zona(zona):
    return f"{PREFIXO}{zona['inicio']}-{zona['fim']}"


def _marcar(configuracao, ligado):
    filtro = {"platform": Origin.WOOCOMMERCE, "entity_type": "frete",
              "object_id": str(configuracao.pk)}
    if ligado:
        ExternalReference.objects.get_or_create(**filtro, defaults={
            "external_id": f"frete-{configuracao.pk}", "origin": Origin.WOOCOMMERCE})
    else:
        ExternalReference.objects.filter(**filtro).delete()


def frete_ligado(configuracao):
    return ExternalReference.all_objects.filter(
        platform=Origin.WOOCOMMERCE, entity_type="frete",
        object_id=str(configuracao.pk)).exists()


def _nossas(cliente):
    return {z["name"]: z for z in cliente.get("shipping/zones") or []
            if str(z.get("name", "")).startswith(PREFIXO)}


def _metodos(cliente, zona_id, zona):
    for metodo in cliente.get(f"shipping/zones/{zona_id}/methods") or []:
        cliente.delete(f"shipping/zones/{zona_id}/methods/{metodo['instance_id']}")
    for metodo in zona["metodos"]:
        cliente.post(f"shipping/zones/{zona_id}/methods", {
            "method_id": "flat_rate", "enabled": True,
            "settings": {"title": metodo["titulo"], "cost": metodo["custo"],
                         "tax_status": "none"}})


def enviar_frete(configuracao, progresso):
    cliente = WooClient(configuracao)
    zonas, avisos = zonas_desejadas()
    for aviso in avisos:
        avisar(aviso, recurso="frete")
    existentes = _nossas(cliente)
    desejadas = {nome_da_zona(z): z for z in zonas}
    sobras = [z for nome, z in existentes.items() if nome not in desejadas]
    total, feitos = len(desejadas) + len(sobras), 0
    for nome, zona in desejadas.items():
        zona_id = existentes[nome]["id"] if nome in existentes else \
            cliente.post("shipping/zones", {"name": nome})["id"]
        # O Woo normaliza o CEP do cliente (tira o hifen) antes de comparar a faixa.
        cliente.put(f"shipping/zones/{zona_id}/locations",
                    [{"code": f"{zona['inicio']}...{zona['fim']}", "type": "postcode"}])
        _metodos(cliente, zona_id, zona)
        feitos += 1
        progresso(feitos, total, f"Zona {nome}")
    for zona in sobras:
        cliente.delete(f"shipping/zones/{zona['id']}")
        feitos += 1
        progresso(feitos, total, f"Removendo {zona['name']}")
    _marcar(configuracao, True)
    return (f"{len(desejadas)} zonas de entrega do StarHub na loja; "
            f"{len(sobras)} antigas removidas.")


def remover_frete(configuracao, progresso):
    cliente = WooClient(configuracao)
    nossas = list(_nossas(cliente).values())
    for posicao, zona in enumerate(nossas, start=1):
        cliente.delete(f"shipping/zones/{zona['id']}")
        progresso(posicao, len(nossas), f"Removendo {zona['name']}")
    _marcar(configuracao, False)
    return f"Frete do StarHub desligado: {len(nossas)} zonas removidas da loja."
