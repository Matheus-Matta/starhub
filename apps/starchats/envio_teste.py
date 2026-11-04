from apps.starchats.cliente import ClienteStarChats, ErroStarChats
from apps.starchats.envio import _objeto, conversa_teste, corpo_modelo
from apps.starchats.renderizacao import preparar

CONTEXTO_TESTE = {
    "cliente": {
        "nome": "Cliente",
        "sobrenome": "de teste",
        "nome_completo": "Cliente de teste",
        "email": "cliente@teste.invalid",
        "telefone": "5511999999999",
        "cpf": "00000000000",
        "cnpj": "",
        "empresa": "Empresa de teste",
        "nascimento": "2000-01-01",
        "aceita_marketing": True,
        "cliente_pagante": True,
    },
    "pedido": {
        "numero": "TESTE-001",
        "status": "processing",
        "status_pagamento": "paid",
        "status_entrega": "unfulfilled",
        "total": "100.00",
        "forma_pagamento": "Pix",
        "metodo_envio": "Entrega padrao",
        "canal_origem": "StarHub",
    },
}


def enviar_teste(conjunto, numero):
    configuracao = conjunto.modelo.configuracao
    if not configuracao or not configuracao.active or not configuracao.caixa_entrada_id:
        raise ErroStarChats("Configure e ative a caixa do StarChats antes do envio de teste.")
    conteudo, parametros = preparar(conjunto, CONTEXTO_TESTE)
    api = ClienteStarChats(configuracao)
    conversa_id = conversa_teste(api, configuracao, numero)
    corpo = corpo_modelo(conjunto, conteudo, parametros, CONTEXTO_TESTE)
    return _objeto(api.enviar_mensagem(conversa_id, corpo))
