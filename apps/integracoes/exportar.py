"""Exportar (StarHub -> marketplace): reenvia os registros da conta, recurso por recurso.

Generico: usa o Marketplace registrado da plataforma (envio/registro.py) e o mesmo
`enviar` do envio automatico, entao as regras de vinculo, lock e permissao valem
iguais. Roda dentro da tarefa `exportar_dados`, com a origem = plataforma destino.
"""

import logging

from apps.integracoes import falhas
from apps.integracoes.envio import registro
from apps.integracoes.envio.base import EnvioNaoSuportado

# Categoria antes de produto (o produto aponta para a colecao) e produto antes do
# estoque (a variante precisa existir la); pedido por ultimo, depois do cliente.
ORDEM = ("categorias", "produtos", "estoque", "clientes", "cupons", "pedidos")
MAX_IDS = 20

logger = logging.getLogger(__name__)


def _vinculados(enviador):
    return set(enviador._referencias().values_list("object_id", flat=True))


def _registros(enviador, conta_id):
    consulta = enviador.modelo.all_objects.filter(account_id=conta_id)
    if enviador.recurso == "estoque":
        consulta = consulta.filter(manage_inventory=True)
    pks = [str(pk) for pk in consulta.order_by("pk").values_list("pk", flat=True)]
    if enviador.recurso == "pedidos":
        # Pedido nasce no marketplace; exportar so atualiza os que ja estao vinculados.
        vinculados = _vinculados(enviador)
        pks = [pk for pk in pks if pk in vinculados]
    return pks


class Resumo:
    def __init__(self):
        self.enviados = self.ignorados = 0
        self.falhas = {}  # recurso -> [pk]
        self.detalhes = []  # falhas.item(...) por registro, para a tabela do admin
        self.primeiro_erro = ""
        self.sem_enviador = []

    @property
    def total_falhas(self):
        return sum(len(pks) for pks in self.falhas.values())

    def falhou(self, recurso, pk, erro, enviador=None):
        motivo = falhas.motivo_legivel(erro)
        self.falhas.setdefault(recurso, []).append(pk)
        self.primeiro_erro = self.primeiro_erro or f"{recurso} {pk}: {motivo}"
        if len(self.detalhes) < falhas.MAX_FALHAS:
            self.detalhes.append(falhas.item(recurso, motivo, pk, *_identificar(enviador, pk)))

    def status(self):
        return falhas.status_final(self.enviados + self.ignorados, self.detalhes)

    def texto(self):
        partes = [f"{self.enviados} enviados", f"{self.ignorados} ignorados"]
        total_falhas = self.total_falhas
        texto = ", ".join(partes)
        if total_falhas:
            restantes = MAX_IDS
            grupos = []
            for recurso, pks in self.falhas.items():
                if restantes <= 0:
                    break
                grupos.append(f"{recurso} {', '.join(pks[:restantes])}")
                restantes -= len(pks[:restantes])
            extra = " ..." if total_falhas > MAX_IDS else ""
            texto += f", {total_falhas} falharam: {'; '.join(grupos)}{extra}"
            texto += f". Primeiro erro: {self.primeiro_erro}"
            texto += (". Veja a lista de falhas nesta tarefa, corrija cada item e "
                      "exporte de novo so os dados que falharam")
        if self.sem_enviador:
            texto += f". Sem envio para esta plataforma: {', '.join(self.sem_enviador)}"
        return texto[:4000]


def _identificar(enviador, pk):
    """(descricao, id externo) do registro que falhou; vazio se nem isso der para ler."""
    if enviador is None:
        return "", ""
    try:
        return falhas.descrever(enviador._carregar(pk)), enviador.referencia(pk) or ""
    except Exception:  # detalhe da falha nao pode derrubar a exportacao dos outros
        logger.warning("Nao foi possivel identificar %s %s", enviador.recurso, pk, exc_info=True)
        return "", ""


def exportar_dados(configuracao, recursos, progresso):
    classe = registro.obter(configuracao.plataforma)
    if classe is None:
        raise EnvioNaoSuportado(
            f"O StarHub ainda nao envia dados para {configuracao.plataforma}."
        )
    marketplace = classe(configuracao)
    resumo = Resumo()
    plano = []
    for recurso in ORDEM:
        if recurso not in recursos:
            continue
        enviador = marketplace.enviador(recurso)
        if enviador is None:
            resumo.sem_enviador.append(recurso)
            continue
        plano.append((recurso, enviador, _registros(enviador, configuracao.account_id)))
    total = sum(len(pks) for _r, _e, pks in plano)
    feitos = 0
    progresso(0, total, "Preparando a exportacao")
    for recurso, enviador, pks in plano:
        vinculados = _vinculados(enviador)
        for pk in pks:
            _enviar(marketplace, recurso, pk, pk in vinculados, resumo)
            feitos += 1
            progresso(feitos, total, f"Exportando {recurso} ({feitos}/{total})")
    return resumo


def _enviar(marketplace, recurso, pk, vinculado, resumo):
    operacao = "update" if vinculado else "create"
    try:
        mensagem = marketplace.enviar(recurso, operacao, pk)
    except EnvioNaoSuportado:
        resumo.ignorados += 1
        return
    except Exception as erro:  # um registro com erro nao para os outros; fica no resumo
        logger.warning("Exportar %s %s falhou: %s", recurso, pk, erro)
        resumo.falhou(recurso, pk, erro, marketplace.enviador(recurso))
        return
    if str(mensagem).startswith("ignorado"):
        resumo.ignorados += 1
    else:
        resumo.enviados += 1

