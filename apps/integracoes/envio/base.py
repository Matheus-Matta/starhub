"""Classes base do envio de alteracoes do hub para um marketplace.

Um marketplace novo herda `Marketplace` (lista os recursos que sabe enviar) e um
`EnviadorRecurso` por recurso (implementa criar/atualizar/excluir). A base cuida
do vinculo com o id externo (ExternalReference) e de decidir qual das tres chamar.
"""

from django.db import transaction

from apps.core.models import ExternalReference


class EnvioNaoSuportado(Exception):
    """Operacao que o marketplace nao aceita: registrada como ignorada, nao como falha."""


class EnviadorRecurso:
    recurso = ""  # "produtos" | "estoque" | "categorias" | "clientes" | "pedidos" | "cupons"...
    entidade = ""  # entity_type do ExternalReference (vazio = recurso)
    modelo = None  # classe do model canonico (apps.loja.models...)

    def __init__(self, marketplace):
        self.marketplace = marketplace

    @property
    def configuracao(self):
        return self.marketplace.configuracao

    @property
    def plataforma(self):
        return self.marketplace.plataforma

    def _entidade(self):
        return self.entidade or self.recurso

    # A subclasse implementa o que o marketplace aceita.

    def criar(self, obj):
        """Cria no marketplace e devolve o id externo."""
        raise EnvioNaoSuportado(f"{self.plataforma} nao cria {self.recurso}.")

    def atualizar(self, obj, external_id):
        raise EnvioNaoSuportado(f"{self.plataforma} nao atualiza {self.recurso}.")

    def excluir(self, external_id):
        raise EnvioNaoSuportado(f"{self.plataforma} nao exclui {self.recurso}.")

    # Vinculo hub <-> marketplace.

    def _referencias(self):
        return ExternalReference.all_objects.filter(
            account_id=self.configuracao.account_id,
            platform=self.plataforma,
            entity_type=self._entidade(),
        )

    def referencia(self, pk):
        return self._referencias().filter(object_id=str(pk)).values_list(
            "external_id", flat=True
        ).first()

    def vincular(self, obj, external_id):
        # A chave e o id externo (indice unico referencia_externa_unica): dois envios
        # que criarem ao mesmo tempo nao deixam dois registros apontando para ele.
        ExternalReference.all_objects.update_or_create(
            account_id=self.configuracao.account_id,
            platform=self.plataforma,
            entity_type=self._entidade(),
            external_id=str(external_id),
            defaults={"object_id": str(obj.pk), "origin": self.plataforma},
        )

    def desvincular(self, pk):
        self._referencias().filter(object_id=str(pk)).delete()

    # Orquestracao.

    def _carregar(self, pk, travar=False):
        consulta = self.modelo.all_objects
        if travar:
            consulta = consulta.select_for_update()
        return consulta.filter(account_id=self.configuracao.account_id, pk=pk).first()

    def _carregar_travado(self, pk):
        # Lock so para criar: dois envios do mesmo registro sem vinculo (create e update
        # em workers diferentes) nao podem os dois criar no marketplace. O segundo
        # espera o primeiro gravar o vinculo.
        return self._carregar(pk, travar=True)

    def enviar(self, operacao, pk):
        if operacao == "delete":
            return self._excluir(pk)
        obj = self._carregar(pk)
        if obj is None:
            return "ignorado: o registro nao existe mais no hub"
        external_id = self.referencia(pk)
        if external_id:
            # Sem lock: o envio manda o estado atual (valor absoluto), entao envios fora
            # de ordem convergem; travar aqui fazia a baixa de estoque de um pedido
            # esperar o timeout do marketplace.
            self.atualizar(obj, external_id)
            return "atualizado"
        with transaction.atomic():
            obj = self._carregar_travado(pk)
            if obj is None:
                return "ignorado: o registro nao existe mais no hub"
            # Relido depois do lock: o envio anterior pode ter acabado de vincular.
            external_id = self.referencia(pk)
            if external_id:
                self.atualizar(obj, external_id)
                return "atualizado"
            if operacao != "create" and not self.marketplace.habilitado(self.recurso, "create"):
                return (
                    f"ignorado: sem vinculo no {self.plataforma} e 'criar' esta desligado; "
                    "ligue Enviar > criar ou sincronize a loja para vincular."
                )
            external_id = self.criar(obj)
            self.vincular(obj, external_id)
            return f"criado {external_id}"

    def _excluir(self, pk):
        external_id = self.referencia(pk)
        if not external_id:
            return f"ignorado: sem vinculo no {self.plataforma}"
        self.excluir(external_id)
        self.desvincular(pk)
        return "excluido"


class Marketplace:
    plataforma = ""  # igual a ConfiguracaoIntegracao.Plataforma e ao codigo de origem
    recursos = ()  # subclasses de EnviadorRecurso

    def __init__(self, configuracao):
        self.configuracao = configuracao
        self._enviadores = {}

    def habilitado(self, recurso, operacao):
        return self.configuracao.habilitado("enviar", recurso, operacao)

    def enviador(self, recurso):
        if recurso not in self._enviadores:
            classe = next((c for c in self.recursos if c.recurso == recurso), None)
            self._enviadores[recurso] = classe(self) if classe else None
        return self._enviadores[recurso]

    def enviar(self, recurso, operacao, pk):
        # Conferido de novo aqui: a configuracao pode ter sido desligada entre o
        # save e a tarefa rodar (fila do Celery, retry).
        if not self.habilitado(recurso, operacao):
            return f"ignorado: Enviar > {recurso} > {operacao} esta desligado"
        enviador = self.enviador(recurso)
        if enviador is None:
            raise EnvioNaoSuportado(f"{self.plataforma} nao recebe {recurso}.")
        return enviador.enviar(operacao, pk)
