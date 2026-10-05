"""Aplica o webhook recebido da loja WooCommerce (corpo = o recurso no formato da API).

    processar_webhook(configuracao, "produtos", "update", {"id": 15, ...}, progresso)

create e update usam o mesmo importador da sincronizacao, sem sobrescrever o texto
que o lojista ajustou no hub. update de registro que o hub nao conhece so cria se
Receber > Criar estiver ligado. delete desativa (o hub nunca apaga pedido nem produto
por causa da loja: historico e financeiro ficam).
"""

from apps.loja.models import Cliente, Cupom, Pedido, Produto
from apps.woocommerce import vinculos
from apps.woocommerce.cliente import WooClient
from apps.woocommerce.importar_clientes import importar_cliente
from apps.woocommerce.importar_cupons import importar_cupom
from apps.woocommerce.importar_pedidos import importar_pedido
from apps.woocommerce.sincronizar_produtos import importar_completo

MODELOS = {"produtos": Produto, "clientes": Cliente, "pedidos": Pedido, "cupons": Cupom}


def _importador(configuracao, recurso):
    if recurso == "produtos":
        return lambda dados: importar_completo(WooClient(configuracao), dados)
    if recurso == "pedidos":
        return lambda dados: importar_pedido(dados, configuracao.dominio_loja)
    return {"clientes": importar_cliente, "cupons": importar_cupom}[recurso]


def _desativar(recurso, externo_id):
    obj = vinculos.existente(recurso, MODELOS[recurso], externo_id)
    if obj is None:
        return "Registro ja nao existia."
    obj.active = False  # como no Shopify: some das listas, o historico fica
    obj.save()
    return "Registro desativado."


def processar_webhook(configuracao, recurso, operacao, dados, progresso):
    progresso(0, 1, f"Webhook {recurso}: {operacao}")
    if recurso not in MODELOS:
        mensagem = "Recurso sem webhook no WooCommerce."
    elif operacao == "delete":
        mensagem = _desativar(recurso, dados.get("id"))
    elif (operacao == "update" and not vinculos.objeto_id(recurso, dados.get("id"))
          and not configuracao.habilitado("receber", recurso, "create")):
        mensagem = "Registro nao encontrado; ligue Receber > Criar para cadastrar."
    else:
        obj, criado = _importador(configuracao, recurso)(dados)
        mensagem = ("Registro nao importado (sem e-mail ou codigo)." if obj is None
                    else "Registro criado." if criado else "Registro atualizado.")
    progresso(1, 1, "Webhook processado")
    return mensagem
