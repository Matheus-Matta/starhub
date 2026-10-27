"""Endpoint de logistica que o Suri chama no checkout (GET valida; POST cota)."""

import json
import logging
from hmac import compare_digest

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.core.tenant.context import tenant_context
from apps.logistica.cotacao import FreteIndisponivel, cotar, normalizar_cep
from apps.logistica.models import TabelaFrete
from apps.suri.cliente import json_decimal
from apps.suri.frete import frete_ligado

logger = logging.getLogger(__name__)
ENTREGA = 1


def _json(dados, status=200):
    return HttpResponse(json_decimal(dados), status=status, content_type="application/json")


def _sem_opcoes(status, motivo):
    # O Suri le qualquer corpo como List<ShopLogisticDTO>, ate o de erro: um objeto
    # {"error"} na raiz quebra o checkout. O status diz o erro; o motivo vai pro log.
    logger.warning("Frete do Suri recusado (%s): %s", status, motivo)
    return _json([], status=status)


def _campo(dados, nome):
    return (dados or {}).get(nome) or (dados or {}).get(nome[:1].lower() + nome[1:])


def _autorizado(request, configuracao):
    recebido = request.headers.get("Authorization", "")
    esperado = f"Bearer {configuracao.token_acesso}"
    return bool(configuracao.token_acesso) and compare_digest(recebido, esperado)


def _destino(corpo):
    endereco = _campo(corpo, "Address") or {}
    return (_campo(endereco, "ZipCode") or "", _campo(endereco, "City") or "",
            _campo(endereco, "State") or "")


def _vendedor(corpo):
    itens = _campo(corpo, "Items") or []
    return next((_campo(item, "FromSellerId") for item in itens
                 if _campo(item, "FromSellerId")), "all")


def _opcao(tabela, cotacao, vendedor):
    prazo = f"{cotacao.prazo_dias} dias uteis" if cotacao.prazo_dias else "a combinar"
    return {
        "ProviderId": f"HUB_{tabela.pk}", "Name": tabela.nome,
        "FromSellerId": vendedor, "Type": ENTREGA, "Price": cotacao.valor,
        "Description": cotacao.detalhe or tabela.nome, "ListPrice": cotacao.valor,
        "PriceWithoutDiscount": cotacao.valor, "DiscountAmount": cotacao.valor * 0,
        "CompanyName": tabela.nome, "MinShippingTimeEstimative": prazo,
        "ShippingTimeEstimative": prazo,
    }


def _opcoes(corpo):
    cep, cidade, uf = _destino(corpo)
    cep = normalizar_cep(cep)
    vendedor, opcoes = _vendedor(corpo), []
    tabelas = TabelaFrete.objects.filter(active=True, no_checkout=True).prefetch_related(
        "faixas").order_by("nome")
    for tabela in tabelas:
        try:
            opcoes.append(_opcao(tabela, cotar(tabela, cep, cidade=cidade, uf=uf), vendedor))
        except FreteIndisponivel:
            continue
        except Exception:  # noqa: BLE001 - uma tabela com defeito nao esconde as demais
            logger.exception("Frete do Suri falhou na tabela %s para o CEP %s", tabela.pk, cep)
    return sorted(opcoes, key=lambda opcao: (opcao["Price"], opcao["Name"]))


@csrf_exempt
def consultar_logistica(request, configuracao_uuid):
    from apps.integracoes.models import ConfiguracaoIntegracao

    configuracao = ConfiguracaoIntegracao.all_objects.filter(
        uuid=configuracao_uuid, plataforma=ConfiguracaoIntegracao.Plataforma.SURI,
        active=True).first()
    if configuracao is None:
        return _sem_opcoes(404, "integracao Suri inexistente ou desligada; confira a URL.")
    if not _autorizado(request, configuracao):
        return _sem_opcoes(401, "Authorization diferente do token da loja; confira os "
                                "headers adicionais no Suri.")
    if request.method == "GET":
        # A documentacao diz que o corpo da validacao e ignorado, mas algumas versoes
        # do Suri tentam desserializa-lo como a mesma lista de opcoes usada no POST.
        return _json([])
    if request.method != "POST":
        resposta = _sem_opcoes(405, f"metodo {request.method}; use GET ou POST.")
        resposta["Allow"] = "GET, POST"
        return resposta
    if not frete_ligado(configuracao):
        return _json([])
    try:
        corpo = json.loads(request.body or b"null")
        if not isinstance(corpo, dict):
            raise ValueError
        with tenant_context(configuracao.account_id):
            opcoes = _opcoes(corpo)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return _sem_opcoes(400, "corpo nao e um objeto JSON com Items e Address.")
    except FreteIndisponivel as erro:
        logger.info("Frete do Suri indisponivel: %s", erro)
        return _json([])
    return _json(opcoes)
