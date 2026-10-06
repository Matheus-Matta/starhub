"""`migrate` com trava: varios containers web subindo juntos (blue e green) migram um por vez.

    python manage.py migrar

No PostgreSQL pega `pg_advisory_lock` antes de migrar: o segundo container espera o
primeiro terminar e encontra tudo aplicado. Sem a trava, os dois aplicariam a mesma
migration ao mesmo tempo e um quebraria no meio (tabela ja existe). No SQLite do dev
so ha um processo: migra direto.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

# Numero fixo da trava (qualquer bigint): o mesmo em todos os containers do StarHub.
TRAVA = 4_2_7_1_2026


class Command(BaseCommand):
    help = "Aplica as migrations com trava no banco (seguro com varios containers web)."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            call_command("migrate", interactive=False, verbosity=options["verbosity"])
            return
        with connection.cursor() as cursor:
            self.stdout.write("Esperando a trava de migracao...")
            cursor.execute("SELECT pg_advisory_lock(%s)", [TRAVA])
            try:
                call_command("migrate", interactive=False, verbosity=options["verbosity"])
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [TRAVA])
