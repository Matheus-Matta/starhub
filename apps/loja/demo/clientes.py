"""Demo de clientes (CPF/CNPJ validos, enderecos de cobranca e entrega) e cupons."""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.loja.demo import DOMINIO_EMAIL, marca
from apps.loja.demo.documentos import cnpj, cpf
from apps.loja.demo.nucleo import PESSOAS
from apps.loja.models import Cliente, Cupom
from apps.loja.services.clientes import gravar_endereco_do_cliente

# (cidade, UF, CEP, bairro, rua)
CIDADES = [("Recife", "PE", "50030-230", "Boa Vista", "Rua da Aurora"),
           ("Sao Paulo", "SP", "01310-100", "Bela Vista", "Avenida Paulista"),
           ("Rio de Janeiro", "RJ", "22021-001", "Copacabana", "Avenida Atlantica"),
           ("Belo Horizonte", "MG", "30130-010", "Centro", "Avenida Afonso Pena"),
           ("Curitiba", "PR", "80020-010", "Centro", "Rua XV de Novembro")]
# (nome, tipo, valor, extras): cada cupom mostra um recurso diferente.
CUPONS = [
    ("10% na loja toda", "percentage", "10", {}),
    ("20% acima de R$ 200", "percentage", "20",
     {"minimum_requirement": "subtotal", "minimum_subtotal": Decimal("200")}),
    ("Frete gratis", "free_shipping", "0", {"free_shipping": True}),
    ("R$ 50 acima de R$ 300", "fixed_amount", "50",
     {"minimum_requirement": "subtotal", "minimum_subtotal": Decimal("300")}),
    ("15% na primeira compra", "percentage", "15", {"first_order_only": True}),
    ("5% levando 3 itens", "percentage", "5",
     {"minimum_requirement": "quantity", "minimum_quantity": 3}),
    ("Black Friday", "percentage", "30", {"usage_limit": 100}),
    ("R$ 25 no Natal", "fixed_amount", "25", {"status": "draft"}),
    ("12% em moda", "percentage", "12", {"product_eligibility": "categories"}),
    ("R$ 40 para clientes VIP", "fixed_amount", "40",
     {"customer_eligibility": "specific_customers", "status": "paused"}),
]


def _endereco(i, primeiro, ultimo, documento, email, telefone, entrega=False):
    cidade, uf, cep, bairro, rua = CIDADES[(i + entrega) % len(CIDADES)]
    return {"first_name": primeiro, "last_name": ultimo, "address_1": rua,
            "number": str(100 + i * 7), "neighborhood": bairro, "city": cidade, "state": uf,
            "postcode": cep, "country": "BR", "email": email, "phone": telefone,
            "address_2": "Apto 101" if entrega else "", "cpf": documento}


def clientes(quantidade):
    criados = []
    for i in range(quantidade):
        primeiro, ultimo = PESSOAS[i % len(PESSOAS)]
        empresa = i % 5 == 4  # um em cada cinco compra como empresa (CNPJ)
        email = f"{primeiro.lower()}.{ultimo.lower()}{i + 1}@{DOMINIO_EMAIL}"
        telefone = f"81 9{8000_0000 + i * 1111:08d}"
        cliente = Cliente.objects.create(
            email=email, nome=primeiro, sobrenome=ultimo, telefone=telefone,
            tipo_documento="cnpj" if empresa else "cpf",
            cpf="" if empresa else cpf(i + 1), cnpj=cnpj(i + 1) if empresa else "",
            empresa=f"{ultimo} Comercio Ltda" if empresa else "",
            nascimento=date(1980 + i % 20, i % 12 + 1, i % 27 + 1),
            aceita_marketing=i % 2 == 0, notas="Cliente de demonstracao.", metadados=marca(),
        )
        documento = cliente.cnpj or cliente.cpf
        for tipo, entrega in (("billing", False), ("shipping", True)):
            endereco = gravar_endereco_do_cliente(
                cliente, tipo, _endereco(i, primeiro, ultimo, documento, email, telefone, entrega)
            )
            endereco.metadados = marca()
            endereco.save()
        criados.append(cliente)
    return criados


def cupons(quantidade, clientes_criados, categorias_criadas):
    agora = timezone.now()
    for i in range(quantidade):
        nome, tipo, valor, extras = CUPONS[i % len(CUPONS)]
        extras = dict(extras)  # copia: o pop abaixo nao pode mexer na lista do modulo
        status = extras.pop("status", "active")
        if i >= len(CUPONS):
            # O nome identifica o cupom na conta (indice unico): a segunda volta numera.
            nome = f"{nome} ({i // len(CUPONS) + 1})"
        cupom = Cupom.objects.create(
            name=nome, discount_type=tipo, value=Decimal(valor),
            status=status,
            starts_at=agora - timedelta(days=10), ends_at=agora + timedelta(days=20 + i),
            description=f"Cupom de demonstracao: {nome}.", metadados=marca(), **extras,
        )
        if cupom.product_eligibility == "categories":
            cupom.categorias.set([categorias_criadas["Moda"], categorias_criadas["Calcados"]])
        if cupom.customer_eligibility == "specific_customers":
            cupom.clientes.set(clientes_criados[:3])
