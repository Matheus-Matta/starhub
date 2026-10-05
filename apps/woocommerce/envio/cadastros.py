"""Categoria, cliente e cupom do hub -> WooCommerce (products/categories, customers, coupons).

Categoria: a imagem so vai no create (a cada `image.src` o Woo baixa a foto de novo).
Cliente: o e-mail e o usuario so vao no create; o Woo recusa trocar o username.
Cupom: o nome do cupom no hub e o codigo que o cliente digita na loja.
"""

from apps.integracoes.url_publica import url_publica
from apps.loja.dinheiro import texto
from apps.loja.models import Categoria, Cliente, Cupom
from apps.loja.services.clientes import endereco_do_cliente
from apps.loja.services.enderecos import para_woo
from apps.woocommerce import vinculos
from apps.woocommerce.envio.base import RecursoWoo


def _ids(recurso, objetos):
    return [int(i) for i in (vinculos.externo_id(recurso, o.pk) for o in objetos) if i]


class CategoriaWoo(RecursoWoo):
    recurso = entidade = "categorias"
    modelo = Categoria
    rota = "products/categories"

    def corpo(self, obj, criando):
        pai = vinculos.externo_id("categorias", obj.pai_id) if obj.pai_id else None
        corpo = {"name": obj.nome, "slug": obj.slug, "description": obj.descricao,
                 "parent": int(pai) if pai else 0}
        imagem = obj.imagem if isinstance(obj.imagem, dict) else {}
        src = url_publica(self.configuracao, imagem.get("src"))
        if criando and src:
            corpo["image"] = {"src": src, "alt": imagem.get("alt") or ""}
        return corpo


class ClienteWoo(RecursoWoo):
    recurso = entidade = "clientes"
    modelo = Cliente
    rota = "customers"

    def corpo(self, obj, criando):
        corpo = {"first_name": obj.nome, "last_name": obj.sobrenome}
        if criando:
            corpo |= {"email": obj.email, "username": obj.usuario}
        for tipo in ("billing", "shipping"):
            endereco = endereco_do_cliente(obj, tipo)
            if endereco is not None:
                corpo[tipo] = {k: v for k, v in para_woo(endereco, {}).items()
                               if not (tipo == "shipping" and k == "email")}
        if obj.cpf:
            corpo.setdefault("billing", {})["cpf"] = obj.cpf
        return corpo


class CupomWoo(RecursoWoo):
    recurso = entidade = "cupons"
    modelo = Cupom
    rota = "coupons"

    def corpo(self, obj, criando):
        T = Cupom.TipoDesconto
        tipo = "percent" if obj.discount_type == T.PERCENTUAL else "fixed_cart"
        valor = obj.value if obj.discount_type != T.FRETE_GRATIS else None
        return {
            "code": obj.name, "discount_type": tipo, "amount": texto(valor) or "0",
            "description": obj.description,
            "status": "publish" if obj.status == Cupom.Status.ATIVO else "draft",
            "date_expires_gmt": obj.ends_at.strftime("%Y-%m-%dT%H:%M:%S") if obj.ends_at
            else None,
            "individual_use": obj.stacking_policy == Cupom.Combinacao.NAO_COMBINA,
            "usage_limit": obj.usage_limit, "usage_limit_per_user": obj.usage_limit_per_customer,
            "free_shipping": obj.free_shipping or obj.discount_type == T.FRETE_GRATIS,
            "exclude_sale_items": obj.excluir_promocao,
            "minimum_amount": texto(obj.minimum_subtotal) if obj.minimum_requirement ==
            Cupom.RequisitoMinimo.SUBTOTAL else "",
            "product_ids": _ids("produtos", obj.produtos.all()),
            "excluded_product_ids": _ids("produtos", obj.produtos_excluidos.all()),
            "product_categories": _ids("categorias", obj.categorias.all()),
            "excluded_product_categories": _ids("categorias", obj.categorias_excluidas.all()),
        }
