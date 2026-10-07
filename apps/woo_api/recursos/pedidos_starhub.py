"""meta_data "starhub" do PEDIDO na saida da API: o que o ERP le no nivel do pedido.

    {"key": "starhub", "value": {"origem": {...}, "cliente": {...},
        "entrega": {"agendamento": "15-10-2026", "tipo": "delivery"},
        "cupons": [...], "idVendedor": 12}}

- servicos nao saem aqui: vao no item (pedidos_servicos.py);
- agendamento sai dd-mm-aaaa, seja qual for o formato que a origem mandou;
- idVendedor e o numero configurado na integracao da plataforma de origem do
  pedido; sem numero configurado o campo nao sai.
"""

from datetime import date, datetime

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.services.extras_pedido import CHAVE

# Como as origens escrevem a data do agendamento (Shopify: texto livre do checkout).
_FORMATOS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y")


def data_brasileira(valor):
    """"2026-10-15", "15/10/2026" ou ISO com hora -> "15-10-2026"; texto que nao e
    data ("a combinar") sai como veio, para o ERP nao receber uma data inventada."""
    texto = str(valor or "").strip()
    dia = None
    for formato in _FORMATOS:
        try:
            dia = datetime.strptime(texto, formato).date()
            break
        except ValueError:
            continue
    if dia is None:
        try:
            # A data como a origem escreveu, sem converter fuso: e o dia combinado.
            dia = datetime.fromisoformat(texto).date()
        except ValueError:
            return valor
    return dia.strftime("%d-%m-%Y") if isinstance(dia, date) else valor


def id_vendedor(pedido):
    return (ConfiguracaoIntegracao.all_objects
            .filter(account_id=pedido.account_id, plataforma=pedido.origin)
            .values_list("id_vendedor", flat=True).first())


def _valor(valor, vendedor):
    valor = {chave: v for chave, v in valor.items() if chave != "servicos"}
    entrega = valor.get("entrega")
    if isinstance(entrega, dict) and entrega.get("agendamento"):
        valor["entrega"] = {**entrega, "agendamento": data_brasileira(entrega["agendamento"])}
    if vendedor is not None:
        valor["idVendedor"] = int(vendedor)
    return valor


def meta_do_pedido(pedido):
    """meta_data do pedido pronto para o ERP; starhub vazio nao sai."""
    vendedor = id_vendedor(pedido)
    saida, achou = [], False
    for meta in pedido.metadados or []:
        if meta.get("key") == CHAVE and isinstance(meta.get("value"), dict):
            achou = True
            valor = _valor(meta["value"], vendedor)
            if not valor:
                continue
            meta = {**meta, "value": valor}
        saida.append(meta)
    if not achou and vendedor is not None:
        proximo = max((meta.get("id", 0) for meta in saida), default=0) + 1
        saida.append({"id": proximo, "key": CHAVE, "value": {"idVendedor": int(vendedor)}})
    return saida
