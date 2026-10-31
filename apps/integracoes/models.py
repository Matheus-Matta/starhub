from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel
from apps.core.validators import separar_dominios
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
    nome_frete = models.CharField(
        "nome do frete no checkout", max_length=150, default="StarHub Frete", blank=True,
        help_text="Nome da calculadora exibido na Shopify. Vazio usa StarHub Frete.",
    )
    exibir_prazo_frete = models.BooleanField(
        "exibir prazo no checkout", default=True,
        help_text="Desligue para ocultar os dias uteis. O prazo da tabela continua salvo.",
    )
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

    # Servicos do hub (Loja > Servicos) na loja. Suri: cada servico vira variante do
    # produto (apps/suri/servicos.py). Shopify: cada servico vira um produto escondido,
    # que o tema poe no carrinho junto do produto (apps/shopify/servicos*.py).
    enviar_servicos = models.BooleanField(
        "enviar servicos", default=False,
        help_text="Leva os servicos para a loja: no Suri como variante do produto, na "
                  "Shopify como produto escondido com uma variante por preco.")
    receber_servicos = models.BooleanField(
        "receber servicos dos pedidos", default=False,
        help_text="Item do pedido com o SKU de um servico vira servico do item do produto, "
                  "com o valor somado nele, e nao um item avulso.")
    # So WooCommerce: formato do pedido que o hub cria na loja (Enviar > Pedidos > Criar).
    # Ligado, como docs/exemplos/pedido-completo.json (apps/woocommerce/envio/
    # pedidos_legado.py); desligado, o formato padrao.
    pedido_legado = models.BooleanField(
        "pedido no formato legado", default=False,
        help_text="Ligado, o pedido enviado a esta loja leva o servico so no meta do item "
                  "(starhub e EPOFW), fora do valor do item e do total, e o agendamento e a "
                  "origem no meta do pedido. Desligado, vai no formato padrao: o valor do "
                  "servico ja somado no item. Quem manda criar o pedido e Enviar > Pedidos > "
                  "Criar, na matriz abaixo.")
    servicos_no_tema = models.BooleanField(
        "oferecer servicos na pagina do produto", default=False,
        help_text="So Shopify: o bloco de servicos do tema (Guia dos servicos) mostra os "
                  "servicos do produto. Desligado, a consulta do tema responde vazia.")

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

    def dominios_permitidos_no_frete(self):
        dominios = [self.dominio_loja, *self.account.dominios_avaliacoes()]
        return separar_dominios(",".join(dominios))


class ExecucaoIntegracao(BaseModel):
    class Tipo(models.TextChoices):
        SINCRONIZAR = "sync", "Sincronizar loja"
        WEBHOOKS = "webhooks", "Cadastrar webhooks"
        RECEBER = "receive", "Receber webhook"
        ENVIAR = "send", "Enviar alteracao"
        EXPORTAR = "export", "Exportar dados"
        IMPORTAR_AVALIACOES = "import_reviews", "Importar avaliacoes"
        IMPORTAR_FRETE = "import_freight", "Importar faixas de frete"
        IMPORTAR_SERVICOS = "import_services", "Importar servicos (planilha)"
        EXPORTAR_SERVICOS = "export_services", "Exportar servicos"
        FRETE_CHECKOUT = "carrier", "Cadastrar frete no checkout"
        VERIFICAR_FRETE = "carrier_check", "Verificar frete no checkout"
        ENCAMINHAR = "forward", "Encaminhar pedido a loja"
        CPF_PEDIDOS = "fill_documents", "Buscar CPF dos pedidos"

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
