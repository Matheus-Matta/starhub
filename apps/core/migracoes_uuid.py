"""Preenche o `uuid` de registros que ja existiam, para as migrations de cada app.

AddField(default=uuid4) grava o MESMO uuid em todas as linhas antigas (o default e
calculado uma vez), e o indice unico nao nasce. Aqui cada linha ganha o seu, e a
linha do historico (simple_history) recebe o uuid do registro que ela descreve.
Fica fora das migrations para nao repetir o codigo em cada app; nao mude o que ele
faz: migrations ja aplicadas dependem deste comportamento.
"""

import uuid

LOTE = 1000


def _preencher(modelo, uuid_de=None):
    pendentes = modelo.objects.filter(uuid__isnull=True).order_by("pk")
    while True:
        # Sem fatiar por offset: cada volta pega as linhas que ainda estao sem uuid.
        lote = list(pendentes[:LOTE])
        if not lote:
            return
        for linha in lote:
            linha.uuid = (uuid_de or {}).get(linha.id) or uuid.uuid4()
        modelo.objects.bulk_update(lote, ["uuid"])


def preencher_uuid(app_label, *nomes):
    """RunPython que preenche `uuid` nos models `nomes` e nos historicos deles."""

    def preencher(apps, schema_editor):
        for nome in nomes:
            modelo = apps.get_model(app_label, nome)
            _preencher(modelo)
            uuid_de = dict(modelo.objects.values_list("pk", "uuid"))
            _preencher(apps.get_model(app_label, f"Historical{nome}"), uuid_de)

    return preencher
