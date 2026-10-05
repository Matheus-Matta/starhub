"""Suri Shop em memoria no lugar do SuriClient: teste nunca fala com o Suri real.

    loja = SuriFalso(produtos=[...], pedidos=[...]).instalar(monkeypatch)
"""

from decimal import Decimal

from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao

MODULOS = ("apps.suri.cliente", "apps.suri.sincronizar", "apps.suri.webhooks",
           "apps.suri.envio.base", "apps.suri.frete")


class SuriFalso:
    def __init__(self, produtos=(), pedidos=(), categorias=(), lojas=({"id": "48346"},)):
        self.produtos_ = list(produtos)
        self.pedidos_ = list(pedidos)
        self.categorias = list(categorias)
        self.lojas = list(lojas)
        self.chamadas = []

    def instalar(self, monkeypatch):
        for modulo in MODULOS:
            monkeypatch.setattr(f"{modulo}.SuriClient", lambda *_a, **_k: self)
        return self

    def produtos(self):
        return iter(self.produtos_)

    def pedidos(self, desde=None):
        return iter(self.pedidos_)

    def get(self, caminho):
        self.chamadas.append(("GET", caminho, None))
        if caminho == "shop/categories":
            return self.categorias
        if caminho == "shop/stores":
            return self.lojas
        rota, _, item_id = caminho.rpartition("/")
        colecao = {"shop/orders": self.pedidos_, "shop/products": self.produtos_}[rota]
        return next(i for i in colecao if str(i["id"]) == item_id)

    def post(self, caminho, corpo):
        self.chamadas.append(("POST", caminho, corpo))
        return corpo

    def put(self, caminho, corpo=None):
        self.chamadas.append(("PUT", caminho, corpo))
        return corpo

    def delete(self, caminho):
        self.chamadas.append(("DELETE", caminho, None))
        return {}


def configuracao(conta, receber=(), enviar=()):
    matriz = permissoes.matriz_vazia()
    for direcao, ligados in (("receber", receber), ("enviar", enviar)):
        for recurso, operacao in ligados:
            matriz[direcao][recurso][operacao] = True
    cfg = ConfiguracaoIntegracao(
        account=conta, plataforma=ConfiguracaoIntegracao.Plataforma.SURI, nome="Suri Shop",
        dominio_loja="https://cbteste.azurewebsites.net", permissoes=matriz,
        url_webhook="https://hub.test/integracoes/suri/webhook")
    cfg.token_acesso = "token-teste"
    cfg.save()
    return cfg


def produto(**extra):
    """Formato de GET shop/products/<id>; numeros como Decimal (o cliente le assim)."""
    return {"id": "48349", "sku": "CAM", "categoryId": "48348", "subcategoryId": None,
            "isActive": True, "name": "Camiseta", "description": "Algodao",
            "price": Decimal("59.9"), "promotionalPrice": Decimal("0"), "images": [],
            "attributes": [{"name": "Cor", "options": [{"name": "Azul"}, {"name": "Verde"}]}],
            "dimensions": [
                {"sku": "CAM-AZ", "dimensions": {"Cor": "Azul"}, "price": Decimal("49.9"),
                 "stocks": {"48346": {"stock": Decimal("3")}, "48347": {"stock": 2}},
                 "measurements": {"weightInGrams": 250}},
                {"sku": "CAM-VD", "dimensions": {"Cor": "Verde"}, "price": Decimal("59.9"),
                 "stocks": {"48346": {"stock": 0}}}],
            **extra}


def pedido(**extra):
    """Formato de GET shop/orders/<id> (dados inventados)."""
    return {"id": "51807", "friendlyCode": None, "status": 2, "userId": "wp:5585912345678",
            "customer": {"document": "529.982.247-25", "name": "Ana Souza",
                         "email": "ana@exemplo.test", "phone": "5585912345678",
                         "address": {"state": "CE", "city": "Fortaleza", "street": "Rua 3",
                                     "number": "123", "zipCode": "60824-020",
                                     "complement": "", "neighborhood": "Centro"}},
            "logistic": {"providerId": "expressa", "name": "Entrega Expressa",
                         "price": Decimal("10.0"), "status": 0, "storeName": "Loja"},
            "payment": {"providerId": "PAG-1", "method": 3, "status": 1},
            "itemsAmount": Decimal("99.8"), "feeAmount": Decimal("0.0"),
            "discountAmount": Decimal("0.0"), "orderDiscountAmount": Decimal("5.0"),
            "totalAmount": Decimal("104.8"), "coupon": None,
            "items": [{"providerId": "48349", "sku": "CAM-AZ", "name": "Camiseta (Azul)",
                       "quantity": Decimal("2.0"), "unitPrice": Decimal("49.9"),
                       "totalAmout": Decimal("99.8"), "discountAmout": Decimal("0.0"),
                       "subTotalAmount": Decimal("99.8")}],
            "createdDate": "2025-05-20T20:41:55.986096Z",
            "receivedDate": "2025-05-20T22:35:03.611367Z",
            "finalizedDate": "2025-05-20T19:36:59.687001-03:00", "canceledDate": None,
            **extra}
