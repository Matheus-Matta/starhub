"""O que todo recurso (produto, categoria, cliente, pedido) tem em comum.

Cada recurso diz: qual model, como filtrar a listagem, como virar JSON do Woo
(`para_woo`) e como gravar o JSON recebido (`gravar`). As views sao genericas.
"""

from django.db.models import Q

from apps.woo_api import datas
from apps.woo_api.erros import WooErro, id_invalido, parametro_invalido


def lista_de_ids(params, nome):
    bruto = params.get(nome) or ""
    try:
        return [int(parte) for parte in str(bruto).split(",") if parte.strip()]
    except ValueError as erro:
        raise parametro_invalido(nome, f"{nome} deve ser uma lista de inteiros.") from erro


def booleano(valor, campo):
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in ("true", "1", "yes", "sim"):
        return True
    if texto in ("false", "0", "no", "nao", ""):
        return False
    raise parametro_invalido(campo, f"{campo} nao e do tipo boolean.")


def inteiro(valor, campo, permitir_nulo=False):
    if valor in (None, "") and permitir_nulo:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError) as erro:
        raise parametro_invalido(campo, f"{campo} nao e do tipo integer.") from erro


def texto(valor, campo, tamanho=None):
    valor = "" if valor is None else str(valor)
    if tamanho and len(valor) > tamanho:
        raise parametro_invalido(campo, f"{campo} passa de {tamanho} caracteres.")
    return valor


def escolha(valor, campo, opcoes):
    if valor not in opcoes:
        raise parametro_invalido(campo, f"{campo} nao esta entre {', '.join(opcoes)}.")
    return valor


class Recurso:
    modelo = None
    nome = ""  # usado no codigo de erro: woocommerce_rest_<nome>_invalid_id
    campo_busca = ()
    ordenacoes = {"id": "id", "date": "created_at", "modified": "updated_at"}
    ordenacao_padrao = ("date", "desc")
    suporta_lixeira = True
    # Campo do date_created do Woo, usado nos filtros after/before.
    campo_data = "created_at"
    request = None  # a view preenche; usado para montar URLs absolutas

    def queryset(self):
        return self.modelo.objects.all()

    def obter(self, pk):
        try:
            return self.queryset().get(pk=int(pk))
        except (self.modelo.DoesNotExist, ValueError, TypeError) as erro:
            raise id_invalido(self.nome) from erro

    def obter_para_escrita(self, pk):
        """Trava a linha (select_for_update) e le o estado DEPOIS do lock.

        Sem prefetch/annotate de proposito: o Postgres recusa FOR UPDATE com
        GROUP BY, e cache de prefetch esconderia itens gravados nesta transacao.
        """
        try:
            return self.modelo.objects.select_for_update().get(pk=int(pk))
        except (self.modelo.DoesNotExist, ValueError, TypeError) as erro:
            raise id_invalido(self.nome) from erro

    def erro_integridade(self, erro):
        return WooErro("woocommerce_rest_conflict", "Registro repetido.", 400)

    def filtrar(self, qs, params):
        if params.get("search") and self.campo_busca:
            termo = params["search"]
            filtro = Q()
            for campo in self.campo_busca:
                filtro |= Q(**{f"{campo}__icontains": termo})
            qs = qs.filter(filtro)
        if params.get("include"):
            qs = qs.filter(pk__in=lista_de_ids(params, "include"))
        if params.get("exclude"):
            qs = qs.exclude(pk__in=lista_de_ids(params, "exclude"))
        if hasattr(self.modelo, "created_at"):
            for param, lookup in (("after", "gt"), ("before", "lt")):
                if params.get(param):
                    filtro = {f"{self.campo_data}__{lookup}": datas.ler(params[param], param)}
                    qs = qs.filter(**filtro)
            for param, lookup in (("modified_after", "gt"), ("modified_before", "lt")):
                if params.get(param):
                    qs = qs.filter(**{f"updated_at__{lookup}": datas.ler(params[param], param)})
        return self.ordenar(qs, params)

    def ordenar(self, qs, params):
        campo_padrao, sentido_padrao = self.ordenacao_padrao
        chave = params.get("orderby") or campo_padrao
        sentido = (params.get("order") or sentido_padrao).lower()
        escolha(chave, "orderby", list(self.ordenacoes))
        escolha(sentido, "order", ["asc", "desc"])
        campo = self.ordenacoes[chave]
        prefixo = "-" if sentido == "desc" else ""
        # id como desempate: sem ele a paginacao repete/pula itens de mesma data.
        return qs.order_by(f"{prefixo}{campo}", f"{prefixo}id")

    def para_woo(self, obj):
        raise NotImplementedError

    def gravar(self, obj, dados, criando):
        """Aplica o JSON recebido em obj (novo ou existente) e salva."""
        raise NotImplementedError

    def excluir(self, obj, forcar):
        """Devolve o JSON do objeto como estava. Sem force: vai para a lixeira."""
        resposta = self.para_woo(obj)
        if forcar:
            obj.delete()
            return resposta
        if not self.suporta_lixeira:
            raise WooErro(
                "woocommerce_rest_trash_not_supported",
                "Este recurso nao suporta lixeira. Envie force=true para excluir.",
                501,
            )
        if obj.status == "trash":
            raise WooErro(
                "woocommerce_rest_already_trashed", "O registro ja esta na lixeira.", 410
            )
        obj.status = "trash"
        obj.save()
        return self.para_woo(obj)
