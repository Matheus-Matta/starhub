from apps.shopify.models import ApresentacaoServicoShopify

Apresentacao = ApresentacaoServicoShopify
TIPOS_EM_GRUPO = {
    Apresentacao.TipoCampo.RADIO,
    Apresentacao.TipoCampo.LISTA,
    Apresentacao.TipoCampo.CARTOES,
}


def _opcao(item, configuracao, **grupo):
    tipo = grupo.get("tipo_campo")
    return {
        **item,
        "rotulo": configuracao.rotulo if configuracao and configuracao.rotulo else item["nome"],
        "descricao": configuracao.descricao if configuracao else "",
        "ordem": grupo.get("ordem", configuracao.ordem if configuracao else 10),
        "tipo_campo": tipo or Apresentacao.TipoCampo.CHECKBOX,
        "grupo": grupo.get("grupo", ""),
        "titulo_grupo": grupo.get("titulo_grupo", ""),
        "obrigatorio": grupo.get("obrigatorio", False),
        "selecionado": grupo.get("selecionado", False),
    }


def _configuracoes(ids):
    return {
        configuracao.servico_id: configuracao
        for configuracao in Apresentacao.objects.filter(
            servico_id__in=ids).prefetch_related("servicos_vinculados")
    }


def aplicar_layout(servicos):
    """Resolve pares apenas entre os servicos que realmente valem para o produto."""
    por_id = {item["id"]: item for item in servicos}
    configuracoes = _configuracoes(por_id)
    usados = set()
    saida = []
    grupos = sorted(configuracoes.values(), key=lambda item: (item.ordem, item.pk))

    for configuracao in grupos:
        principal = configuracao.servico_id
        vinculados = [item.pk for item in configuracao.servicos_vinculados.all()
                      if item.pk in por_id and item.pk not in usados]
        if (configuracao.tipo_campo not in TIPOS_EM_GRUPO or principal not in por_id
                or principal in usados or not vinculados):
            continue
        dados_grupo = {
            "tipo_campo": configuracao.tipo_campo,
            "grupo": f"servicos-{configuracao.pk}",
            "titulo_grupo": configuracao.titulo_grupo,
            "obrigatorio": configuracao.obrigatorio,
            "ordem": configuracao.ordem,
        }
        padrao = configuracao.padrao
        ids_grupo = [principal, *vinculados]
        for indice, servico_id in enumerate(ids_grupo):
            selecionado = (
                padrao == Apresentacao.Padrao.PRINCIPAL and indice == 0
                or padrao == Apresentacao.Padrao.ALTERNATIVO and indice == 1)
            saida.append(_opcao(
                por_id[servico_id], configuracoes.get(servico_id), **dados_grupo,
                selecionado=selecionado))
        usados.update(ids_grupo)

    restantes = []
    for servico_id, item in por_id.items():
        if servico_id in usados:
            continue
        configuracao = configuracoes.get(servico_id)
        tipo = configuracao.tipo_campo if configuracao else Apresentacao.TipoCampo.CHECKBOX
        # Radio/Lista sem o outro servico no produto nao pode continuar exclusivo.
        if tipo in (Apresentacao.TipoCampo.RADIO, Apresentacao.TipoCampo.LISTA):
            tipo = Apresentacao.TipoCampo.CHECKBOX
            obrigatorio = selecionado = False
        else:
            obrigatorio = configuracao.obrigatorio if configuracao else False
            selecionado = bool(
                configuracao and configuracao.padrao == Apresentacao.Padrao.PRINCIPAL)
        restantes.append(_opcao(
            item, configuracao, tipo_campo=tipo, obrigatorio=obrigatorio,
            selecionado=selecionado))
    saida.extend(sorted(restantes, key=lambda item: (item["ordem"], item["nome"])))
    return saida
