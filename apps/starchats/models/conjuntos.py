from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel
from apps.starchats.models.regras import CAMPOS


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
    limite_diario = models.PositiveIntegerField(
        "limite maximo de envios por dia",
        default=0,
        help_text="Zero deixa sem limite. O limite vale separadamente para cada conjunto.",
    )
    numeros_permitidos = models.JSONField(
        "numeros permitidos",
        default=list,
        blank=True,
        help_text="Se a lista estiver preenchida, somente estes WhatsApps recebem mensagens.",
    )
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
        constraints = [models.UniqueConstraint(
            fields=["account", "nome"], name="starchats_conjunto_nome_por_conta"
        )]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        from apps.starchats.renderizacao import VARIAVEL
        from apps.starchats.telefones import NumeroInvalido, numero_whatsapp

        caminhos = {valor for valor, _rotulo in CAMPOS}
        erros = {}
        for campo in ("parametros_corpo", "parametros_cabecalho"):
            invalidos = [caminho for caminho in (getattr(self, campo) or {}).values()
                         if caminho not in caminhos]
            if invalidos:
                erros[campo] = f"Dado desconhecido: {', '.join(invalidos)}."
        for numero in self.numeros_permitidos or []:
            try:
                numero_whatsapp(numero)
            except NumeroInvalido:
                erros["numeros_permitidos"] = f"Numero invalido: {numero}."
                break
        self._validar_modelo(VARIAVEL, erros)
        if erros:
            raise ValidationError(erros)

    def _validar_modelo(self, variavel, erros):
        if bool(self.midia_cabecalho_url) != bool(self.midia_cabecalho_tipo):
            erros["midia_cabecalho_url"] = "Informe juntos a URL e o tipo da midia."
        if not self.modelo_id:
            return
        faltam = set(variavel.findall(self.modelo.conteudo or "")) - {
            str(chave) for chave in (self.parametros_corpo or {})
        }
        if faltam:
            erros["parametros_corpo"] = (
                f"Associe as variaveis do modelo: {', '.join(sorted(faltam))}."
            )
        cabecalho = next((item for item in (self.modelo.componentes or [])
                          if isinstance(item, dict)
                          and str(item.get("type", "")).upper() == "HEADER"), {})
        faltam = set(variavel.findall(cabecalho.get("text", ""))) - {
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
        if formato in {"image", "video", "document"} and self.midia_cabecalho_tipo != formato:
            erros["midia_cabecalho_tipo"] = f"Este modelo exige {formato}."
