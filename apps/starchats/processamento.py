from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.loja.models import Cliente, Pedido
from apps.starchats.contexto import montar
from apps.starchats.envio import enviar_modelo
from apps.starchats.models import ConfiguracaoStarChats, ConjuntoEnvio, EnvioStarChats
from apps.starchats.regras import conjunto_atende
from apps.starchats.renderizacao import preparar


def _objeto(tipo, objeto_id):
    if tipo == "cliente":
        cliente = Cliente.objects.get(pk=objeto_id)
        return cliente, cliente, None
    if tipo == "pedido":
        pedido = Pedido.objects.select_related("cliente").get(pk=objeto_id)
        return pedido, pedido.cliente, pedido
    raise ValueError(f"Tipo de evento desconhecido: {tipo}")


def _chave(conjunto, tipo, objeto_id, evento_id):
    base = f"{conjunto.uuid}:{tipo}:{objeto_id}"
    return f"uma-vez:{base}" if conjunto.enviar_uma_vez else f"evento:{evento_id}:{base}"


def _reservar(conjunto, cliente, tipo, objeto_id, evento, evento_id):
    with transaction.atomic():
        envio, criado = EnvioStarChats.objects.get_or_create(
            chave_deduplicacao=_chave(conjunto, tipo, objeto_id, evento_id),
            defaults={
                "account_id": conjunto.account_id,
                "conjunto": conjunto,
                "cliente": cliente,
                "tipo_objeto": tipo,
                "objeto_id": str(objeto_id),
                "evento": evento,
            },
        )
        envio = EnvioStarChats.objects.select_for_update().get(pk=envio.pk)
        recente = timezone.now() - timedelta(minutes=10)
        processando = (
            envio.status == EnvioStarChats.Status.PROCESSANDO
            and envio.processando_em
            and envio.processando_em >= recente
        )
        if not criado and (envio.status == EnvioStarChats.Status.ENVIADO or processando):
            return None
        envio.status = EnvioStarChats.Status.PROCESSANDO
        envio.processando_em = timezone.now()
        envio.erro = ""
        envio.save(update_fields=["status", "processando_em", "erro", "updated_at"])
        return envio


def processar_evento(conta_id, tipo, objeto_id, evento, evento_id):
    objeto, cliente, pedido = _objeto(tipo, objeto_id)
    if cliente is None:
        return 0
    configuracao = ConfiguracaoStarChats.objects.filter(active=True).first()
    if not configuracao or not configuracao.caixa_entrada_id:
        return 0
    conjuntos = ConjuntoEnvio.objects.filter(
        active=True,
        evento=evento,
        modelo__active=True,
        modelo__configuracao=configuracao,
    ).select_related("modelo").prefetch_related("regras")
    contexto = montar(cliente, pedido)
    enviados = 0
    erros = []
    for conjunto in conjuntos:
        if not conjunto_atende(conjunto, contexto):
            continue
        envio = _reservar(conjunto, cliente, tipo, objeto.pk, evento, evento_id)
        if envio is None:
            continue
        envio.conteudo, envio.parametros = preparar(conjunto, contexto)
        envio.save(update_fields=["conteudo", "parametros", "updated_at"])
        try:
            resposta = enviar_modelo(envio, contexto)
            envio.mensagem_externa_id = str(resposta.get("id", ""))
            envio.status = EnvioStarChats.Status.ENVIADO
            envio.enviado_em = timezone.now()
            envio.save(update_fields=["mensagem_externa_id", "status", "enviado_em", "updated_at"])
            enviados += 1
        except Exception as erro:  # gravar a falha antes de a tarefa pedir nova tentativa
            envio.status = EnvioStarChats.Status.FALHOU
            envio.erro = str(erro)[:2000]
            envio.save(update_fields=["status", "erro", "updated_at"])
            erros.append(erro)
    if erros:
        raise erros[0]
    return enviados
