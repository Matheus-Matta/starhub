"""Marketplaces que sabem receber alteracoes do hub.

Cada app de marketplace registra a sua classe no `ready()`; o Distribuidor so
envia para configuracoes cuja plataforma esta aqui (uma loja cadastrada sem
enviador pronto nao recebe nada, em vez de quebrar a tarefa).
"""

_classes = {}


def registrar(classe):
    """Decorator: `@registrar class ShopifyMarketplace(Marketplace)`."""
    if not classe.plataforma:
        raise ValueError(f"{classe.__name__} precisa definir `plataforma` para ser registrado.")
    _classes[classe.plataforma] = classe
    return classe


def desregistrar(plataforma):
    """So para testes: tira um marketplace falso do registro."""
    _classes.pop(plataforma, None)


def obter(plataforma):
    return _classes.get(plataforma)


def plataformas():
    return list(_classes)
