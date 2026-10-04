"""Importar avaliacoes por planilha: so as colunas e regras; a tela, o modelo e a
tarefa sao os de toda importacao (apps/integracoes/admin_importar.py)."""

from apps.integracoes.admin_importar import ImportarPlanilhaMixin
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao


class ImportarAvaliacoesMixin(ImportarPlanilhaMixin):
    importar_tipo = ExecucaoIntegracao.Tipo.IMPORTAR_AVALIACOES
    importar_tarefa = "apps.loja.tasks.importar_avaliacoes"
    importar_arquivo_modelo = "modelo-avaliacoes.csv"
    importar_descricao = "Cria os clientes e as avaliacoes de uma vez."
    importar_colunas = [
        ("email", True, "E-mail do cliente. Se nao existir, o cliente e criado so no hub."),
        ("nome", False, "Nome do cliente (usado so quando ele e criado)."),
        ("sobrenome", False, "Sobrenome do cliente (a vitrine mostra so a inicial)."),
        ("sku", True, "SKU do produto ou de uma variante dele."),
        ("nota", True, "De 1 a 5."),
        ("comentario", True, "Texto da avaliacao, ate 1500 caracteres."),
        ("nome_publico", False, "Nome que aparece na loja; vazio = \"Nome S.\"."),
        ("status", False, "aprovada, pendente ou rejeitada; vazio = aprovada (vai para a loja)."),
        ("data", False, "Data da avaliacao, dd/mm/aaaa; vazio = hoje."),
    ]
    importar_exemplo = ["ana@exemplo.com", "Ana", "Lima", "POL-001", "5",
                        "Poltrona linda e muito confortavel.", "", "aprovada", "15/09/2026"]
    importar_regras = [
        "Mesmo e-mail e mesmo produto atualiza a avaliacao: importar de novo a planilha "
        "corrigida nao duplica.",
        "Cliente novo fica so no hub: nao vira conta nem recebe e-mail na loja.",
        "Aprovada vai para a loja como as outras. Pendente espera a moderacao.",
        "Linha com erro nao para as outras: a tarefa lista cada uma com o motivo.",
    ]

    def importar_configuracao(self, request):
        configuracao = ConfiguracaoIntegracao.objects.filter(
            plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY).first()
        if configuracao is None:
            raise ValueError("Configure a integracao Shopify antes: as avaliacoes aprovadas "
                             "vao para a loja.")
        return configuracao
