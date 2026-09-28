from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class JSONDecimalField(models.JSONField):
    """JSONField que aceita Decimal (vira texto): o JSON do ERP chega com Decimal."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("encoder", DjangoJSONEncoder)
        super().__init__(*args, **kwargs)


ComDatas = BaseModel

# Preco, custo, peso e total nunca sao negativos (o form mostra o erro no campo).
NAO_NEGATIVO = [MinValueValidator(0)]
