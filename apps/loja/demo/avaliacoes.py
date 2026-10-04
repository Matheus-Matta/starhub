"""Demo de avaliacoes: pendentes, aprovadas e rejeitadas, algumas com foto.

A foto e um arquivo de verdade no MEDIA (FileField): a imagem demo e copiada uma
vez so e todas as fotos apontam para ela, para o --limpar nao deixar copias.
"""

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.loja.demo import marca
from apps.loja.models import Avaliacao, FotoAvaliacao
from apps.loja.services.avaliacoes import nome_publico

FOTO = "avaliacoes/demo/demo1.png"
STATUS = ["pendente", "aprovada", "aprovada", "rejeitada", "aprovada"]
TEXTOS = [
    "Chegou antes do prazo e bem embalado. Muito confortavel.",
    "Bonito, mas a cor e um pouco mais escura do que na foto.",
    "Montagem simples, o manual ajudou. Recomendo.",
    "Veio com um arranhao na lateral; a loja trocou rapido.",
    "Otimo custo-beneficio, comprei o segundo.",
]


def _foto():
    if not default_storage.exists(FOTO):
        origem = settings.BASE_DIR / "static" / "starhub" / "img" / "demos" / "demo1.png"
        default_storage.save(FOTO, ContentFile(origem.read_bytes()))
    return FOTO


def avaliacoes(clientes, produtos, quantidade):
    agora = timezone.now()
    criadas = []
    for i in range(quantidade):
        status = STATUS[i % len(STATUS)]
        cliente = clientes[i % len(clientes)]
        avaliacao = Avaliacao.objects.create(
            produto=produtos[i // len(clientes) % len(produtos)], cliente=cliente,
            nome_publico=nome_publico(cliente), nota=5 - i % 5, comentario=TEXTOS[i % len(TEXTOS)],
            status=status, compra_verificada=i % 2 == 0, metadados=marca(),
            motivo_rejeicao="Fala de outro produto" if status == "rejeitada" else "",
            moderado_em=agora if status != "pendente" else None,
        )
        FotoAvaliacao.objects.create(avaliacao=avaliacao, imagem=_foto(), metadados=marca())
        criadas.append(avaliacao)
    return criadas
