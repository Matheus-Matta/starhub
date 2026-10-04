"""Video da avaliacao na loja (Files).

A Shopify so baixa IMAGEM por URL externa; video tem de subir antes por staged
upload: pede um destino (stagedUploadsCreate), manda o arquivo para ele e cria o
arquivo com o resourceUrl. O processamento do video na Shopify continua sozinho.
"""

import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.loja.services.midias_avaliacao import mime_do_video
from apps.shopify import consultas_avaliacoes as q
from apps.shopify.cliente import ShopifyErro

TEMPO_ENVIO = 120  # segundos: video de ate 50 MB


def _multipart(campos, nome, conteudo, mime):
    limite = uuid.uuid4().hex
    partes = []
    for chave, valor in campos:
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{chave}"\r\n\r\n'
                      f"{valor}\r\n".encode())
    # O arquivo vai por ultimo: o storage da Shopify ignora campos depois dele.
    partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="file"; '
                  f'filename="{nome}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    partes.append(conteudo)
    partes.append(f"\r\n--{limite}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def _postar(alvo, foto):
    nome = foto.imagem.name.rsplit("/", 1)[-1]
    with foto.imagem.open("rb") as arquivo:
        conteudo = arquivo.read()
    campos = [(p["name"], p["value"]) for p in alvo["parameters"]]
    corpo, tipo = _multipart(campos, nome, conteudo, mime_do_video(nome))
    try:
        with urlopen(Request(alvo["url"], data=corpo, method="POST",
                             headers={"Content-Type": tipo}), timeout=TEMPO_ENVIO):
            pass
    except HTTPError as erro:
        detalhe = erro.read().decode(errors="replace")[:300]
        raise ShopifyErro(f"A Shopify recusou o video (HTTP {erro.code}): {detalhe}") from erro
    except (URLError, TimeoutError) as erro:
        raise ShopifyErro(f"Nao foi possivel enviar o video para a Shopify: {erro}") from erro


def criar(enviador, foto, alt):
    """Gid do Video criado na loja a partir do arquivo da avaliacao."""
    nome = foto.imagem.name.rsplit("/", 1)[-1]
    destino = enviador.mutacao(q.SUBIR_ARQUIVO, {"input": [{
        "resource": "VIDEO", "filename": nome, "mimeType": mime_do_video(nome),
        "fileSize": str(foto.imagem.size), "httpMethod": "POST",
    }]}, "stagedUploadsCreate")["stagedTargets"][0]
    _postar(destino, foto)
    criados = enviador.mutacao(q.CRIAR_ARQUIVOS, {"files": [{
        "originalSource": destino["resourceUrl"], "contentType": "VIDEO", "alt": alt,
    }]}, "fileCreate")
    return criados["files"][0]["id"]
