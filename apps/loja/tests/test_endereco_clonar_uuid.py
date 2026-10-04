"""O endereco copiado para o pedido ganha uuid proprio.

`clonar` copia o registro com pk = None: sem trocar o uuid, a copia levava o do
cadastro do cliente e o indice unico recusava a gravacao do pedido.
"""

import pytest

from apps.core.models import Address
from apps.loja.services.enderecos import clonar


@pytest.mark.django_db
def test_copia_do_endereco_tem_uuid_diferente_do_original(conta):
    original = Address.objects.create(name="Casa", address_line_1="Rua A, 1")

    copia = clonar(original, "Entrega")

    assert copia.pk != original.pk
    assert copia.uuid != original.uuid
