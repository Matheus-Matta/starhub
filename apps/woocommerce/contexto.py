"""Loja e avisos da tarefa do WooCommerce em andamento (apps/integracoes/contexto.py)."""

from apps.integracoes.contexto import ContextoMarketplace

_contexto = ContextoMarketplace("woocommerce")
configuracao_atual = _contexto.configuracao_atual
usando_configuracao = _contexto.usando_configuracao
avisar = _contexto.avisar
coletando_avisos = _contexto.coletando_avisos
ambiente = _contexto.ambiente
