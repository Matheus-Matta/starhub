from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel

CAMPOS = [
    ("cliente.nome", "Cliente: nome"),
    ("cliente.sobrenome", "Cliente: sobrenome"),
    ("cliente.nome_completo", "Cliente: nome completo"),
    ("cliente.email", "Cliente: e-mail"),
    ("cliente.telefone", "Cliente: telefone"),
    ("cliente.cpf", "Cliente: CPF"),
    ("cliente.cnpj", "Cliente: CNPJ"),
    ("cliente.empresa", "Cliente: empresa"),
    ("cliente.nascimento", "Cliente: nascimento"),
    ("cliente.aceita_marketing", "Cliente: aceita marketing"),
    ("cliente.cliente_pagante", "Cliente: ja pagou"),
    ("pedido.numero", "Pedido: numero"),
    ("pedido.status", "Pedido: status"),
    ("pedido.status_pagamento", "Pedido: status do pagamento"),
    ("pedido.status_entrega", "Pedido: status da entrega"),
    ("pedido.total", "Pedido: total"),
    ("pedido.forma_pagamento", "Pedido: forma de pagamento"),
    ("pedido.metodo_envio", "Pedido: metodo de envio"),
    ("pedido.canal_origem", "Pedido: canal de origem"),
]


class RegraEnvio(BaseModel):
    class Operador(models.TextChoices):
        IGUAL = "eq", "igual a"
        DIFERENTE = "neq", "diferente de"
        CONTEM = "contains", "contem"
        NAO_CONTEM = "not_contains", "nao contem"
        MAIOR = "gt", "maior que"
        MAIOR_IGUAL = "gte", "maior ou igual a"
        MENOR = "lt", "menor que"
        MENOR_IGUAL = "lte", "menor ou igual a"
        VAZIO = "is_null", "esta vazio"
        PREENCHIDO = "is_not_null", "esta preenchido"

    nome = models.CharField(max_length=150)
    campo = models.CharField(max_length=50, choices=CAMPOS)
    operador = models.CharField(max_length=20, choices=Operador)
    valor = models.CharField(
        max_length=255,
        blank=True,
        help_text="Ex.: confirmed, true ou 100.00. Vazio nos operadores de vazio.",
    )

    class Meta:
        verbose_name = "regra de envio"
        verbose_name_plural = "Regras de envio"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        sem_valor = {self.Operador.VAZIO, self.Operador.PREENCHIDO}
        if self.operador not in sem_valor and not self.valor.strip():
            raise ValidationError({"valor": "Informe o valor comparado por esta regra."})
        if self.operador in sem_valor:
            return
        if self.campo in {"cliente.aceita_marketing", "cliente.cliente_pagante"}:
            if self.valor.casefold() not in {"true", "false", "sim", "nao", "1", "0"}:
                raise ValidationError({"valor": "Use true/false, sim/nao ou 1/0."})
        if self.campo == "pedido.total":
            try:
                Decimal(self.valor.replace(",", "."))
            except InvalidOperation as erro:
                mensagem = {"valor": "Informe um valor numerico, como 100.00."}
                raise ValidationError(mensagem) from erro


class ConjuntoEnvio(BaseModel):
    class Evento(models.TextChoices):
        CLIENTE_CRIADO = "cliente.criado", "Cliente criado"
        CLIENTE_ALTERADO = "cliente.alterado", "Cliente alterado"
        PEDIDO_CRIADO = "pedido.criado", "Pedido criado"
        PEDIDO_ALTERADO = "pedido.alterado", "Pedido alterado"

    class Modo(models.TextChoices):
        TODAS = "all", "Todas as regras devem valer"
        QUALQUER = "any", "Basta uma regra valer"

    nome = models.CharField(max_length=150)
    evento = models.CharField(max_length=30, choices=Evento)
    modo = models.CharField(max_length=10, choices=Modo, default=Modo.TODAS)
    modelo = models.ForeignKey(
        "starchats.ModeloMensagem", on_delete=models.PROTECT, related_name="conjuntos"
    )
    regras = models.ManyToManyField(RegraEnvio, related_name="conjuntos", blank=True)
    parametros_corpo = models.JSONField(
        "dados do modelo",
        default=dict,
        blank=True,
        help_text="Associe cada variavel ao dado. Ex.: 1 = cliente.nome_completo.",
    )
    parametros_cabecalho = models.JSONField(
        "dados do cabecalho",
        default=dict,
        blank=True,
        help_text="Para cabecalho com texto variavel. Ex.: atendente = cliente.nome.",
    )
    midia_cabecalho_url = models.URLField(
        "URL da midia do cabecalho",
        blank=True,
        help_text="Imagem, video ou documento publico exigido pelo modelo.",
    )
    midia_cabecalho_tipo = models.CharField(
        "tipo da midia",
        max_length=10,
        blank=True,
        choices=[("image", "Imagem"), ("video", "Video"), ("document", "Documento")],
    )
    codigo_botao = models.CharField(
        "codigo do botao",
        max_length=100,
        blank=True,
        help_text="Valor do botao 'copiar codigo', quando o modelo tiver esse botao.",
    )
    enviar_uma_vez = models.BooleanField(
        default=True,
        help_text="Evita repetir este conjunto para o mesmo cliente ou pedido.",
    )

    class Meta:
        verbose_name = "conjunto de envio"
        verbose_name_plural = "Conjuntos de envio"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "nome"], name="starchats_conjunto_nome_por_conta"
            )
        ]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        from apps.starchats.renderizacao import VARIAVEL

        caminhos = {valor for valor, _rotulo in CAMPOS}
        erros = {}
        for campo in ("parametros_corpo", "parametros_cabecalho"):
            invalidos = [
                caminho
                for caminho in (getattr(self, campo) or {}).values()
                if caminho not in caminhos
            ]
            if invalidos:
                erros[campo] = f"Dado desconhecido: {', '.join(invalidos)}."
        if bool(self.midia_cabecalho_url) != bool(self.midia_cabecalho_tipo):
            erros["midia_cabecalho_url"] = "Informe juntos a URL e o tipo da midia."
        if self.modelo_id:
            corpo = set(VARIAVEL.findall(self.modelo.conteudo or ""))
            faltam = corpo - {str(chave) for chave in (self.parametros_corpo or {})}
            if faltam:
                erros["parametros_corpo"] = (
                    f"Associe as variaveis do modelo: {', '.join(sorted(faltam))}."
                )
            cabecalho = next(
                (
                    item
                    for item in (self.modelo.componentes or [])
                    if isinstance(item, dict)
                    and str(item.get("type", "")).upper() == "HEADER"
                ),
                {},
            )
            variaveis = set(VARIAVEL.findall(cabecalho.get("text", "")))
            faltam = variaveis - {
                str(chave) for chave in (self.parametros_cabecalho or {})
            }
            if faltam:
                erros["parametros_cabecalho"] = (
                    f"Associe as variaveis do cabecalho: {', '.join(sorted(faltam))}."
                )
            formato = str(cabecalho.get("format", "")).casefold()
            if formato in {"image", "video", "document"} and not self.midia_cabecalho_url:
                erros["midia_cabecalho_url"] = "Este modelo exige uma midia no cabecalho."
            if formato == "text" and self.midia_cabecalho_url:
                erros["midia_cabecalho_url"] = "O cabecalho deste modelo e texto, nao midia."
            if formato in {"image", "video", "document"} and (
                self.midia_cabecalho_tipo != formato
            ):
                erros["midia_cabecalho_tipo"] = f"Este modelo exige {formato}."
        if erros:
            raise ValidationError(erros)
