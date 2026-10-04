"""Demo do nucleo: contas, perfis de acesso, usuarios, canais de venda, politicas e
estado de publicacao, referencias externas e chaves da API Woo."""

from datetime import timedelta

from django.contrib.auth.models import Group, Permission
from django.utils import timezone

from apps.core.models import (
    AccessProfile,
    Account,
    ExternalReference,
    Origin,
    PublicationPolicy,
    PublicationState,
    SalesChannel,
    User,
)
from apps.loja.demo import PREFIXO_CONTA, SENHA_USUARIOS, marca, nome_n, prefixo_usuario

PERFIS = ["Vendas", "Estoque", "Financeiro", "Atendimento", "Marketing", "Expedicao",
          "Compras", "Fiscal", "Gerencia", "Suporte"]
# Perfis que tambem alteram (os outros so consultam) o que e da loja.
ALTERAM = {"Vendas", "Estoque", "Gerencia"}
PESSOAS = [("Ana", "Souza"), ("Bruno", "Lima"), ("Carla", "Mendes"), ("Diego", "Alves"),
           ("Elisa", "Rocha"), ("Fabio", "Costa"), ("Gabriela", "Nunes"), ("Hugo", "Pereira"),
           ("Isabela", "Martins"), ("Joao", "Ribeiro")]
PLATAFORMAS = [Origin.SHOPIFY, Origin.WOOCOMMERCE, Origin.MERCADO_LIVRE, Origin.SHOPEE,
               Origin.AMAZON, Origin.MAGALU, Origin.API, Origin.STARHUB, Origin.IMPORT]
ENTIDADES = [PublicationPolicy.EntityType.PRODUCT, PublicationPolicy.EntityType.ORDER,
             PublicationPolicy.EntityType.COUPON, PublicationPolicy.EntityType.CUSTOMER]
SITUACOES = ["synced", "pending", "failed", "syncing", "skipped", "unsupported"]


def contas(quantidade):
    """Contas extras (vazias), para a lista e o filtro de conta do superusuario."""
    return [
        Account.objects.get_or_create(
            slug=f"{PREFIXO_CONTA}{i:02d}",
            defaults={"name": f"Loja demo {i:02d}", "email": f"loja{i:02d}@demo.starhub.test"},
        )[0]
        for i in range(1, quantidade + 1)
    ]


def perfis(conta, quantidade):
    da_loja = Permission.objects.filter(content_type__app_label="loja")
    ver = list(da_loja.filter(codename__startswith="view_"))
    alterar = list(da_loja.filter(codename__startswith="change_"))
    criados = []
    for i in range(quantidade):
        nome = nome_n(PERFIS, i)
        codigo = nome.lower().replace(" ", "-")
        grupo = Group.objects.create(name=f"demo {conta.slug} {codigo}")
        grupo.permissions.set(ver + (alterar if nome in ALTERAM else []))
        criados.append(AccessProfile.objects.create(
            # "demo-": a conta ja tem os perfis fixos "vendas", "estoque"... (perfis_padrao).
            name=f"{nome} (demo)", code=f"demo-{codigo}", group=grupo, metadados=marca()
        ))
    return criados


def usuarios(conta, perfis_criados):
    criados = []
    for i, perfil in enumerate(perfis_criados):
        primeiro, ultimo = PESSOAS[i % len(PESSOAS)]
        codigo = perfil.code.removeprefix("demo-")
        usuario = User.objects.create_user(
            f"{prefixo_usuario(conta)}{codigo}", f"{primeiro.lower()}.{codigo}@demo.test",
            SENHA_USUARIOS, account=conta, is_staff=True, first_name=primeiro, last_name=ultimo,
            access_profile=perfil,
        )
        usuario.groups.add(perfil.group)
        criados.append(usuario)
    return criados


def canais(quantidade):
    criados = []
    for i in range(quantidade):
        plataforma = PLATAFORMAS[i % len(PLATAFORMAS)]
        criados.append(SalesChannel.objects.create(
            name=f"{plataforma.label} demo {i + 1}", platform=plataforma,
            external_store_id=f"demo-loja-{i + 1}", metadados=marca(),
        ))
    return criados


def politicas(canais_criados, quantidade):
    for i in range(quantidade):
        entidade, canal = ENTIDADES[i % len(ENTIDADES)], canais_criados[i % len(canais_criados)]
        PublicationPolicy.objects.create(
            name=f"{entidade.label} publicado no {canal.name}", entity_type=entidade,
            target_channel=canal, priority=i + 1, enabled=i % 5 != 4,
            default_action="deny" if i % 3 == 2 else "allow",
            rules={"all": [{"field": "status", "operator": "eq", "value": "publish"}],
                   "any": [{"field": "tags", "operator": "contains", "value": "Promocao"}]},
            metadados=marca(),
        )


def publicacoes(canais_criados, produtos, quantidade):
    """Um produto por canal: referencia externa (id no canal) e estado de publicacao."""
    agora = timezone.now()
    for i in range(quantidade):
        produto, canal = produtos[i % len(produtos)], canais_criados[i % len(canais_criados)]
        referencia = ExternalReference.objects.create(
            platform=canal.platform, entity_type="product", object_id=str(produto.pk),
            external_id=f"{canal.platform}-{1000 + i}", metadados=marca(),
        )
        situacao = SITUACOES[i % len(SITUACOES)]
        PublicationState.objects.create(
            entity_type="product", object_id=str(produto.pk), channel=canal,
            desired_state="unpublished" if i % 4 == 3 else "published", sync_status=situacao,
            external_reference=referencia,
            last_synced_at=agora - timedelta(hours=i) if situacao == "synced" else None,
            last_error="Canal recusou: categoria sem mapeamento." if situacao == "failed" else "",
            metadados=marca(),
        )


def chaves(quantidade):
    """Chaves ck_/cs_ da API Woo; devolve o par da primeira para testar a API."""
    from apps.woo_api.models import ChaveApi

    par = None
    for i in range(quantidade):
        chave = ChaveApi(descricao=f"Integracao demo {i + 1}", metadados=marca(),
                         permissao=["read_write", "read", "write"][i % 3])
        gerado = chave.gerar()
        chave.save()
        par = par or gerado
    return par
