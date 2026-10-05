"""Recursos no formato da API REST v3 do WooCommerce (dados inventados)."""


def produto_simples(**extra):
    return {"id": 15, "name": "Sofa Azul", "slug": "sofa-azul", "type": "simple",
            "status": "publish", "featured": False, "catalog_visibility": "visible",
            "description": "<p>Sofa</p>", "short_description": "Sofa curto", "sku": "SOFA-1",
            "regular_price": "1999.90", "sale_price": "1799.90", "manage_stock": True,
            "stock_quantity": 7, "stock_status": "instock", "backorders": "no",
            "weight": "30.5", "categories": [{"id": 9, "name": "Sofas", "slug": "sofas"}],
            "tags": [{"id": 3, "name": "Sala", "slug": "sala"}], "images": [], **extra}


def produto_variavel():
    return {"id": 20, "name": "Camiseta", "slug": "camiseta", "type": "variable",
            "status": "publish", "description": "", "short_description": "", "sku": "",
            "categories": [], "tags": [], "images": [], "variations": [21, 22]}


def variacao(id_, cor, sku, preco, estoque):
    return {"id": id_, "sku": sku, "regular_price": preco, "sale_price": "",
            "manage_stock": True, "stock_quantity": estoque, "stock_status": "instock",
            "attributes": [{"id": 1, "name": "Cor", "option": cor}], "image": None}


def endereco(**extra):
    return {"first_name": "Ana", "last_name": "Souza", "company": "", "address_1": "Rua A",
            "address_2": "", "city": "Recife", "state": "PE", "postcode": "50000-000",
            "country": "BR", "number": "100", "neighborhood": "Centro", **extra}


def cliente():
    return {"id": 7, "email": "ana@exemplo.test", "first_name": "Ana", "last_name": "Souza",
            "username": "ana", "role": "customer", "is_paying_customer": True,
            "billing": endereco(email="ana@exemplo.test", phone="81999998888",
                                cpf="529.982.247-25", persontype="1"),
            "shipping": endereco()}


def pedido(**extra):
    return {"id": 501, "number": "501", "status": "processing", "currency": "BRL",
            "prices_include_tax": False, "date_created_gmt": "2026-10-01T12:00:00",
            "date_paid_gmt": "2026-10-01T12:05:00", "date_completed_gmt": None,
            "customer_id": 7, "customer_note": "Entregar a tarde",
            "billing": endereco(email="ana@exemplo.test", phone="81999998888"),
            "shipping": endereco(), "payment_method": "pix",
            "payment_method_title": "Pix", "transaction_id": "TX-1",
            "line_items": [{"id": 1001, "name": "Sofa Azul", "product_id": 15,
                            "variation_id": 0, "quantity": 2, "sku": "SOFA-1",
                            "price": 1799.9, "subtotal": "3599.80", "subtotal_tax": "0.00",
                            "total": "3239.82", "total_tax": "0.00"}],
            "shipping_lines": [{"id": 2001, "method_id": "flat_rate",
                                "method_title": "Entrega", "total": "50.00",
                                "total_tax": "0.00"}],
            "fee_lines": [], "coupon_lines": [{"id": 3001, "code": "promo10",
                                               "discount": "359.98", "discount_tax": "0"}],
            **extra}
