from django.db import transaction

from apps.starchats.cliente import ClienteStarChats, ErroStarChats
from apps.starchats.models import ContatoStarChats
from apps.starchats.renderizacao import mapear
from apps.starchats.telefones import NumeroInvalido, numero_whatsapp


def _objeto(resposta):
    atual = resposta.get("payload", resposta) if isinstance(resposta, dict) else resposta
    if isinstance(atual, list):
        return atual[0] if atual else {}
    return atual if isinstance(atual, dict) else {}


def _telefone(valor, identificacao="destinatario"):
    try:
        return f"+{numero_whatsapp(valor)}"
    except NumeroInvalido as erro:
        raise ErroStarChats(f"O telefone de {identificacao} nao pode ser enviado.") from erro


def _criar_destino(api, configuracao, *, numero, nome, email, identificador):
    telefone = _telefone(numero, nome)
    resposta = _objeto(
        api.criar_contato(
            {
                "inbox_id": configuracao.caixa_entrada_id,
                "name": nome,
                "email": email,
                "phone_number": telefone,
                "identifier": identificador,
            }
        )
    )
    contato = resposta.get("contact", resposta)
    contato_id = contato.get("id")
    vinculo = resposta.get("contact_inbox") or contato.get("contact_inbox") or {}
    origem = vinculo.get("source_id")
    if not contato_id:
        raise ErroStarChats("O StarChats criou o contato sem devolver o ID.")
    if not origem:
        vinculo = _objeto(
            api.vincular_contato(
                contato_id,
                {"inbox_id": configuracao.caixa_entrada_id, "source_id": telefone.lstrip("+")},
            )
        )
        origem = vinculo.get("source_id")
    if not origem:
        raise ErroStarChats("O StarChats nao devolveu a origem do contato no WhatsApp.")
    return str(contato_id), str(origem)


def _criar_contato(api, configuracao, cliente):
    return _criar_destino(
        api,
        configuracao,
        numero=cliente.telefone,
        nome=cliente.nome_completo or cliente.email,
        email=cliente.email,
        identificador=f"starhub-cliente-{cliente.uuid}",
    )


def _criar_conversa(api, configuracao, contato_id, origem):
    conversa = _objeto(
        api.criar_conversa(
            {
                "source_id": origem,
                "inbox_id": configuracao.caixa_entrada_id,
                "contact_id": int(contato_id),
                "status": "open",
            }
        )
    )
    if not conversa.get("id"):
        raise ErroStarChats("O StarChats criou a conversa sem devolver o ID.")
    return str(conversa["id"])


def _garantir_destino(api, configuracao, cliente):
    with transaction.atomic():
        vinculo, _ = ContatoStarChats.objects.get_or_create(
            configuracao=configuracao,
            cliente=cliente,
            defaults={"account_id": configuracao.account_id},
        )
        vinculo = ContatoStarChats.objects.select_for_update().get(pk=vinculo.pk)
        if not vinculo.contato_externo_id:
            vinculo.contato_externo_id, vinculo.origem_externa_id = _criar_contato(
                api, configuracao, cliente
            )
        if not vinculo.conversa_externa_id:
            vinculo.conversa_externa_id = _criar_conversa(
                api,
                configuracao,
                vinculo.contato_externo_id,
                vinculo.origem_externa_id,
            )
        vinculo.save()
        return vinculo.conversa_externa_id


def conversa_teste(api, configuracao, numero):
    digitos = numero_whatsapp(numero)
    contato_id, origem = _criar_destino(
        api,
        configuracao,
        numero=numero,
        nome="Teste StarHub",
        email="",
        identificador=f"starhub-teste-{digitos}",
    )
    return _criar_conversa(api, configuracao, contato_id, origem)


def corpo_modelo(conjunto, conteudo, parametros, contexto):
    modelo = conjunto.modelo
    processados = {"body": parametros}
    cabecalho = mapear(conjunto.parametros_cabecalho, contexto)
    if conjunto.midia_cabecalho_url:
        cabecalho.update({
            "media_url": conjunto.midia_cabecalho_url,
            "media_type": conjunto.midia_cabecalho_tipo,
        })
    if cabecalho:
        processados["header"] = cabecalho
    if conjunto.codigo_botao:
        processados["buttons"] = [{
            "type": "copy_code", "parameter": conjunto.codigo_botao,
        }]
    return {
        "content": conteudo,
        "message_type": "outgoing",
        "private": False,
        "content_type": "text",
        "template_params": {
            "name": modelo.nome,
            "category": modelo.categoria,
            "language": modelo.idioma,
            "processed_params": processados,
        },
    }


def enviar_modelo(envio, contexto):
    conjunto = envio.conjunto
    configuracao = conjunto.modelo.configuracao
    api = ClienteStarChats(configuracao)
    conversa_id = _garantir_destino(api, configuracao, envio.cliente)
    corpo = corpo_modelo(conjunto, envio.conteudo, envio.parametros, contexto)
    return _objeto(api.enviar_mensagem(conversa_id, corpo))
