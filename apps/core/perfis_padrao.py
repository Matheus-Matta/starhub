"""Grupos fixos do sistema e os perfis de acesso iniciais de toda conta.

Grupo (auth.Group) e global e guarda as permissoes; perfil (AccessProfile) e da
conta e aponta para um grupo. O usuario ganha as permissoes do grupo do perfil dele
(apps/core/tenant/auth_backend.py). Aqui ficam:

- GRUPOS: os grupos fixos, com as permissoes de cada um (a fonte da verdade).
- sincronizar_grupos: cria os grupos e acerta as permissoes. Roda na migration
  core.0003 e no fim de todo `migrate` (model novo entra no grupo sem migration).
- criar_perfis: um perfil de cada grupo fixo na conta (is_system=True). Roda na
  migration (contas que ja existiam) e quando uma conta nasce (sinal post_save).

Os grupos fixos nao sao editaveis no admin (o Group nem aparece): o que vale e esta
lista. Perfil proprio de uma conta continua podendo ser criado a parte.
"""

from django.apps import apps as apps_globais

VER = ["view"]
EDITAR = ["add", "change", "view"]
TUDO = ["add", "change", "delete", "view"]
TODOS = "*"  # todos os models do app

PEDIDOS = ["pedido", "itempedido", "pagamentopedido", "entregapedido"]
CLIENTES = ["cliente", "clienteendereco"]
CATALOGO = ["produto", "varianteproduto", "midiaproduto", "categoria", "tag", "tipovariante",
            "valorvariante", "valordavarianteproduto", "itembundle"]
INTEGRACOES_ANTIGAS = [
    "saleschannel", "publicationpolicy", "publicationstate", "externalreference",
]
LOGS = ("auditlog", ["logentry"], VER)

# (codigo, nome, descricao, regras); regra = (app, models ou TODOS, acoes) ou "app.codename".
GRUPOS = [
    ("administrador", "Administrador", "Tudo da conta: loja, usuarios, integracoes e logs.", [
        ("loja", TODOS, TUDO), ("woo_api", TODOS, TUDO), "woo_api.usar_api",
        ("core", ["user", "address", *INTEGRACOES_ANTIGAS], TUDO),
        ("integracoes", TODOS, TUDO), ("core", ["accessprofile"], VER),
        ("core", ["account"], ["view", "change"]), LOGS,
    ]),
    ("gerente", "Gerente", "Opera a loja inteira, sem excluir; ve usuarios e logs.", [
        ("loja", TODOS, EDITAR), ("woo_api", ["chaveapi"], VER),
        ("core", ["address", *INTEGRACOES_ANTIGAS], EDITAR),
        ("integracoes", TODOS, EDITAR),
        ("core", ["user", "accessprofile", "account"], VER), LOGS,
    ]),
    ("vendas", "Vendas", "Pedidos e clientes; consulta catalogo e cupons.", [
        ("loja", [*PEDIDOS, *CLIENTES], EDITAR), ("core", ["address"], EDITAR),
        ("loja", ["cupom", *CATALOGO], VER),
    ]),
    ("catalogo", "Catalogo", "Produtos, variantes, categorias, tags e kits.", [
        ("loja", CATALOGO, TUDO), ("loja", ["pedido", "itempedido"], VER),
    ]),
    ("estoque", "Estoque", "Ajusta estoque das variantes e cuida das entregas.", [
        ("loja", ["varianteproduto"], ["view", "change"]), ("loja", ["entregapedido"], EDITAR),
        ("loja", ["produto", "itembundle", "midiaproduto", "categoria", "pedido", "itempedido"],
         VER),
    ]),
    ("financeiro", "Financeiro", "Pagamentos, cupons e status dos pedidos.", [
        ("loja", ["pagamentopedido"], TUDO), ("loja", ["cupom"], EDITAR),
        ("loja", ["pedido"], ["view", "change"]),
        ("loja", ["itempedido", *CLIENTES], VER), ("core", ["address"], VER), LOGS,
    ]),
    ("atendimento", "Atendimento", "Clientes e acompanhamento de pedidos.", [
        ("loja", CLIENTES, EDITAR), ("core", ["address"], EDITAR),
        ("loja", ["pedido"], ["view", "change"]),
        ("loja", ["itempedido", "entregapedido", "pagamentopedido", *CATALOGO], VER),
    ]),
    ("leitura", "Somente leitura", "Consulta tudo da loja, sem alterar nada.", [
        ("loja", TODOS, VER), ("core", ["address", *INTEGRACOES_ANTIGAS], VER),
        ("integracoes", TODOS, VER),
    ]),
    ("integracao-api", "Integracao API", "Usuario do ERP (JWT) na API Woo.", [
        "woo_api.usar_api", ("loja", TODOS, EDITAR),
    ]),
]


def nome_do_grupo(nome):
    return f"Padrao: {nome}"


def _models(apps, app_label, modelos):
    if modelos != TODOS:
        return modelos
    try:
        app = apps.get_app_config(app_label)
    except LookupError:
        # Migration antiga usa um estado historico em que apps novos ainda nao existem.
        return []
    return [m._meta.model_name for m in app.get_models()
            if not m._meta.model_name.startswith("historical")]


def _permissoes(apps, regras):
    """(app_label, codename) de cada permissao das regras."""
    pares = set()
    for regra in regras:
        if isinstance(regra, str):
            pares.add(tuple(regra.split(".", 1)))
            continue
        app_label, modelos, acoes = regra
        pares |= {(app_label, f"{acao}_{modelo}")
                  for modelo in _models(apps, app_label, modelos) for acao in acoes}
    return pares


def sincronizar_grupos(apps=apps_globais):
    """Cria os grupos fixos e deixa cada um com EXATAMENTE as permissoes da lista."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    grupos = {}
    for codigo, nome, _descricao, regras in GRUPOS:
        grupo, _ = Group.objects.get_or_create(name=nome_do_grupo(nome))
        pares = _permissoes(apps, regras)
        candidatas = Permission.objects.filter(
            content_type__app_label__in={app for app, _ in pares}
        ).select_related("content_type")
        grupo.permissions.set(
            [p for p in candidatas if (p.content_type.app_label, p.codename) in pares]
        )
        grupos[codigo] = grupo
    return grupos


def criar_perfis(conta_id, apps=apps_globais):
    """Um perfil de cada grupo fixo na conta; o que ja existe (pelo codigo) fica."""
    Group = apps.get_model("auth", "Group")
    AccessProfile = apps.get_model("core", "AccessProfile")
    # Na migration o model historico so tem o manager simples; no codigo, all_objects.
    perfis = getattr(AccessProfile, "all_objects", AccessProfile.objects)
    nomes = [nome_do_grupo(nome) for _, nome, _, _ in GRUPOS]
    existentes = {g.name: g for g in Group.objects.filter(name__in=nomes)}
    grupos = (sincronizar_grupos(apps) if len(existentes) < len(GRUPOS)
              else {codigo: existentes[nome_do_grupo(nome)] for codigo, nome, _, _ in GRUPOS})
    for codigo, nome, _descricao, _regras in GRUPOS:
        perfis.get_or_create(account_id=conta_id, code=codigo, defaults={
            "name": nome, "group": grupos[codigo], "is_system": True,
        })


def perfis_da_conta_nova(sender, instance, created, raw=False, **kwargs):
    """post_save de Account: a conta nova ja nasce com os perfis iniciais."""
    if not created or raw:  # raw: loaddata de fixture traz os proprios perfis
        return
    from apps.core.tenant.context import tenant_context

    # Na conta nova: o BaseModel recusa gravar em conta diferente da ativa.
    with tenant_context(instance.pk):
        criar_perfis(instance.pk)


def grupos_depois_do_migrate(sender, app_config=None, **kwargs):
    """post_migrate: so no ultimo app, quando todas as permissoes ja existem. App sem
    models (corsheaders) nao recebe o sinal: vale o ultimo que tem."""
    ultimo = [a for a in apps_globais.get_app_configs() if a.models_module is not None][-1]
    if app_config is not None and app_config.label == ultimo.label:
        sincronizar_grupos()
