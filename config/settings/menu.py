"""Menu lateral do admin: icone de cada model, secoes agrupadas, ordem e paginas extras.

Lido por apps/core/ui/menu.py. Separado do base.py so por tamanho (regra das 200 linhas).
"""

# Menu lateral do admin (apps/core/ui/menu.py). Cada app vira uma SECAO com
# separador; cada model e um item com o proprio icone (id do simbolo em
# static/starhub/img/icones.svg). Chave: "app_label.model_name".
STARHUB_MENU_ICONES = {
    "loja.produto": "package",
    "loja.categoria": "layout-list",
    "loja.cliente": "users-round",
    "loja.pedido": "clipboard-list",
    "loja.tag": "star",
    "loja.cupom": "wallet",
    "loja.avaliacao": "message-square-text",
    "logistica.tabelafrete": "truck",
    "loja.tipovariante": "layout-grid",
    "loja.varianteproduto": "archive",
    "core.account": "house",
    "core.user": "user",
    "core.accessprofile": "shield",
    "core.address": "folder",
    "integracoes.configuracaointegracao": "marca:shopify",
    "integracoes.execucaointegracao": "history",
    "notificacoes.configuracaoemail": "mail",
    "notificacoes.configuracaonotificacao": "bell",
    "woo_api.chaveapi": "key-round",
}
# Models de um app que aparecem na secao de outro: {"app_origem": "app_destino"} move o
# app inteiro; {"app.model": "app_destino"} move so aquele model.
# As chaves da API Woo sao credencial de acesso da conta, entao ficam junto de
# contas, usuarios e perfis de acesso (app core).
STARHUB_MENU_AGRUPAR = {
    "woo_api": "core",
    # Tarefas rodam integracoes e importacoes de planilha: ficam no Nucleo; a secao
    # Integracoes fica so com a configuracao de cada plataforma.
    "integracoes.execucaointegracao": "core",
    # E-mail (SMTP) e Notificacoes sao configuracao da conta: Nucleo.
    "notificacoes": "core",
}
# Fluxo operacional primeiro; auditoria fica no final para nao disputar atencao.
STARHUB_MENU_ORDEM = ["loja", "logistica", "integracoes", "core", "auditlog"]
# Paginas custom (sem model) no menu: {"app_label": [("Titulo", "admin:nome_url")]}.
# Pagina do admin sem model proprio: {app: [(titulo, nome da url, icone opcional)]}.
STARHUB_MENU_PAGINAS = {
    "integracoes": [("WooCommerce", "admin:integracoes_configuracaointegracao_woocommerce",
                     "marca:woocommerce"),
                    ("Suri Shop", "admin:integracoes_configuracaointegracao_suri",
                     "marca:suri")],
}
