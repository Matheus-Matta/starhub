"""Cria o banco do PostgreSQL com o nome do .env (POSTGRES_DB), se ainda nao existir.

    python manage.py criar_banco
    docker compose run --rm web-blue python manage.py criar_banco

Conecta no banco de manutencao `postgres` com o mesmo usuario e senha do .env e roda
CREATE DATABASE. Ja existindo, nao faz nada: roda em toda subida do web, antes do
`migrar`. O usuario precisa da permissao CREATEDB (o do PostgreSQL do compose tem).
No SQLite do dev o arquivo nasce sozinho: nada a fazer.
"""

import psycopg
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from psycopg import sql

MANUTENCAO = "postgres"
TRAVA_CRIACAO = 4_2_7_1_2027


class Command(BaseCommand):
    help = "Cria o banco POSTGRES_DB do .env no servidor PostgreSQL, se ainda nao existir."

    def handle(self, *args, **options):
        config = connections["default"].settings_dict
        if config["ENGINE"] != "django.db.backends.postgresql":
            self.stdout.write("Banco nao e PostgreSQL: nada a criar.")
            return
        nome = config["NAME"]
        try:
            # autocommit: CREATE DATABASE nao roda dentro de transacao.
            with psycopg.connect(dbname=MANUTENCAO, user=config["USER"],
                                 password=config["PASSWORD"], host=config["HOST"] or None,
                                 port=config["PORT"] or None, autocommit=True,
                                 **config.get("OPTIONS", {})) as conexao:
                conexao.execute("SELECT pg_advisory_lock(%s)", [TRAVA_CRIACAO])
                try:
                    existe = conexao.execute(
                        "SELECT 1 FROM pg_database WHERE datname = %s", [nome]).fetchone()
                    if existe:
                        self.stdout.write(f"Banco {nome} ja existe.")
                        return
                    conexao.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(nome), sql.Identifier(config["USER"])))
                finally:
                    conexao.execute("SELECT pg_advisory_unlock(%s)", [TRAVA_CRIACAO])
        except psycopg.Error as erro:
            raise CommandError(
                f"Nao foi possivel criar o banco {nome}: {erro}. Confira POSTGRES_HOST, "
                "POSTGRES_USER e POSTGRES_PASSWORD no .env; o usuario precisa poder criar "
                "banco (CREATEDB), ou crie o banco a mao no servidor.") from erro
        self.stdout.write(self.style.SUCCESS(f"Banco {nome} criado."))
