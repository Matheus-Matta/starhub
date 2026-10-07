from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel
from apps.integracoes import permissoes, segredos


class ConfiguracaoIntegracao(BaseModel):
    NOME_FIXO = "Shopify"
    VERSAO_API_FIXA = "2026-07"

    class Plataforma(models.TextChoices):
        SHOPIFY = "shopify", "Shopify"
        WOOCOMMERCE = "woocommerce", "WooCommerce"
        SURI = "suri", "Suri Shop"

    nome = models.CharField("nome", max_length=150, default=NOME_FIXO)
    plataforma = models.CharField(
        "plataforma", max_length=30, choices=Plataforma, default=Plataforma.SHOPIFY
    )
    dominio_loja = models.CharField("dominio da loja", max_length=255, blank=True)
    versao_api = models.CharField("versao da API", max_length=20, default=VERSAO_API_FIXA)
    token_criptografado = models.TextField(editable=False, blank=True)
    segredo_criptografado = models.TextField(editable=False, blank=True)
    # Assina o token que o tema gera no Liquid (hmac_sha256). Nao e o client secret do
    # app: este fica nas configuracoes do tema, que qualquer editor do tema le.
    segredo_avaliacoes_criptografado = models.TextField(editable=False, blank=True)
    url_webhook = models.URLField("URL publica dos webhooks", blank=True)
    permissoes = models.JSONField("permissoes", default=permissoes.matriz_vazia, blank=True)
    # Liga/desliga do frete do hub no checkout: desligado, a rota de cotacao responde sem
    # opcoes na hora, e o cadastro na Shopify fica inativo (ela para de chamar).
    frete_ativo = models.BooleanField("frete do hub no checkout", default=True)
    # Cada origem vende por um vendedor no ERP: sai como starhub.idVendedor nos pedidos
    # desta plataforma (API Woo). Vazio, o campo nao sai: um 0 o ERP aceitaria calado.
    id_vendedor = models.PositiveIntegerField(
        "ID do vendedor no ERP", null=True, blank=True,
        help_text="Numero do vendedor no ERP para os pedidos que vem desta loja. "
                  "Vai no meta_data do pedido como idVendedor.")
    # So WooCommerce, so o superusuario muda: ligado, a rota de pedidos da API Woo do hub
    # repassa a requisicao do ERP para a loja e devolve a resposta dela (woo_api).
    encaminhar_pedidos = models.BooleanField(
        "encaminhar pedidos do ERP a loja", default=False,
        help_text="Desligado, a API Woo do hub responde os pedidos com os dados do hub. "
                  "Ligado, cada chamada de pedido do ERP vai para a loja WooCommerce e a "
                  "resposta dela volta ao ERP; cada uma fica em Tarefas, com a requisicao "
                  "e a resposta.")

    class Meta:
        verbose_name = "configuracao de integracao"
        verbose_name_plural = "Shopify"
        constraints = [models.UniqueConstraint(
            fields=["account", "plataforma"], name="integracao_plataforma_conta_unica"
        )]

    def __str__(self):
        return self.nome

    @property
    def token_acesso(self):
        return segredos.descriptografar(self.token_criptografado)

    @token_acesso.setter
    def token_acesso(self, valor):
        self.token_criptografado = segredos.criptografar(valor)

    @property
    def segredo_app(self):
        return segredos.descriptografar(self.segredo_criptografado)

    @segredo_app.setter
    def segredo_app(self, valor):
        self.segredo_criptografado = segredos.criptografar(valor)

    @property
    def segredo_avaliacoes(self):
        return segredos.descriptografar(self.segredo_avaliacoes_criptografado)

    @segredo_avaliacoes.setter
    def segredo_avaliacoes(self, valor):
        self.segredo_avaliacoes_criptografado = segredos.criptografar(valor)

    def habilitado(self, direcao, recurso, operacao):
        matriz = permissoes.normalizar(self.permissoes)
        return matriz.get(direcao, {}).get(recurso, {}).get(operacao, False)


class ExecucaoIntegracao(BaseModel):
    class Tipo(models.TextChoices):
        SINCRONIZAR = "sync", "Sincronizar loja"
        WEBHOOKS = "webhooks", "Cadastrar webhooks"
        RECEBER = "receive", "Receber webhook"
        ENVIAR = "send", "Enviar alteracao"
        EXPORTAR = "export", "Exportar dados"
        IMPORTAR_AVALIACOES = "import_reviews", "Importar avaliacoes"
        IMPORTAR_FRETE = "import_freight", "Importar faixas de frete"
        FRETE_CHECKOUT = "carrier", "Cadastrar frete no checkout"
        VERIFICAR_FRETE = "carrier_check", "Verificar frete no checkout"
        ENCAMINHAR = "forward", "Encaminhar pedido a loja"

    class Status(models.TextChoices):
        PENDENTE = "pending", "Pendente"
        PROCESSANDO = "running", "Processando"
        CONCLUIDA = "completed", "Concluida"
        # Terminou, mas parte dos itens deu erro: detalhe por item em `falhas`.
        CONCLUIDA_COM_FALHAS = "completed_errors", "Concluida com falhas"
        FALHOU = "failed", "Falhou"

    # Vazia nas tarefas que nao falam com marketplace (ex.: importar faixas de frete).
    configuracao = models.ForeignKey(
        ConfiguracaoIntegracao, on_delete=models.PROTECT, related_name="execucoes",
        null=True, blank=True,
    )
    tipo = models.CharField("tarefa", max_length=20, choices=Tipo)
    status = models.CharField(
        max_length=20, choices=Status, default=Status.PENDENTE, db_index=True
    )
    celery_task_id = models.CharField("ID no Celery", max_length=255, blank=True)
    etapa = models.CharField(max_length=150, default="Aguardando")
    processados = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    progresso = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    mensagem = models.TextField(blank=True)
    # O que o operador pediu na tela (direcao e recursos): a tarefa le daqui.
    parametros = models.JSONField("parametros", default=dict, blank=True)
    # Um item por falha (apps/integracoes/falhas.py): recurso, id, descricao,
    # id_externo e motivo; o admin mostra em tabela.
    falhas = models.JSONField("falhas", default=list, blank=True, encoder=DjangoJSONEncoder)
    iniciada_em = models.DateTimeField(null=True, blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        # So "tarefa": alem das integracoes, roda as importacoes de planilha.
        verbose_name = "tarefa"
        verbose_name_plural = "Tarefas"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(
            # Duas sincronizacoes da mesma loja ao mesmo tempo gravariam o mesmo
            # registro em paralelo e criariam duplicado no marketplace.
            fields=["configuracao"],
            condition=models.Q(status__in=["pending", "running"], tipo__in=["sync", "export"]),
            name="integracao_uma_sincronizacao_por_vez",
        )]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.get_status_display()}"
