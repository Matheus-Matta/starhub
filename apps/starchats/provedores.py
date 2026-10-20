from dataclasses import dataclass
from typing import Callable


class ErroProvedorMensagens(Exception):
    """Falha temporaria que pode ser repetida pela tarefa de envio."""


@dataclass(frozen=True)
class ProvedorMensagens:
    disponivel: Callable
    enviar: Callable


# Cada app de WhatsApp registra seu adaptador no ready(). O motor comum conhece
# somente este contrato e nao precisa importar clientes de APIs futuras.
provedores: dict[str, ProvedorMensagens] = {}


def registrar(codigo, *, disponivel, enviar):
    provedores[codigo] = ProvedorMensagens(
        disponivel=disponivel,
        enviar=enviar,
    )


def obter(codigo):
    return provedores.get(codigo)
