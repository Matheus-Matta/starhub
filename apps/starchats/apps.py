from django.apps import AppConfig


class StarChatsConfig(AppConfig):
    name = "apps.starchats"
    # A secao reune cadastros que podem ser usados por qualquer provedor de WhatsApp.
    # Somente a conexao com a API continua tendo a marca StarChats.
    verbose_name = "Mensagens"

    def ready(self):
        from apps.starchats import sinais

        sinais.conectar()
