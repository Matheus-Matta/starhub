"""Cria uma conta (tenant). Primeiro passo num banco novo, antes do createsuperuser.

    python manage.py criar_conta "Minha Loja"          # slug: minha-loja
    python manage.py createsuperuser                   # pede o id impresso aqui
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.core.models import Account


class Command(BaseCommand):
    help = "Cria uma conta (tenant) e mostra o id usado no createsuperuser."

    def add_arguments(self, parser):
        parser.add_argument("nome")
        parser.add_argument("--slug", default="")

    def handle(self, *args, nome, slug, **options):
        slug = slug or slugify(nome)
        if Account.objects.filter(slug=slug).exists():
            raise CommandError(f"Ja existe uma conta com o slug {slug!r}.")
        conta = Account.objects.create(name=nome, slug=slug)
        self.stdout.write(self.style.SUCCESS(f"Conta criada: {conta.name}"))
        self.stdout.write(f"id: {conta.pk}")
