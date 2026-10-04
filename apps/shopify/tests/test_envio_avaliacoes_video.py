"""Video da avaliacao: a Shopify so baixa imagem por URL; video sobe por staged upload."""

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.shopify.envio import avaliacoes_video
from apps.shopify.tests.test_envio_avaliacoes import _avaliacao, cenario  # noqa: F401

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 32

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def test_video_sobe_por_staged_upload_e_vira_video_na_loja(cenario, monkeypatch):  # noqa: F811
    enviador, loja, produto = cenario
    subidos = []
    monkeypatch.setattr(avaliacoes_video, "_postar", lambda alvo, foto: subidos.append(
        (alvo["url"], foto.imagem.name)))
    video = SimpleUploadedFile("v.mp4", MP4, content_type="video/mp4")
    avaliacao = _avaliacao(produto, fotos=[video])

    assert enviador.enviar("update", avaliacao.pk).startswith("publicada")

    pedido = loja.ultima("stagedUploadsCreate")["input"][0]
    assert pedido["resource"] == "VIDEO" and pedido["mimeType"] == "video/mp4"
    assert subidos and subidos[0][0] == "https://upload.test/video"
    criado = loja.ultima("fileCreate")["files"][0]
    assert criado == {"originalSource": "https://upload.test/recurso/v", "contentType": "VIDEO",
                      "alt": "Video da avaliacao de Ana L."}
    campos = {c["key"]: c["value"] for c in loja.ultima("metaobjectUpsert")["metaobject"]["fields"]}
    assert json.loads(campos["photos"]) == ["gid://shopify/Video/1"]
