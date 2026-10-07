"""Gera dados de demonstracao (10 ou mais por model) numa conta, para testar o sistema.

    python manage.py gerar_demo                  # conta do ACCOUNT_ADMIN do .env
    python manage.py gerar_demo --conta minha-loja --quantidade 20
    python manage.py gerar_demo --limpar         # apaga o demo anterior e gera de novo
    python manage.py gerar_demo --remover        # so apaga o demo

So o que o demo criou e apagado (apps/loja/demo/limpeza.py). Em producao
(DEBUG=False) recusa, a menos de --permitir-producao.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.core.envfile import ler_env
from apps.core.models import Account, User
from apps.core.origem import SISTEMA, origem
from apps.core.perfis_padrao import criar_perfis
from apps.core.tenant.context import tenant_context
from apps.loja.demo import (
    SENHA_USUARIOS,
    avaliacoes,
    catalogo,
    clientes,
    limpeza,
    nucleo,
    pedidos,
    variacoes,
)


class Command(BaseCommand):
    help = "Gera dados demo (10+ por model) numa conta. --limpar recria, --remover apaga."

    def add_arguments(self, parser):
        parser.add_argument("--conta", help="Slug da conta (padrao: ACCOUNT_ADMIN do .env).")
        parser.add_argument("--quantidade", type=int, default=10,
                            help="Registros por model (minimo e padrao: 10).")
        parser.add_argument("--limpar", action="store_true",
                            help="Apaga o demo que ja existe na conta e gera de novo.")
        parser.add_argument("--remover", action="store_true", help="So apaga o demo da conta.")
        parser.add_argument("--permitir-producao", action="store_true",
                            help="Roda mesmo com DEBUG=False (nao recomendado).")

    def handle(self, *args, **opcoes):
        if not settings.DEBUG and not opcoes["permitir_producao"]:
            raise CommandError("DEBUG=False: dados demo nao vao para producao. "
                               "Use --permitir-producao se for mesmo o caso.")
        quantidade = max(opcoes["quantidade"], 10)
        conta = self._conta(opcoes["conta"])
        with transaction.atomic(), tenant_context(conta), origem(SISTEMA, via="gerar_demo"):
            if opcoes["remover"] or opcoes["limpar"]:
                self._mostrar("Removido", limpeza.remover(conta))
            # Perfis fixos da conta (perfis_padrao): um demo antigo podia ocupar os codigos.
            criar_perfis(conta.pk)
            if opcoes["remover"]:
                return
            if limpeza.existe_demo(conta):
                raise CommandError("A conta ja tem dados demo. Use --limpar para recriar "
                                   "ou --remover para apagar.")
            chave = self._gerar(conta, quantidade)
        self.stdout.write(self.style.SUCCESS(f"Demo gerado na conta {conta.name!r}."))
        self.stdout.write(f"Usuarios demo: senha {SENHA_USUARIOS!r} "
                          f"(ex.: {nucleo.prefixo_usuario(conta)}vendas).")
        if chave:
            self.stdout.write(f"Chave da API Woo para testar: {chave[0]} / {chave[1]}")

    def _conta(self, slug):
        if not slug:
            dados = {**ler_env(settings.BASE_DIR / ".env"), **os.environ}
            slug = slugify(dados.get("ACCOUNT_ADMIN", "").strip())
        conta = Account.objects.filter(slug=slug).first() if slug else None
        if conta is None:
            raise CommandError(f"Conta {slug!r} nao encontrada. Informe --conta <slug> "
                               "ou crie com: python manage.py criar_conta_inicial")
        return conta

    def _gerar(self, conta, quantidade):
        nucleo.contas(quantidade)
        nucleo.usuarios(conta, nucleo.perfis(conta, quantidade))
        tags = catalogo.tags(quantidade)
        catalogo.servicos(quantidade)
        categorias = catalogo.categorias(conta, quantidade)
        valores = catalogo.tipos_e_valores()
        simples = catalogo.simples(categorias, tags, quantidade)
        variaveis = variacoes.variaveis(categorias, tags, valores)
        variacoes.kits(categorias, simples, quantidade)
        variacoes.externo(categorias)
        canais = nucleo.canais(quantidade)
        nucleo.politicas(canais, quantidade)
        nucleo.publicacoes(canais, simples, quantidade)
        compradores = clientes.clientes(quantidade)
        clientes.cupons(quantidade, compradores, categorias)
        vendaveis = [p.variante_padrao for p in simples]
        vendaveis += [v for p in variaveis for v in p.variantes.all()]
        # O dobro: so metade das situacoes tem envio, e entregas tambem passam de `quantidade`.
        pedidos.pedidos(compradores, vendaveis, quantidade * 2)
        avaliacoes.avaliacoes(compradores, simples, quantidade)
        chave = nucleo.chaves(quantidade)
        self._mostrar("Gerado", self._contagem(conta))
        return chave

    def _contagem(self, conta):
        from django.apps import apps

        contagem = {}
        for modelo in apps.get_models():
            if modelo._meta.app_label not in ("core", "loja", "woo_api"):
                continue
            if hasattr(modelo, "all_objects") and not modelo.__name__.startswith("Historical"):
                total = modelo.all_objects.filter(account=conta).count()
                contagem[str(modelo._meta.verbose_name_plural)] = total
        contagem["contas"] = Account.objects.count()
        contagem["usuarios"] = User.objects.filter(account=conta).count()
        return contagem

    def _mostrar(self, titulo, contagem):
        self.stdout.write(f"{titulo}:")
        for nome, total in sorted(contagem.items()):
            self.stdout.write(f"  {nome:<32} {total}")
