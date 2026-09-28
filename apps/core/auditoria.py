"""AppConfig do django-auditlog com o nome da secao em portugues no admin.

Fica fora de apps/core/apps.py de proposito: com duas AppConfig no mesmo modulo o
Django deixa de escolher a CoreConfig sozinho e a secao "Nucleo" vira "Core".
"""

from auditlog.apps import AuditlogConfig


class AuditoriaConfig(AuditlogConfig):
    verbose_name = "Auditoria"
