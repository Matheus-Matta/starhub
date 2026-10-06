"""Catalogo dos eventos que podem notificar, e o texto de cada aviso.

    evento_de(Pedido, "criado")        # "pedido.criado"
    aviso(pedido, "criado")            # {"evento", "titulo", "mensagem", "link"}

Um grupo por model (criado, alterado, excluido) mais a tarefa de integracao que falhou.
A tela de configuracao mostra os eventos nesta ordem; o que nao esta aqui nao avisa.
"""

from django.urls import NoReverseMatch, reverse

from apps.loja.models import Avaliacao, Categoria, Cliente, Cupom, Pedido, Produto

ACOES = ("criado", "alterado", "excluido")
FEMININOS = {"Categoria", "Avaliacao"}
# model -> (prefixo do evento, nome no texto do aviso, grupo na tela)
MODELOS = {
    Pedido: ("pedido", "Pedido", "Pedidos"),
    Produto: ("produto", "Produto", "Produtos"),
    Cliente: ("cliente", "Cliente", "Clientes"),
    Categoria: ("categoria", "Categoria", "Categorias"),
    Cupom: ("cupom", "Cupom", "Cupons"),
    Avaliacao: ("avaliacao", "Avaliacao", "Avaliacoes"),
}
TAREFA_FALHOU = "tarefa.falhou"
PERMISSAO_TAREFA = "integracoes.view_execucaointegracao"
CANAIS = (("navegador", "Navegador"), ("email", "E-mail"))


def _rotulo(nome, acao):
    return acao[:-1] + "a" if nome in FEMININOS else acao  # "Categoria criada"


def catalogo():
    """[(grupo, [(evento, rotulo)])] na ordem da tela."""
    grupos = [(grupo, [(f"{prefixo}.{acao}", f"{nome} {_rotulo(nome, acao)}") for acao in ACOES])
              for prefixo, nome, grupo in MODELOS.values()]
    grupos.append(("Tarefas de integracao",
                   [(TAREFA_FALHOU, "Tarefa falhou ou terminou com falhas")]))
    return grupos


EVENTOS = {evento for _, itens in catalogo() for evento, _ in itens}


def permissao(evento):
    """Permissao de ver o registro do evento: so quem a tem recebe o aviso no navegador."""
    if evento == TAREFA_FALHOU:
        return PERMISSAO_TAREFA
    prefixo = evento.split(".", 1)[0]
    modelo = next((m for m, dados in MODELOS.items() if dados[0] == prefixo), None)
    return f"{modelo._meta.app_label}.view_{modelo._meta.model_name}" if modelo else None


def evento_de(modelo, acao):
    prefixo = MODELOS.get(modelo, (None,))[0]
    return f"{prefixo}.{acao}" if prefixo else None


def _link(obj, excluido):
    if excluido:
        return ""
    opcoes = obj._meta
    try:
        return reverse(f"admin:{opcoes.app_label}_{opcoes.model_name}_change", args=[obj.pk])
    except NoReverseMatch:
        return ""


def _descricao(obj):
    if isinstance(obj, Pedido):
        return f"#{obj.number} - R$ {obj.total} - {obj.get_status_display()}"
    return str(obj)


def aviso(obj, acao):
    nome = MODELOS[type(obj)][1]
    return {"evento": evento_de(type(obj), acao),
            "titulo": f"{nome} {_rotulo(nome, acao)}"[:200],
            "mensagem": _descricao(obj)[:500],
            "link": _link(obj, acao == "excluido")}


def aviso_de_tarefa(execucao):
    return {"evento": TAREFA_FALHOU,
            "titulo": f"Tarefa #{execucao.pk} {execucao.get_status_display().lower()}"[:200],
            "mensagem": f"{execucao.get_tipo_display()}: {execucao.mensagem}"[:500],
            "link": reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk])}
