"""Botao "Logs" na edicao: abre a lista do auditlog so com os logs daquele registro,
mais recentes primeiro, e o usuario comum so ve logs da conta dele."""

import re

import pytest
from auditlog.models import LogEntry
from django.contrib.auth.models import Permission

from apps.core.models import User
from apps.core.tenant.context import tenant_context
from apps.loja.services.variantes import criar_produto

pytestmark = [pytest.mark.django_db, pytest.mark.sem_conta]


def _link_logs(html):
    padrao = r'href="([^"]*auditlog/logentry/\?registro=[^"]+)"[^>]*>.*?Logs</a>'
    achado = re.search(padrao, html, re.S)
    return achado.group(1).replace("&amp;", "&") if achado else None


def _linhas(html):
    return re.findall(r"<tr[^>]*>.*?</tr>", html.split("<tbody", 1)[-1], re.S)


@pytest.fixture
def produtos(conta, outra_conta):
    with tenant_context(conta):
        camiseta = criar_produto("Camiseta", sku="CAM-1")
        camiseta.nome = "Camiseta azul"
        camiseta.save()
        caneca = criar_produto("Caneca", sku="CAN-1")
    with tenant_context(outra_conta):
        de_fora = criar_produto("Produto de fora", sku="FORA-1")
    return camiseta, caneca, de_fora


def test_edicao_tem_o_botao_que_filtra_os_logs_do_registro(admin_logado, produtos):
    camiseta, caneca, _ = produtos
    pagina = admin_logado.get(f"/admin/loja/produto/{camiseta.pk}/change/").content.decode()
    link = _link_logs(pagina)
    assert link
    lista = admin_logado.get(link)
    assert lista.status_code == 200
    logs = list(lista.context["cl"].result_list)
    assert logs and {log.object_pk for log in logs} == {str(camiseta.pk)}
    assert [log.timestamp for log in logs] == sorted((log.timestamp for log in logs), reverse=True)
    assert logs[0].changes_dict.get("nome") == ["Camiseta", "Camiseta azul"]
    # O filtro aplicado aparece com o nome do registro (e da para limpar na gaveta).
    assert "Produto: Camiseta azul" in lista.content.decode()
    # Sem o botao (lista toda) aparecem outros registros.
    geral = admin_logado.get("/admin/auditlog/logentry/")
    assert {log.object_pk for log in geral.context["cl"].result_list} >= {str(caneca.pk)}


def test_filtro_invalido_nao_mostra_nada(admin_logado, produtos):
    resposta = admin_logado.get("/admin/auditlog/logentry/?registro=abc")
    assert resposta.status_code == 200 and not list(resposta.context["cl"].result_list)


def test_sem_permissao_de_ver_logs_nao_ha_botao(client, conta, produtos):
    usuario = User.objects.create_user("op", "op@loja.test", "senha-forte-123",
                                       account=conta, is_staff=True)
    usuario.user_permissions.set(Permission.objects.filter(content_type__app_label="loja"))
    client.force_login(usuario)
    html = client.get(f"/admin/loja/produto/{produtos[0].pk}/change/").content.decode()
    assert "Salvar" in html and _link_logs(html) is None


def test_usuario_comum_so_ve_logs_da_conta_dele(client, conta, produtos):
    camiseta, _, de_fora = produtos
    usuario = User.objects.create_user("op", "op@loja.test", "senha-forte-123",
                                       account=conta, is_staff=True)
    usuario.user_permissions.set(Permission.objects.filter(content_type__app_label="loja"))
    ver_logs = Permission.objects.get(codename="view_logentry", content_type__app_label="auditlog")
    usuario.user_permissions.add(ver_logs)
    client.force_login(usuario)
    assert LogEntry.objects.filter(additional_data__account_id=str(conta.pk)).exists()
    link = _link_logs(client.get(f"/admin/loja/produto/{camiseta.pk}/change/").content.decode())
    assert link and list(client.get(link).context["cl"].result_list)
    logs = client.get("/admin/auditlog/logentry/").context["cl"].result_list
    # Tipo + id: a conta tem logs de outros models (ex.: perfis iniciais) com o mesmo id.
    geral = {(log.content_type.model, log.object_pk) for log in logs}
    assert ("produto", str(camiseta.pk)) in geral and ("produto", str(de_fora.pk)) not in geral
