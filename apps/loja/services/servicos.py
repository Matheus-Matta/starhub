"""Liga os servicos do pedido ao cadastro de Servicos (id e SKU para o ERP).

Os servicos do pedido ficam em starhub.servicos ({"item_id", "sku" do item,
"servico", "opcao", "preco"}). Ao gravar, cada um ganha "servico_id"; servico sem
cadastro nasce na hora, com SKU SERV-<NOME>. Na leitura, servico antigo (sem
servico_id) e achado pelo nome.
"""

from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.models import Servico
from apps.loja.models.servico import sku_do_servico


def _chave(nome):
    return str(nome or "").strip().casefold()


def vincular(servicos):
    """Mesma lista com servico_id em cada servico; cria o cadastro que faltar."""
    saida = []
    for servico in servicos or []:
        if not isinstance(servico, dict) or not _chave(servico.get("servico")):
            saida.append(servico)
            continue
        nome = str(servico["servico"]).strip()
        # get_or_create pela chave unica: dois pedidos com o mesmo servico novo, ao
        # mesmo tempo, terminam no mesmo cadastro (o perdedor relê depois do conflito).
        cadastro, _ = Servico.objects.get_or_create(
            nome_normalizado=_chave(nome), defaults={"nome": nome})
        saida.append({**servico, "servico_id": cadastro.pk})
    return saida


def cadastros(servicos):
    """{servico_id ou nome normalizado: Servico} para os servicos de um pedido."""
    ids = {s.get("servico_id") for s in servicos if isinstance(s, dict) and s.get("servico_id")}
    nomes = {_chave(s.get("servico")) for s in servicos
             if isinstance(s, dict) and not s.get("servico_id")}
    achados = Servico.objects.filter(pk__in=ids) if ids else []
    por_nome = Servico.objects.filter(nome_normalizado__in=nomes) if nomes else []
    return {**{s.pk: s for s in achados}, **{s.nome_normalizado: s for s in por_nome}}


def cadastrar_dos_pedidos(pedido_model, servico_model):
    """Cadastro de cada servico que ja aparece em pedidos (migration 0019).

    Recebe as classes para rodar com os models historicos da migration. So cria
    Servico: os pedidos nao mudam, a leitura acha o cadastro pelo nome.
    """
    vistos = set(servico_model.objects.values_list("account_id", "nome_normalizado"))
    criados = 0
    for conta, metadados in pedido_model.objects.values_list("account_id", "metadados").iterator():
        starhub = next((m.get("value") for m in metadados or []
                        if isinstance(m, dict) and m.get("key") == "starhub"), None)
        servicos = starhub.get("servicos") if isinstance(starhub, dict) else None
        for servico in servicos if isinstance(servicos, list) else []:
            nome = str(servico.get("servico") or "").strip() if isinstance(servico, dict) else ""
            if not nome or (conta, nome.casefold()) in vistos:
                continue
            vistos.add((conta, nome.casefold()))
            servico_model.objects.create(account_id=conta, nome=nome,
                                         nome_normalizado=nome.casefold(),
                                         sku=sku_do_servico(nome))
            criados += 1
    return criados


def preencher_precos_dos_pedidos(pedido_model, servico_model):
    """Servico com preco zero recebe o ultimo preco pago por ele num pedido (migration).

    Servico criado sozinho pelo pedido nascia sem preco. Servico nunca vendido fica
    em zero para o operador preencher. Devolve quantos ganharam preco.
    """
    sem_preco = {s.pk: s for s in servico_model.objects.filter(preco=0)}
    por_nome = {(s.account_id, s.nome_normalizado): s for s in sem_preco.values()}
    ultimo = {}
    for conta, metadados in (pedido_model.objects.order_by("pk")
                             .values_list("account_id", "metadados").iterator()):
        starhub = next((m.get("value") for m in metadados or []
                        if isinstance(m, dict) and m.get("key") == "starhub"), None)
        servicos = starhub.get("servicos") if isinstance(starhub, dict) else None
        for servico in servicos if isinstance(servicos, list) else []:
            if not isinstance(servico, dict):
                continue
            cadastro = sem_preco.get(servico.get("servico_id")) or por_nome.get(
                (conta, _chave(servico.get("servico"))))
            preco = _preco_valido(servico.get("preco"))
            if cadastro and preco:
                ultimo[cadastro.pk] = preco  # pedido mais novo por ultimo: ele vence
    for pk, preco in ultimo.items():
        servico_model.objects.filter(pk=pk).update(preco=preco)
    return len(ultimo)


def _preco_valido(valor):
    try:
        preco = dinheiro(valor)
    except ValorInvalido:
        return None
    return preco if preco and preco > 0 else None


def do_cadastro(servico, mapa):
    return mapa.get(servico.get("servico_id")) or mapa.get(_chave(servico.get("servico")))
