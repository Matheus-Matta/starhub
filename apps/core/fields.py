"""Tipos de campo que carregam a semantica usada pela interface do StarHub."""

from django.db import models

from apps.core.widgets import EditorHTML


class TextoHTMLField(models.TextField):
    """Texto rico armazenado como HTML e editado visualmente nos formularios."""

    def formfield(self, **kwargs):
        kwargs.setdefault("widget", EditorHTML)
        return super().formfield(**kwargs)
