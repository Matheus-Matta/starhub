from django.db import transaction

from apps.starchats.cliente import ClienteStarChats, ErroStarChats
from apps.starchats.models import ContatoStarChats
from apps.starchats.renderizacao import mapear


def _objeto(resposta):
    atual = resposta.get("payload", resposta) if isinstance(resposta, dict) else resposta
    if isinstance(atual, list):
        return atual[0] if atual else {}
    return atual if isinstance(atual, dict) else {}


def _telefone(cliente):
    digitos = "".join(caractere for caractere in cliente.telefone if caractere.isdigit())
    if not digitos:
        raise ErroStarChats(f"O cliente {cliente} nao possui telefone.")
    if len(digitos) in {10, 11}:
        digitos = f"55{digitos}"
    if not 10 <= len(digitos) <= 15:
        raise ErroStarChats(f"O telefone de {cliente} nao pode ser enviado ao WhatsApp.")
    return f"+{digitos}"


def _criar_contato(api, configuracao, cliente):
    telefone = _telefone(cliente)
    resposta = _objeto(
        api.criar_contato(
            {
                "inbox_id": configuracao.caixa_entrada_id,
                "name": cliente.nome_completo or cliente.email,
                "email": cliente.email,
                "phone_number": telefone,
                "identifier": f"starhub-cliente-{cliente.uuid}",
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
            conversa = _objeto(
                api.criar_conversa(
                    {
                        "source_id": vinculo.origem_externa_id,
                        "inbox_id": configuracao.caixa_entrada_id,
                        "contact_id": int(vinculo.contato_externo_id),
                        "status": "open",
                    }
                )
            )
            if not conversa.get("id"):
                raise ErroStarChats("O StarChats criou a conversa sem devolver o ID.")
            vinculo.conversa_externa_id = str(conversa["id"])
        vinculo.save()
        return vinculo.conversa_externa_id


def enviar_modelo(envio, contexto):
    conjunto = envio.conjunto
    configuracao = conjunto.modelo.configuracao
    api = ClienteStarChats(configuracao)
    conversa_id = _garantir_destino(api, configuracao, envio.cliente)
    modelo = conjunto.modelo
    processados = {"body": envio.parametros}
    cabecalho = mapear(conjunto.parametros_cabecalho, contexto)
    if conjunto.midia_cabecalho_url:
        cabecalho.update(
            {
                "media_url": conjunto.midia_cabecalho_url,
                "media_type": conjunto.midia_cabecalho_tipo,
            }
        )
    if cabecalho:
        processados["header"] = cabecalho
    if conjunto.codigo_botao:
        processados["buttons"] = [
            {"type": "copy_code", "parameter": conjunto.codigo_botao}
        ]
    corpo = {
        "content": envio.conteudo,
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
    return _objeto(api.enviar_mensagem(conversa_id, corpo))
