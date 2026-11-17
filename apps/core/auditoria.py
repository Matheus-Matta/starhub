"""AppConfig do django-auditlog com o nome da secao em portugues no admin.

Fica fora de apps/core/apps.py de proposito: com duas AppConfig no mesmo modulo o
Django deixa de escolher a CoreConfig sozinho e a secao "Nucleo" vira "Core".

Cada log guarda tambem o registro inteiro como ficou (serialized_data): o "antes ->
depois" so mostra o que mudou, e o operador precisa ver o resto (preco, estoque,
total) para entender a alteracao. Campo de credencial fica de fora do retrato.
"""

from auditlog.apps import AuditlogConfig

SEGREDOS = ("criptografad", "senha", "password", "token", "segredo", "secret")


def campos_do_retrato(modelo):
    return [campo.name for campo in modelo._meta.concrete_fields
            if not campo.primary_key and not any(s in campo.name.lower() for s in SEGREDOS)]


class AuditoriaConfig(AuditlogConfig):
    verbose_name = "Auditoria"

    def ready(self):
        super().ready()
        from auditlog.registry import auditlog

        # A versao do simple_history e copia do registro: logar ela duplicava cada log.
        for modelo in [m for m in auditlog._registry if hasattr(m, "instance_type")]:
            auditlog.unregister(modelo)
        # AUDITLOG_INCLUDE_ALL_MODELS nao tem opcao global de retrato: liga model a model.
        for modelo, opcoes in auditlog._registry.items():
            opcoes["serialize_data"] = True
            opcoes["serialize_kwargs"] = {"fields": campos_do_retrato(modelo)}
