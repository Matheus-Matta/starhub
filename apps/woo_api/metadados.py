"""meta_data do Woo: lista de {"id", "key", "value"}.

No envio o ERP manda {"key", "value"} (ou com "id" para trocar um existente).
Mesma chave sem id atualiza o primeiro com aquela chave, como o update_meta_data
do WooCommerce.
"""

from apps.woo_api.erros import parametro_invalido


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
            alvo["value"] = novo.get("value")
            continue
        if "key" not in novo:
            raise parametro_invalido("meta_data", f"Metadado id {novo.get('id')} nao existe.")
        lista.append({"id": proximo_id, "key": novo["key"], "value": novo.get("value")})
        proximo_id += 1
    return lista
