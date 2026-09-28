"""Pagina "Meu perfil" do admin: so o que a pessoa precisa mexer nela mesma.

Nome, sobrenome e e-mail. Usuario, grupos e permissoes nao aparecem aqui: isso
e de quem administra acessos (Autenticacao > Usuarios). Qualquer usuario da
equipe acessa, sem precisar da permissao de alterar usuarios.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.template.response import TemplateResponse


class PerfilForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]
        labels = {"first_name": "Nome", "last_name": "Sobrenome", "email": "E-mail"}
        widgets = {
            "first_name": forms.TextInput(attrs={"placeholder": "Ana"}),
            "last_name": forms.TextInput(attrs={"placeholder": "Silva"}),
            "email": forms.EmailInput(attrs={"placeholder": "nome@empresa.com.br"}),
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        modelo = get_user_model()
        email_ja_usado = (
            modelo.objects.filter(email__iexact=email)
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if email and email_ja_usado:
            # O login JWT aceita e-mail no lugar do usuario: dois iguais seria ambiguo.
            raise forms.ValidationError("Este e-mail ja e usado por outro usuario.")
        return email


def perfil_view(admin_site, request):
    form = PerfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Perfil atualizado.")
        return redirect("admin:perfil")
    contexto = {
        **admin_site.each_context(request),
        "title": "Meu perfil",
        "subtitle": None,
        "form": form,
    }
    return TemplateResponse(request, "admin/perfil.html", contexto)
