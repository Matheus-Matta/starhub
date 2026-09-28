"""Regras de dominio do Sprint Log: unicidade por conta, variantes, bundle e FKs."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.core.models import Address
from apps.core.tenant.context import tenant_context
from apps.core.tenant.exceptions import TenantMismatchError
from apps.loja.models import (
    Cliente,
    ItemBundle,
    Pedido,
    Produto,
    TipoVariante,
    ValorDaVarianteProduto,
    ValorVariante,
    VarianteProduto,
)
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


def test_mesmo_email_e_permitido_em_outra_conta_e_barrado_na_mesma(outra_conta):
    Cliente.objects.create(email="contato@cliente.test")
    with tenant_context(outra_conta):
        Cliente.objects.create(email="contato@cliente.test")
    with pytest.raises(IntegrityError):
        Cliente.objects.create(email="CONTATO@cliente.test")


def test_cpf_e_email_repetido_viram_erro_amigavel_no_formulario():
    Cliente.objects.create(email="ana@cliente.test")
    cliente = Cliente(email="ana@cliente.test", cpf="111.111.111-11", telefone="12")
    with pytest.raises(ValidationError) as erro:
        cliente.full_clean(exclude=["account"])
    assert set(erro.value.message_dict) >= {"email", "cpf", "telefone"}


def test_cpf_valido_e_gravado_sem_mascara():
    cliente = Cliente.objects.create(email="a@b.test", cpf="529.982.247-25")
    assert cliente.cpf == "52998224725"


def _opcoes(tipo_nome, *valores, posicao=0):
    tipo, _ = TipoVariante.objects.get_or_create(nome=tipo_nome, defaults={"posicao": posicao})
    return [ValorVariante.objects.get_or_create(tipo=tipo, valor=valor, defaults={"posicao": n})[0]
            for n, valor in enumerate(valores)]


def test_tipo_de_variante_e_global_e_cada_variante_escolhe_o_valor():
    """A Cor e cadastrada uma vez e serve a camiseta e a caneca, cada uma com o seu valor."""
    preto, branco = _opcoes("Cor", "Preto", "Branco")
    for nome, valor in (("Camiseta", preto), ("Caneca", branco)):
        produto = Produto.objects.create(nome=nome, tipo=Produto.Tipo.VARIAVEL)
        variante = VarianteProduto.objects.create(produto=produto, titulo=valor.valor)
        ValorDaVarianteProduto.objects.create(variante=variante, valor=valor)
    assert TipoVariante.objects.count() == 1
    assert ValorDaVarianteProduto.objects.filter(valor__tipo__nome="Cor").count() == 2
    with pytest.raises(IntegrityError):
        TipoVariante.objects.create(nome="Cor")  # um "Cor" por conta


def test_variante_nao_tem_dois_valores_do_mesmo_tipo():
    produto = Produto.objects.create(nome="Camiseta", tipo=Produto.Tipo.VARIAVEL)
    preto, branco = _opcoes("Cor", "Preto", "Branco")
    variante = VarianteProduto.objects.create(produto=produto, titulo="Preto")
    ValorDaVarianteProduto.objects.create(variante=variante, valor=preto)
    with pytest.raises(ValidationError):
        ValorDaVarianteProduto(variante=variante, valor=branco).clean()


def test_componente_so_entra_em_produto_do_tipo_bundle():
    mouse = criar_produto("Mouse", sku="MOU-1")
    kit = Produto.objects.create(nome="Kit Gamer", tipo=Produto.Tipo.BUNDLE)
    ItemBundle(bundle_product=kit, component_variant=mouse.variante_padrao, quantity=1).clean()
    with pytest.raises(ValidationError):
        ItemBundle(bundle_product=mouse, component_variant=mouse.variante_padrao).clean()


def test_cep_brasileiro_invalido_e_recusado_e_o_valido_e_normalizado():
    with pytest.raises(ValidationError):
        Address(country_code="br", postal_code="5003").clean()
    Address(country_code="US", postal_code="94105-1234").clean()  # internacional passa
    endereco = Address.objects.create(country_code="br", postal_code="50030-230")
    assert (endereco.country_code, endereco.postal_code) == ("BR", "50030230")


def test_pedido_nao_aceita_cliente_de_outra_conta(outra_conta):
    with tenant_context(outra_conta):
        cliente_b = Cliente.objects.create(email="b@outra.test")
    with pytest.raises(TenantMismatchError):
        Pedido.objects.create(cliente=cliente_b)


def test_produto_que_nao_e_variavel_tem_uma_variante_so():
    """O usuario cadastra a variante do produto simples; a segunda e recusada."""
    produto = Produto.objects.create(nome="Caneca", tipo=Produto.Tipo.SIMPLES)
    produto.variantes.all().delete()  # o manager cria a padrao (API); aqui o admin nao cria
    primeira = VarianteProduto.objects.create(produto=produto, titulo="Default")
    assert primeira.is_default  # a primeira vira a padrao sozinha
    segunda = VarianteProduto(produto=produto, titulo="Outra")
    with pytest.raises(ValidationError) as erro:
        segunda.full_clean(exclude=["account"])
    assert "Variavel" in str(erro.value.message_dict["produto"])


def test_produto_variavel_aceita_varias_e_nao_volta_a_simples_com_elas():
    produto = Produto.objects.create(nome="Camiseta", tipo=Produto.Tipo.VARIAVEL)
    VarianteProduto.objects.create(produto=produto, titulo="P")
    outra = VarianteProduto(produto=produto, titulo="M")
    outra.full_clean(exclude=["account"])
    outra.save()
    produto.tipo = Produto.Tipo.SIMPLES
    with pytest.raises(ValidationError) as erro:
        produto.full_clean(exclude=["account"])
    assert "tipo" in erro.value.message_dict


def test_bundle_nao_precisa_de_variante():
    kit = Produto.objects.create(nome="Kit", tipo=Produto.Tipo.BUNDLE)
    kit.variantes.all().delete()
    kit.full_clean(exclude=["account"])


def _componente(kit, nome, estoque, quantidade, controla=True):
    variante = criar_produto(nome, sku=nome.upper(), inventory_quantity=estoque,
                             manage_inventory=controla).variante_padrao
    ItemBundle.objects.create(bundle_product=kit, component_variant=variante, quantity=quantidade)
    return variante


def test_estoque_do_bundle_e_o_do_componente_que_acaba_primeiro():
    """Kit = 1 mouse + 2 pilhas; 10 mouses e 6 pilhas -> 3 kits, limitado pelas pilhas."""
    kit = Produto.objects.create(nome="Kit", tipo=Produto.Tipo.BUNDLE)
    _componente(kit, "Mouse", 10, 1)
    pilha = _componente(kit, "Pilha", 6, 2)
    _componente(kit, "Manual", 0, 1, controla=False)  # sem controle de estoque: nao limita
    assert kit.estoque_do_bundle() == (3, pilha)
    assert (kit.estoque, kit.situacao_estoque) == (3, "instock")
    pilha.inventory_quantity = 1
    pilha.save()
    assert (kit.estoque, kit.situacao_estoque) == (0, "outofstock")


def test_variante_do_bundle_nao_controla_estoque_proprio():
    kit = Produto.objects.create(nome="Kit", tipo=Produto.Tipo.BUNDLE)
    kit.variantes.all().delete()
    variante = VarianteProduto.objects.create(produto=kit, titulo="Default", price=99)
    assert variante.manage_inventory is False
