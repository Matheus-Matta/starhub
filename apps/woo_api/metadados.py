"""meta_data do Woo: lista de {"id", "key", "value"}.

No envio o ERP manda {"key", "value"} (ou com "id" para trocar um existente).
Mesma chave sem id atualiza o primeiro com aquela chave, como o update_meta_data
do WooCommerce.
"""

from decimal import Decimal

from apps.woo_api.erros import parametro_invalido


def _serializar_value(value):
    """meta_data e dado opaco do ERP, nao dinheiro do hub. Valores numericos sao
    devolvidos como numeros, igual ao WooCommerce: Decimal inteiro vira int,
    Decimal com casas vira float. Strings continuam strings.
    """
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    return value


def mesclar(atuais, novos):
    if novos is None:
        return atuais
    if not isinstance(novos, list):
        raise parametro_invalido("meta_data", "meta_data nao e do tipo array.")
    lista = [dict(item) for item in (atuais or [])]
    proximo_id = max((item.get("id", 0) for item in lista), default=0) + 1
    for novo in novos:
        if not isinstance(novo, dict) or "key" not in novo and "id" not in novo:
            raise parametro_invalido("meta_data", "Cada item precisa de key e value.")
        alvo = None
        if novo.get("id"):
            alvo = next((i for i in lista if i.get("id") == novo["id"]), None)
        if alvo is None and "key" in novo:
            alvo = next((i for i in lista if i.get("key") == novo["key"]), None)
        if alvo is not None:
            alvo["key"] = novo.get("key", alvo["key"])
            alvo["value"] = _serializar_value(novo.get("value"))
            continue
        if "key" not in novo:
            raise parametro_invalido("meta_data", f"Metadado id {novo.get('id')} nao existe.")
        value = _serializar_value(novo.get("value"))
        lista.append({"id": proximo_id, "key": novo["key"], "value": value})
        proximo_id += 1
    return lista
