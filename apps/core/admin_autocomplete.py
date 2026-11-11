"""Dados extras usados pelos autocompletes do admin."""

from django.contrib.admin.views.autocomplete import AutocompleteJsonView


class AutocompleteTema(AutocompleteJsonView):
    def serialize_result(self, obj, to_field_name):
        resultado = super().serialize_result(obj, to_field_name)
        if obj._meta.label_lower == "loja.varianteproduto":
            resultado["sku"] = obj.sku
        return resultado
