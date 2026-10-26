"""Pre-consulta os CEPs dos enderecos ja cadastrados (motor de CEP do hub).

    python manage.py aquecer_ceps            # todos os CEPs novos dos enderecos
    python manage.py aquecer_ceps --limite 200

O checkout so vai a rede para CEP que o hub nunca viu; aquecendo os CEPs dos clientes
e pedidos que ja existem, a primeira compra de cada um responde do banco. Uma consulta
por segundo: as APIs gratuitas (Nominatim) pedem isso.
"""

import time

from django.core.management.base import BaseCommand

from apps.core.models import Address
from apps.logistica import geo
from apps.logistica.models import CoordenadaCep

INTERVALO = 1.0


class Command(BaseCommand):
    help = "Consulta e guarda a coordenada dos CEPs dos enderecos que o hub ainda nao conhece."

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=0, help="No maximo N CEPs (0 = todos).")

    def handle(self, *args, limite=0, **opcoes):
        ceps = {"".join(c for c in cep if c.isdigit())
                for cep in Address.all_objects.values_list("postal_code", flat=True)}
        ceps = sorted(c for c in ceps if len(c) == 8)
        conhecidos = set(CoordenadaCep.objects.filter(cep__in=ceps).values_list("cep", flat=True))
        novos = [c for c in ceps if c not in conhecidos][:limite or None]
        self.stdout.write(f"{len(ceps)} CEPs nos enderecos; {len(novos)} ainda sem coordenada.")
        achados = 0
        for posicao, cep in enumerate(novos, 1):
            try:
                geo.coordenada(cep)
                achados += 1
            except geo.GeoErro as erro:
                self.stdout.write(f"  {cep}: {erro}")
            if posicao % 20 == 0 or posicao == len(novos):
                self.stdout.write(f"{posicao}/{len(novos)} consultados, {achados} localizados.")
            time.sleep(INTERVALO)
        self.stdout.write(self.style.SUCCESS(f"Pronto: {achados} de {len(novos)} localizados."))
