"""{% componente %}: include com "slot", o que o {% include %} do Django nao tem.

Exemplo de uso num template:

    {% componente "card" titulo="Pedidos recentes" icone="clipboard-list" %}
      {% slot "acoes" %}<a class="btn btn-sm btn-outline" href="...">Ver todos</a>{% endslot %}
      <p>Conteudo do card.</p>
    {% endcomponente %}

Dentro de templates/components/card.html o conteudo chega como {{ slot }} e o
bloco nomeado como {{ slots.acoes }}.
"""

from django import template
from django.template.base import token_kwargs


class SlotNode(template.Node):
    def __init__(self, nome, nodelist):
        self.nome = nome
        self.nodelist = nodelist

    def render(self, context):
        # O slot nomeado sai no lugar dele dentro do componente, nao aqui.
        return ""


class ComponenteNode(template.Node):
    def __init__(self, nome, kwargs, nodelist):
        self.nome = nome
        self.kwargs = kwargs
        self.nodelist = nodelist

    def render(self, context):
        valores = {chave: valor.resolve(context) for chave, valor in self.kwargs.items()}
        # So os slots do nivel de cima: slot de componente aninhado e dele.
        slots = {
            no.nome: no.nodelist.render(context)
            for no in self.nodelist
            if isinstance(no, SlotNode)
        }
        valores["slot"] = self.nodelist.render(context)
        valores["slots"] = slots
        nome = self.nome.resolve(context)
        modelo = context.template.engine.get_template(f"components/{nome}.html")
        with context.push(**valores):
            return modelo.render(context)


def componente(parser, token):
    bits = token.split_contents()
    if len(bits) < 2:
        raise template.TemplateSyntaxError('Uso: {% componente "nome" chave=valor %}')
    nome = parser.compile_filter(bits[1])
    kwargs = token_kwargs(bits[2:], parser)
    if len(kwargs) != len(bits[2:]):
        raise template.TemplateSyntaxError("{% componente %} aceita apenas chave=valor.")
    nodelist = parser.parse(("endcomponente",))
    parser.delete_first_token()
    return ComponenteNode(nome, kwargs, nodelist)


def slot(parser, token):
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError('Uso: {% slot "nome" %}...{% endslot %}')
    nodelist = parser.parse(("endslot",))
    parser.delete_first_token()
    return SlotNode(bits[1].strip("\"'"), nodelist)
