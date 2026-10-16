from django.utils import timezone

from apps.starchats.cliente import ClienteStarChats
from apps.starchats.models import ModeloMensagem


def _lista(resposta):
    if isinstance(resposta, list):
        return resposta
    return resposta.get("payload", []) if isinstance(resposta, dict) else []


def _eh_whatsapp(caixa):
    valores = " ".join(
        str(caixa.get(chave, ""))
        for chave in ("channel_type", "provider", "provider_name", "medium")
    ).casefold()
    return "whatsapp" in valores or ("twilio" in valores and "sms" not in valores)


def _corpo(componentes):
    corpo = next(
        (
            item
            for item in componentes
            if isinstance(item, dict) and str(item.get("type", "")).upper() == "BODY"
        ),
        {},
    )
    return corpo.get("text", "")


def sincronizar(configuracao):
    api = ClienteStarChats(configuracao)
    caixas = [caixa for caixa in _lista(api.caixas()) if _eh_whatsapp(caixa)]
    configuracao.caixas_disponiveis = [
        {"id": caixa.get("id"), "nome": caixa.get("name", f"Caixa {caixa.get('id')}")}
        for caixa in caixas
    ]
    ids = {item["id"] for item in configuracao.caixas_disponiveis}
    if configuracao.caixa_entrada_id not in ids:
        configuracao.caixa_entrada_id = next(iter(ids), None) if len(ids) == 1 else None
    escolhida = next(
        (item for item in configuracao.caixas_disponiveis
         if item["id"] == configuracao.caixa_entrada_id),
        None,
    )
    configuracao.caixa_entrada_nome = escolhida["nome"] if escolhida else ""
    if configuracao.caixa_entrada_id:
        _sincronizar_modelos(configuracao, _lista(api.modelos(configuracao.caixa_entrada_id)))
    configuracao.sincronizado_em = timezone.now()
    configuracao.ultimo_erro = ""
    configuracao.save()
    return len(caixas)


def _sincronizar_modelos(configuracao, modelos):
    ModeloMensagem.objects.filter(configuracao=configuracao).update(active=False)
    for item in modelos:
        componentes = item.get("components") or []
        componentes = componentes if isinstance(componentes, list) else []
        situacao = item.get("status", "")
        ModeloMensagem.objects.update_or_create(
            configuracao=configuracao,
            caixa_entrada_id=configuracao.caixa_entrada_id,
            nome=item.get("name", ""),
            idioma=item.get("language", ""),
            defaults={
                "account_id": configuracao.account_id,
                "identificador_externo": str(item.get("id", "")),
                "categoria": item.get("category", ""),
                "situacao": situacao,
                "conteudo": _corpo(componentes),
                "componentes": componentes,
                "active": not situacao or str(situacao).upper() == "APPROVED",
            },
        )
