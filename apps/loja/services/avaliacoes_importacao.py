"""Uma linha da planilha de avaliacoes -> cliente + avaliacao (o lojista criando as suas).

Colunas: email, nome, sobrenome, sku (ou produto_id), nota, comentario e, opcionais,
nome_publico, status (aprovada | pendente | rejeitada; vazio = aprovada, porque quem
importa e o proprio lojista) e data (dd/mm/aaaa ou aaaa-mm-dd).

- Cliente e achado pelo e-mail; se nao existe, nasce so no hub (`_sem_envio`): ele
  existe para assinar a avaliacao, nao para virar conta e e-mail na loja.
- Mesmo cliente + mesmo produto atualiza a avaliacao em vez de duplicar: importar a
  planilha corrigida de novo e seguro. A rejeitada fica de historico e nao e tocada.
- O save() leva a aprovada para a loja (o mesmo envio da moderacao).
"""

from datetime import datetime, time

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import Origin
from apps.integracoes.importar_planilha import LinhaInvalida
from apps.loja.models import Avaliacao, Cliente, VarianteProduto
from apps.loja.services.avaliacoes import (
    AvaliacaoInvalida,
    _comentario,
    _nota,
    nome_publico,
    pedido_que_comprova,
)

Status = Avaliacao.Status
STATUS = {"": Status.APROVADA, "aprovada": Status.APROVADA, "aprovado": Status.APROVADA,
          "pendente": Status.PENDENTE, "rejeitada": Status.REJEITADA,
          "rejeitado": Status.REJEITADA}
FORMATOS_DATA = ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y")
# Cabecalho escrito a mao: "E-mail" vira e_mail (planilha.coluna), "Estrelas" e a nota...
APELIDOS = {"e_mail": "email", "mail": "email", "estrelas": "nota", "texto": "comentario",
            "avaliacao": "comentario", "codigo": "sku", "sku_do_produto": "sku"}


def _cliente(dados):
    email = dados.get("email", "").strip().lower()
    try:
        validate_email(email)
    except ValidationError as erro:
        raise LinhaInvalida(f"e-mail invalido ou vazio: '{email}'.") from erro
    cliente = Cliente.objects.filter(email_normalizado=email.casefold()).first()
    if cliente is None:
        cliente = Cliente(email=email, nome=dados.get("nome", "")[:150],
                          sobrenome=dados.get("sobrenome", "")[:150], origin=Origin.IMPORT)
        cliente._sem_envio = True
        try:
            with transaction.atomic():
                cliente.save()
        except IntegrityError:  # outra linha/tarefa criou o mesmo e-mail agora
            cliente = Cliente.objects.get(email_normalizado=email.casefold())
    return cliente


def _produto(dados):
    sku, produto_id = dados.get("sku", ""), dados.get("produto_id", "")
    consulta = VarianteProduto.objects.select_related("produto")
    variante = None
    if sku:
        variante = consulta.filter(sku__iexact=sku).order_by("pk").first()
    elif produto_id.isdigit():
        variante = consulta.filter(produto_id=int(produto_id)).order_by("pk").first()
    if variante is None:
        raise LinhaInvalida(f"produto nao encontrado (sku '{sku or produto_id}'); confira o SKU.")
    produto = variante.produto
    if not produto.avaliacoes_permitidas:
        raise LinhaInvalida(f"o produto '{produto.nome}' nao aceita avaliacoes; ligue no produto.")
    return produto


def _data(texto):
    if not texto:
        return None
    for formato in FORMATOS_DATA:
        try:
            dia = datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
        return timezone.make_aware(datetime.combine(dia, time(12)))
    raise LinhaInvalida(f"data '{texto}' fora do formato dd/mm/aaaa.")


def _status(texto):
    chave = texto.strip().lower()
    if chave not in STATUS:
        raise LinhaInvalida(f"status '{texto}' desconhecido; use aprovada, pendente ou rejeitada.")
    return STATUS[chave]


def importar_linha(dados, usuario=None):
    """(avaliacao, criada) da linha; LinhaInvalida com o motivo se nao der."""
    dados = {APELIDOS.get(chave, chave): valor for chave, valor in dados.items()}
    try:
        nota, comentario = _nota(dados.get("nota")), _comentario(dados.get("comentario"))
    except AvaliacaoInvalida as erro:
        raise LinhaInvalida(str(erro)) from erro
    status, quando = _status(dados.get("status", "")), _data(dados.get("data", ""))
    cliente, produto = _cliente(dados), _produto(dados)
    pedido = pedido_que_comprova(cliente, produto)
    campos = {
        "nota": nota, "comentario": comentario, "status": status,
        "nome_publico": (dados.get("nome_publico") or nome_publico(cliente))[:80],
        "compra_verificada": pedido is not None, "pedido": pedido,
        "moderado_em": None if status == Status.PENDENTE else timezone.now(),
        "moderado_por": usuario if getattr(usuario, "pk", None) else None,
    }
    with transaction.atomic():
        avaliacao = (Avaliacao.objects.select_for_update().filter(cliente=cliente, produto=produto)
                     .exclude(status=Status.REJEITADA).first())
        criada = avaliacao is None
        if criada:
            avaliacao = Avaliacao(cliente=cliente, produto=produto, origin=Origin.IMPORT)
        for campo, valor in campos.items():
            setattr(avaliacao, campo, valor)
        avaliacao.save()  # save, nao update(): a aprovada precisa ir para a loja
        if quando:
            # created_at e auto_now_add: a data da planilha entra depois, sem novo envio.
            Avaliacao.objects.filter(pk=avaliacao.pk).update(created_at=quando)
    return avaliacao, criada
