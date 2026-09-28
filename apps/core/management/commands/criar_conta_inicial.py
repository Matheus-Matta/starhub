"""Cria a conta inicial e o superusuario dela com os dados do .env.

    USER_ADMIN=admin
    PASSWORD_ADMIN=...
    ACCOUNT_ADMIN=starhub
    EMAIL_ADMIN=admin@empresa.com.br   (opcional)

    python manage.py criar_conta_inicial

Pode rodar de novo sem medo: conta e usuario que ja existem sao reaproveitados e
a senha de quem ja existe NAO e trocada. Variavel de ambiente real vale mais que
o .env (em prod ela vem do servico, nao do arquivo).
"""

import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.core.envfile import ler_env
from apps.core.models import Account, User

OBRIGATORIAS = ("USER_ADMIN", "PASSWORD_ADMIN", "ACCOUNT_ADMIN")


class Command(BaseCommand):
    help = "Cria a conta inicial e o superusuario com USER_ADMIN, PASSWORD_ADMIN e ACCOUNT_ADMIN."

    def add_arguments(self, parser):
        parser.add_argument("--env", default=str(settings.BASE_DIR / ".env"),
                            help="Arquivo .env a ler (padrao: .env na raiz do projeto).")

    def handle(self, *args, env, **options):
        dados = {**ler_env(Path(env)), **os.environ}
        faltando = [nome for nome in OBRIGATORIAS if not dados.get(nome, "").strip()]
        if faltando:
            raise CommandError(f"Defina no .env: {', '.join(faltando)}.")
        nome_conta = dados["ACCOUNT_ADMIN"].strip()
        usuario = dados["USER_ADMIN"].strip()
        senha = dados["PASSWORD_ADMIN"]
        email = dados.get("EMAIL_ADMIN", "").strip()

        with transaction.atomic():
            conta, conta_nova = Account.objects.get_or_create(
                slug=slugify(nome_conta), defaults={"name": nome_conta}
            )
            existente = User.objects.filter(username=usuario).first()
            if existente is not None and existente.account_id != conta.pk:
                raise CommandError(
                    f"O usuario {usuario!r} ja existe em outra conta ({existente.account})."
                )
            if existente is None:
                self._conferir_senha(senha, usuario)
                User.objects.create_superuser(usuario, email, senha, account=conta)

        self.stdout.write(self.style.SUCCESS(
            f"Conta {conta.name!r} {'criada' if conta_nova else 'ja existia'} (id {conta.pk})."
        ))
        if existente is None:
            self.stdout.write(self.style.SUCCESS(f"Superusuario {usuario!r} criado."))
        else:
            self.stdout.write(f"Superusuario {usuario!r} ja existia: senha mantida.")

    def _conferir_senha(self, senha, usuario):
        try:
            validate_password(senha, User(username=usuario))
        except ValidationError as erro:
            motivo = " ".join(erro.messages)
            # Em dev "admin/admin" agiliza; em prod o mesmo comando criaria um
            # superusuario com senha fraca exposto na internet.
            if not settings.DEBUG:
                raise CommandError(f"Senha fraca para producao: {motivo}") from erro
            self.stdout.write(self.style.WARNING(f"Senha fraca (aceita so em dev): {motivo}"))
