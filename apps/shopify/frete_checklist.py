"""Checklist "Frete no checkout" da tela Integracoes > Shopify.

Junta tres fontes, sem chamar a Shopify (a tela nao espera API externa):
- a ultima verificacao (frete_diagnostico.py, no vinculo "frete_checkout");
- a ultima tarefa de cadastro (o 403 do plano aparece la);
- o que o hub sabe sozinho (peso das variantes, tabelas marcadas para o checkout).

Cada item: {"titulo", "estado": ok | falta | aviso | manual | pendente, "detalhe", "como"}.
Obrigatorios (OBRIGATORIOS) decidem se esta "pronto para o checkout"; os outros (origem
das tabelas, peso, embalagem) so avisam. `para_ligar` e o que o dialogo do "Ligar frete"
lista antes de confirmar.
"""

from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.utils.dateparse import parse_datetime

from apps.core.models import ExternalReference, Origin
from apps.integracoes.models import ExecucaoIntegracao
from apps.logistica.models import TabelaFrete
from apps.loja.models import VarianteProduto
from apps.shopify.frete_diagnostico import ENTIDADE

PENDENTE = "Clique em Verificar configuracao para conferir na loja."
CADASTRADO = "Frete do StarHub cadastrado na loja"
ZONA_TITULO = "Ligado a zona de envio"
OBRIGATORIOS = ("Escopos read_shipping e write_shipping", "Plano libera frete de terceiros",
                CADASTRADO, ZONA_TITULO, "CEP dos locais de estoque",
                "Tabelas de frete no checkout")
ZONA = ("Na Shopify: Configuracoes > Frete e entrega > perfil Geral > zona Brasil > Adicionar "
        "taxa > Usar transportadora ou app > StarHub Frete.")
PLANO = ("Planos Advanced, Plus, anual ou loja de desenvolvimento ja liberam. No Basic mensal, "
         "peca ao suporte da Shopify o \"Third-party carrier-calculated shipping\".")


def _item(titulo, estado, detalhe="", como=""):
    return {"titulo": titulo, "estado": estado, "detalhe": detalhe, "como": como}


def _ultimo_cadastro(configuracao):
    return (ExecucaoIntegracao.objects.filter(configuracao=configuracao,
                                              tipo=ExecucaoIntegracao.Tipo.FRETE_CHECKOUT)
            .order_by("-created_at").first())


def _plano(diag, cadastro):
    recusado = cadastro and cadastro.status == "failed" and any(
        termo in cadastro.mensagem.lower() for termo in ("403", "forbidden", "third-party"))
    if recusado:
        return _item("Plano libera frete de terceiros", "falta", cadastro.mensagem[:200], PLANO)
    plano = diag.get("plano") or {}
    if (diag.get("servico") or {}).get("ativo") or plano.get("liberado_de_cara"):
        return _item("Plano libera frete de terceiros", "ok", plano.get("nome", ""))
    if not diag:
        return _item("Plano libera frete de terceiros", "pendente", "", PENDENTE)
    return _item("Plano libera frete de terceiros", "manual",
                 f"Plano {plano.get('nome') or 'desconhecido'}.", PLANO)


def _origem_das_tabelas(locais):
    """Tabela por distancia mede do CEP de origem dela, nao do local da Shopify."""
    ceps = {"".join(c for c in local["cep"] if c.isdigit()) for local in locais}
    longe = [t.nome for t in TabelaFrete.objects.filter(active=True, no_checkout=True,
                                                        tipo=TabelaFrete.Tipo.DISTANCIA)
             if t.cep_origem not in ceps]
    if not longe:
        return _item("Origem das tabelas por distancia", "ok",
                     "O CEP de origem bate com um local da loja.")
    return _item("Origem das tabelas por distancia", "aviso",
                 f"CEP de origem diferente dos locais da loja: {', '.join(longe)}.",
                 "Confira se a entrega sai mesmo desse CEP; o km e medido a partir dele.")


def _peso():
    ligadas = ExternalReference.objects.filter(platform=Origin.SHOPIFY, entity_type="variantes")
    # object_id e texto; PostgreSQL exige comparar valores do mesmo tipo.
    sem_peso = (VarianteProduto.objects.annotate(id_texto=Cast("pk", CharField()))
                .filter(id_texto__in=ligadas.values("object_id"))
                .filter(Q(weight__isnull=True) | Q(weight=0)).count())
    if not sem_peso:
        return _item("Peso nos produtos", "ok", "Todas as variantes da loja tem peso.")
    return _item("Peso nos produtos", "aviso", f"{sem_peso} variante(s) da loja sem peso.",
                 "As tabelas do hub ainda nao cobram por peso; preencha o peso na Shopify para "
                 "quando cobrarem (sem peso a Shopify manda 0 g).")


def checklist(configuracao):
    if configuracao is None or not configuracao.pk:
        return {"itens": [], "verificado_em": None}
    vinculo = ExternalReference.objects.filter(platform=Origin.SHOPIFY, entity_type=ENTIDADE,
                                               object_id=str(configuracao.pk)).first()
    diag = (vinculo.metadata if vinculo else None) or {}
    escopos, servico = diag.get("escopos") or {}, diag.get("servico") or {}
    locais, zonas = diag.get("locais") or {}, diag.get("zonas") or {}
    itens = []
    if not diag:
        itens.append(_item("Escopos read_shipping e write_shipping", "pendente", "", PENDENTE))
    elif escopos.get("erro") or escopos.get("faltam"):
        itens.append(_item("Escopos read_shipping e write_shipping", "falta",
                           escopos.get("erro") or "Faltam: " + ", ".join(escopos["faltam"]),
                           "Inclua os escopos no app (Dev Dashboard) e reinstale na loja."))
    else:
        itens.append(_item("Escopos read_shipping e write_shipping", "ok"))
    itens.append(_plano(diag, _ultimo_cadastro(configuracao)))
    if not configuracao.frete_ativo:
        itens.append(_item("Frete do StarHub cadastrado na loja", "aviso",
                           "Desligado no hub: o checkout nao mostra o frete do StarHub.",
                           "Clique em Ligar frete para voltar a oferecer."))
    elif servico.get("erro_url"):
        itens.append(_item("Frete do StarHub cadastrado na loja", "falta", servico["erro_url"]))
    elif servico.get("ativo"):
        itens.append(_item("Frete do StarHub cadastrado na loja", "ok", servico.get("url", "")))
    else:
        itens.append(_item("Frete do StarHub cadastrado na loja", "falta" if diag else "pendente",
                           servico.get("erro", ""), "Clique em Cadastrar frete no checkout."))
    if zonas.get("zonas"):
        itens.append(_item("Ligado a zona de envio", "ok", "; ".join(zonas["zonas"])))
    elif servico.get("ativo"):
        itens.append(_item("Ligado a zona de envio", "manual" if zonas.get("erro") else "falta",
                           zonas.get("erro", ""), ZONA))
    else:
        itens.append(_item("Ligado a zona de envio", "pendente", "", ZONA))
    lista = locais.get("lista") or []
    if lista:
        sem_cep = [local["nome"] for local in lista if not local["cep"]]
        detalhe = ", ".join(f"{local['nome']}: {local['cep'] or 'sem CEP'}" for local in lista)
        itens.append(_item("CEP dos locais de estoque", "falta" if sem_cep else "ok", detalhe,
                           "A Shopify manda como origem o CEP do local (Configuracoes > Locais)."))
        itens.append(_origem_das_tabelas(lista))
    else:
        itens.append(_item("CEP dos locais de estoque", "pendente" if not diag else "manual",
                           locais.get("erro", ""), "Confira em Configuracoes > Locais."))
    itens.append(_peso())
    tabelas = TabelaFrete.objects.filter(active=True, no_checkout=True).count()
    itens.append(_item("Tabelas de frete no checkout", "ok" if tabelas else "falta",
                       f"{tabelas} tabela(s) marcada(s).",
                       "" if tabelas else
                       "Marque \"oferecer no checkout\" em Logistica > Tabelas."))
    itens.append(_item("Embalagem padrao", "manual", "",
                       "Confira em Configuracoes > Frete e entrega > Embalagens "
                       "(a API nao mostra)."))
    quando = diag.get("verificado_em")
    obrigatorios = [item for item in itens if item["titulo"] in OBRIGATORIOS]
    opcionais = [item for item in itens if item["titulo"] not in OBRIGATORIOS]
    faltam = [item for item in obrigatorios if item["estado"] != "ok"]
    return {
        "itens": itens, "verificado_em": parse_datetime(quando) if quando else None,
        "grupos": [("Obrigatorios", obrigatorios), ("Opcionais (so avisam)", opcionais)],
        "pronto": not faltam,
        "selo": (f"Faltam {len(faltam)} de {len(obrigatorios)} obrigatorios" if faltam
                 else "Pronto para o checkout"),
        # Ligar e o proprio cadastro: ele nao entra na lista do que falta para ligar.
        "para_ligar": [_motivo(item) for item in faltam if item["titulo"] != CADASTRADO],
    }


def _motivo(item):
    """Linha do dialogo do "Ligar frete": o que falta e como resolver."""
    if item["titulo"] == ZONA_TITULO and item["estado"] == "pendente":
        return f"{ZONA_TITULO}: depois de ligar, {ZONA[0].lower()}{ZONA[1:]}"
    if item["estado"] == "pendente":
        return f"{item['titulo']}: ainda nao verificado (clique em Verificar configuracao)"
    return f"{item['titulo']}: {item['como'] or item['detalhe']}"
