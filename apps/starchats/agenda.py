import uuid

from django.db import transaction


class EventoPendente:
    def __init__(self, chave, evento):
        self.chave = chave
        self.evento = evento
        self.executado = False

    def combinar(self, evento):
        if not self.evento.endswith(".criado"):
            self.evento = evento

    def __call__(self):
        self.executado = True
        conta_id, tipo, objeto_id = self.chave
        from apps.core.tarefas import enfileirar
        from apps.starchats.tasks import enviar_evento_starchats

        enfileirar(
            enviar_evento_starchats,
            conta_id,
            tipo,
            objeto_id,
            self.evento,
            str(uuid.uuid4()),
        )


def _pendentes(conexao):
    lista = conexao.run_on_commit
    salvo = getattr(conexao, "_eventos_starchats", None)
    if salvo is None or salvo[0] is not lista:
        indice = {item.chave: item for _sids, item, *_ in lista if isinstance(item, EventoPendente)}
        salvo = (lista, indice)
        conexao._eventos_starchats = salvo
    return salvo[1]


def agendar(conta_id, tipo, objeto_id, evento):
    conexao = transaction.get_connection()
    chave = (str(conta_id), tipo, objeto_id)
    pendentes = _pendentes(conexao)
    atual = pendentes.get(chave)
    if atual is not None and not atual.executado:
        atual.combinar(evento)
        return
    pendente = EventoPendente(chave, evento)
    pendentes[chave] = pendente
    transaction.on_commit(pendente, robust=True)
