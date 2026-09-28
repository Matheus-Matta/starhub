# StarHub: detalhes do projeto

Documento de referencia do projeto. `AGENTS.md` e `CLOUDE.md` apontam para ca.
Explica o que o sistema faz, como ele esta montado e onde mexer, com exemplos.

## 1. O que e

O StarHub e um **hub de integracao com marketplaces**. Ele guarda o catalogo
(produtos, categorias), os clientes e os pedidos num lugar so e conversa com:

- **o ERP**, por uma API **identica a do WooCommerce** (`apps/woo_api`). O ERP da
  empresa so sabe integrar com WooCommerce; entao o StarHub se passa por uma loja
  WooCommerce e o ERP funciona sem saber que do outro lado e outro sistema;
- **cada marketplace**, por um app Django proprio (um app por marketplace).

A interface e so o **admin do Django**, com um tema proprio (convertido do
template Metronic "store-inventory") e algumas paginas custom.

Exemplo do fluxo:

```text
ERP --(POST /wp-json/wc/v1/products)--> StarHub --(app do marketplace)--> Mercado Livre, Shopee...
ERP <--(GET /wp-json/wc/v1/orders)----- StarHub <--(pedido do marketplace)-- marketplaces
```

## 2. Stack

| Peca | Uso |
| --- | --- |
| Django 5.1 | admin, models, ORM |
| Django REST Framework + SimpleJWT | API Woo e login JWT |
| Channels + Daphne | servidor ASGI (HTTP + WebSocket) |
| Celery | tarefas em segundo plano (sincronizar com marketplaces) |
| Redis | fila do Celery, channel layer e cache em **prod** |
| PostgreSQL | banco em **prod** (SQLite em dev) |

## 3. Dev x prod

| | Dev (`config.settings.dev`) | Prod (`config.settings.prod`) |
| --- | --- | --- |
| Processos | **um terminal so**: `python manage.py runserver` | daphne, worker e beat **separados** |
| Celery | roda a tarefa na hora, dentro do processo (`CELERY_TASK_ALWAYS_EAGER`) | worker lendo o Redis |
| Channels / cache | memoria | Redis |
| Banco | `db.sqlite3` | PostgreSQL |

Rodar em dev:

```powershell
python -m venv .venv                  # so na primeira vez
.\.venv\Scripts\Activate.ps1          # a cada terminal novo
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py criar_conta "Minha Loja"   # imprime o id da conta (tenant)
python manage.py createsuperuser           # pede esse id no campo "Account"
python manage.py runserver        # abre http://127.0.0.1:8000/admin/
```

Rodar em prod (cada linha e um processo/servico; variaveis em `.env.example`):

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py migrate && python manage.py collectstatic --noinput
daphne -b 0.0.0.0 -p 8000 config.asgi:application
celery -A config worker -l info
celery -A config beat -l info
```

O Daphne **nao serve arquivos estaticos**: o nginx (ou outro proxy) serve
`/static/` a partir de `staticfiles/` e repassa o resto ao Daphne com
`X-Forwarded-Proto` (o prod.py confia nesse cabecalho para saber que e HTTPS).

## 4. Estrutura

```text
config/                 settings (base/dev/prod), urls, asgi, celery, routing (WebSocket)
apps/core/              tema do admin + nucleo multi-tenant: Account, User, AccessProfile,
                        BaseModel, Address, ExternalReference, SalesChannel, Publication*
apps/core/tenant/       conta ativa (ContextVar), TenantManager, middleware, validators
apps/loja/              dados do hub: Produto + VarianteProduto, Categoria, Tag, Cliente,
                        Pedido, ItemPedido, PagamentoPedido, EntregaPedido, Cupom
apps/woo_api/           API compativel com WooCommerce + login JWT + chaves ck_/cs_
templates/admin/        sobrescritas do admin (base, login, index, change_list, fieldset)
templates/components/   componentes reutilizaveis (card, forms, field, badge, sidebar...)
templates/layouts/      layouts fora do admin (auth.html: login e "voce saiu")
static/starhub/         CSS por assunto, JS da casca e sprite de icones
scripts/                check_tamanho_de_arquivo.py (regra das 200 linhas)
```

`example_templetes_react_to_convert_html/` e o template comprado, so para
consulta. Esta no `.gitignore` e **nao** vai para o repositorio (licenca).

## 5. Tema do admin

### 5.1 Como funciona

- `apps.core.admin_app.StarHubAdminConfig` troca o `admin.site` pelo
  `StarHubAdminSite`. Todo `@admin.register` cai nele sozinho.
- `templates/admin/base.html` substitui a casca do Django, mas **mantem todos os
  blocks** (`breadcrumbs`, `content`, `object-tools`, `sidebar`, `extrastyle`...).
  Qualquer tela nativa do admin continua funcionando.
- O CSS do tema carrega **depois** do `extrastyle`: o CSS de cada tela do Django
  entra ali e, no empate, quem carrega por ultimo ganha.
- As cores ficam em `static/starhub/css/tokens.css`, com seletor
  `:root[data-theme]`. Esse arquivo tambem aponta as variaveis do Django
  (`--body-bg`, `--primary`...) para as nossas. Assim listagem, formulario e
  widgets nativos mudam de cor junto, sem CSS por tela.
- Tema claro/escuro/automatico: o botao usa o `admin/js/theme.js` do proprio Django.

Cuidado: `{% block %}` dentro de `{% include %}` **nao** pode ser sobrescrito
pelos templates filhos. Por isso o header (com a trilha `breadcrumbs`) esta
escrito direto no `base.html`, e nao num componente. O teste
`test_trilha_do_change_list_aparece_no_header` pega esse erro.

### 5.2 Componentes

Dois jeitos de usar:

```django
{# 1. Sem conteudo livre: include normal #}
{% include "components/stat_card.html" with rotulo="Pedidos" valor=12 icone="shopping-cart" tom="primary" %}

{# 2. Com conteudo livre ("slot"): tag {% componente %} do apps/core #}
{% componente "card" titulo="Pedidos recentes" icone="clipboard-list" flush=True %}
  {% slot "acoes" %}<a class="btn btn-sm btn-outline" href="...">Ver todos</a>{% endslot %}
  <table class="table">...</table>
{% endcomponente %}
```

| Componente | Para que serve |
| --- | --- |
| `card` | caixa com titulo, acoes (`slot "acoes"`), corpo e rodape (`slot "rodape"`) |
| `alert` | aviso com icone (`tom`: info, success, warning, destructive) |
| `stat_card` | numero de destaque do painel (`eh_moeda=True` formata em reais) |
| `badge` | etiqueta colorida; use `tom=status\|tom_status` |
| `forms` | renderiza **qualquer** form do Django (erros, ocultos, campos) |
| `field` | um campo (rotulo, input, ajuda, erros) |
| `empty_state`, `page_header`, `messages`, `sidebar`, `header_busca`, `user_menu`, `theme_toggle` | pecas da casca |

Tags e filtros (ja carregados em todo template, sem `{% load %}`):
`{% icone "package" "icon-lg" %}`, `{% componente %}`, `{% slot %}`,
`{{ valor|moeda }}` (R$ 1.234,50), `{{ status|tom_status }}`, `{{ user|iniciais }}`.

Icone novo: copie o `<symbol>` do lucide para `static/starhub/img/icones.svg`.

### 5.3 Formularios e widgets

Todo ModelAdmin herda de `TemaModelAdmin` (inline: `TemaTabularInline`),
de `apps/core/admin_base.py`. Com isso, sem configurar campo a campo:

| Campo do Django | Vira |
| --- | --- |
| select comum (`ForeignKey`, `choices`) | botao com lista flutuante; busca a partir de 8 opcoes (`select.js`) |
| select multiplo (`ManyToMany`) | etiquetas com "x" + lista com busca e caixinhas (`multiselect.js`) |
| `DateField` / `DateTimeField` | calendario pt-BR (`dd/mm/aaaa`) + hora (`datas.js`) |
| par inicio/fim | seletor de periodo com dois meses: `periodos = [("promocao_inicio", "promocao_fim")]` |
| `BooleanField` | switch |
| checkbox de lista | checkbox do template (azul com check) |

O `<select>`/`<input>` do Django continua no form, escondido e sincronizado:
validacao, "+" de adicionar relacionado e linhas novas de inline funcionam.
Para um campo NAO virar widget do tema: `attrs={"data-sem-tema": ""}`.
Autocomplete do admin (`autocomplete_fields`) segue o select2, so com o visual do tema.

Rotulo fica EM CIMA do campo (6px); campos na mesma tupla do `fieldsets` viram
colunas iguais. Em form comum use `components/forms.html` e os widgets de
`apps/core/widgets.py` (`DataTema`, `DataHoraTema`, `SwitchTema`):

```django
<form method="post">{% csrf_token %}
  {% include "components/forms.html" with form=form %}
  <button class="btn btn-primary">Salvar</button>
</form>
```

Criacao e edicao usam a mesma estrutura generica de
`templates/admin/change_form.html`: cabecalho com contexto e acoes, cards de
campos empilhados em uma coluna, inlines abaixo e rodape de salvamento fixo.
Todas as secoes com `collapse` iniciam abertas, mas ainda podem ser fechadas.
No celular tambem os campos pareados viram uma coluna. O ModelAdmin continua
definindo os grupos em `fieldsets`;
nao se cria um template diferente para cada model.

#### Botoes "+", lapis e olho dos campos de relacao

Abrem num modal com a pagina do Django num iframe, nao numa janela nova
(`static/starhub/js/modal-relacionado.js`). Ao salvar, o registro ja fica
selecionado no campo e o modal fecha; "Cancelar" dentro do modal so fecha.
Pecas que dependem disso: `X_FRAME_OPTIONS = "SAMEORIGIN"` (settings) e
`templates/admin/popup_response.html` (avisa o `window.parent`). Vale sozinho para
todo campo de relacao do admin, sem configurar nada.

#### Lista de filhos com modal (ex.: variantes do produto)

Em vez de um inline longo, a pagina mostra uma lista; linha e botoes com
`data-modal-url` abrem o form do filho num modal (`static/starhub/js/modal-lista.js`,
contrato em `apps/core/admin_lista_modal.py`). Exemplo real: `lista_variantes` em
`apps/loja/admin/variantes.py` + `templates/admin/loja/lista_variantes.html`.
Salvou no modal: a pagina recarrega (ou salva o pai, se ele foi editado).

#### Campos que so aparecem conforme outro

Declare no ModelAdmin (ou no inline, com campos da mesma linha) o atributo
`condicoes` (`apps/core/admin_condicoes.py`); o `static/starhub/js/condicoes.js`
mostra e esconde na hora:

```python
condicoes = {
    "#componentes-group": {"campo": "tipo", "em": ["bundle"]},        # inline inteiro
    "url_externa": {"campo": "tipo", "em": ["external"]},             # campo
    "inventory_quantity": {"campo": "manage_inventory", "marcado": True},
    "sale_starts_at": {"campo": "sale_price", "preenchido": True},
    "tags": [regra_a, regra_b],                                        # basta uma valer
}
```

- Esconder e so visual: o campo continua no POST. A obrigatoriedade de cada escolha
  (CNPJ quando o tipo e CNPJ, URL no produto externo, lista na elegibilidade do cupom)
  e validada no servidor, com erro no campo. Campo com erro nunca fica escondido.
- Nome errado numa regra faz o teste `test_toda_regra_aponta_para_campo_e_inline_que_existem` falhar.

#### Placeholder, mascara, validacao e colunas

Tudo automatico pelo `TemaMixin`, a partir de `apps/core/ui/entradas.py`:

| O que | Onde | Exemplo |
| --- | --- | --- |
| placeholder (exemplo do que digitar) | `PLACEHOLDERS` (`"campo"` ou `"Model.campo"`) | CEP `00000-000`, SKU `CAM-AZUL-M` |
| mascara ao digitar | `MASCARAS` + `static/starhub/js/mascaras.js` | cep, cpf, cnpj, cpf-cnpj, telefone, uf, pais, moeda, digitos |
| largura (colunas de 12) | `LARGURAS` ou `larguras = {...}` no ModelAdmin | `("postal_code", "address_1", "number")` = 3 + 7 + 2 |

- Campo comum ocupa 6 colunas (meia linha). No celular tudo vira uma coluna.
- A mascara so ajuda: o admin usa `novalidate`, entao quem valida e o servidor
  (`apps/core/validators.py`: CPF, CNPJ, telefone, GTIN, UF), com erro no campo.
  CPF/CNPJ chegam com pontos e sao gravados so com digitos (`CampoSoDigitos`).
- Endereco estrangeiro passa: CEP com letras e telefone com `+` nao sao mascarados,
  e CEP/UF so sao conferidos quando o pais e BR.
- Campo novo sem placeholder: o teste `test_todo_campo_de_digitar_tem_placeholder` falha.
- Conta e origem nao aparecem para o usuario comum; o superusuario as ve na secao
  "Conta" (`apps/core/admin_conta.py`).

#### Campos JSON (tags, imagens, metadados, listas, objetos)

JSON cru nao aparece para o usuario. Cada campo JSON ganha o tratamento do
seu tipo, declarado no ModelAdmin com `campos_json`
(`apps/core/json_widgets.py`; configuracoes da loja em `apps/loja/admin/campos.py`):

| Widget | Para que | Exemplo |
| --- | --- | --- |
| `TagsTema(sugestoes=...)` | etiquetas criadas na hora (Enter, virgula, Tab, colar "a, b") | (livre; `Produto.tags` agora e M2M de `Tag`) |
| `ImagensTema(multiplas=True, pasta=...)` | galeria: enviar (arrastar/clicar), colar URL, alt, reordenar, remover | `Categoria.imagem` (produto usa `MidiaProduto`) |
| `ChaveValorTema()` | linhas chave = valor | `metadados` |
| `ListaTema(colunas, com_id)` | tabela com colunas `texto`, `numero`, `dinheiro`, `switch`, `tags`, `escolha` (select de `opcoes`) e `valor` (`10`, `true`, `["a"]` viram numero/booleano/lista) | frete, taxas, cupons, atributos |
| `ObjetoTema(campos, extras)` | grade de campos fixos; `extras=True` guarda o que o ERP mandar a mais (numero e objeto continuam do tipo que eram). Sem `campos`: dicionario livre chave = valor | endereco, dimensoes, `SalesChannel.settings` |
| `TagsTema(simples=True)` | etiquetas gravadas como lista de textos `["read", "write"]` | `ChaveApi.scopes` |
| `RegrasTema()` (`apps/core/json_regras.py`) | uma linha por condicao (grupo, campo, operador, valor); grava `{"all": [...], "any": [...]}` do motor de regras | `PublicationPolicy.rules` |

Sem declarar nada, o `TemaMixin` usa o `widget_padrao`: `metadados` vira chave = valor e
todo JSON com `default=dict` vira dicionario livre. Lista com formato proprio precisa
ser declarada; o teste `test_nenhum_campo_json_do_admin_aparece_cru` falha se faltar.

```python
@admin.register(Produto)
class ProdutoAdmin(TemaModelAdmin):
    campos_json = {"tags": TagsTema(), "metadados": ChaveValorTema()}
```

- O valor enviado continua sendo o JSON (textarea escondido); o servidor
  revalida e normaliza por tipo (`apps/core/json_normalizar.py`): tag sem
  repetir e mantendo `id`, metadado sem chave descartado, dinheiro `"15,9"` ->
  `"15.90"` (texto, formato Woo), valor invalido volta como erro no campo.
- Imagem enviada: conferida pela assinatura do arquivo (PNG/JPG/GIF/WEBP, ate
  5 MB; um `.exe` renomeado para `.png` e recusado), gravada em
  `MEDIA_ROOT/<pasta>/` com nome aleatorio. A API Woo devolve a URL completa.
  Em producao o nginx precisa servir `/media/`. Limitacao: se OUTRO campo do
  mesmo formulario der erro, o arquivo ja gravado fica orfao no MEDIA.

### 5.4 Listagem, filtros e busca

- A listagem inteira e um data grid: toolbar, busca, acoes em massa, tabela e
  paginacao ficam no mesmo card (`templates/admin/change_list.html`). Em tela
  estreita a toolbar empilha e somente a tabela ganha rolagem horizontal.
- No desktop o card ocupa a altura disponivel da janela. Toolbar, acoes e
  paginacao ficam fixas; somente o corpo da tabela rola e o cabecalho das
  colunas continua visivel.
- A busca da listagem nao tem botao: envia sozinha 600 ms depois da ultima
  tecla e devolve o foco ao campo depois do recarregamento.
- Produto aparece em uma celula rica com miniatura, nome e SKU. Pedido mostra
  avatar, nome e e-mail do cliente, alem da quantidade de itens. Sem imagem,
  os componentes usam icone ou iniciais como alternativa.
- Filtros ficam numa **gaveta** (drawer) pela direita, aberta pelo botao
  "Filtros" (com contador) ao lado do "Adicionar". Altura da tela inteira,
  so o miolo rola. Depois de clicar num filtro a gaveta volta aberta.
- Filtro de data: `list_filter = [("criado_em", FiltroPeriodo), ...]`
  (`apps/core/filtros.py`). Usa `__date__gte/__date__lte`: "ate 30/09" inclui o dia 30 inteiro.
- Busca do header (Ctrl+K): procura em todo ModelAdmin que tem `search_fields`
  (`apps/core/busca.py`). Model novo com `search_fields` entra sozinho.

### 5.5 Espacamento

Uma regra so (`static/starhub/css/layout.css`): pagina, `#content`,
`#content-main` e o form do admin sao colunas com `gap: var(--gap-pagina)`
(20px; 30px a partir de 1024px). Card, `.module`, aviso e cabecalho **nao tem
margem**. Nao ponha `margin-top`/`margin-bottom` em card: ajuste o gap.

### 5.6 Pagina custom no tema

Exemplo real: `ChaveApiAdmin.guia_view` (`apps/woo_api/admin.py`).

1. Acrescente a URL no `get_urls()` do ModelAdmin, com `self.admin_site.admin_view(...)`.
2. Monte o contexto com `**self.admin_site.each_context(request)` (menu, usuario, tema).
3. O template estende `admin/base_site.html` e preenche `breadcrumbs`, `content_title` e `content`.
4. Para aparecer no menu lateral: `STARHUB_MENU_PAGINAS` no `config/settings/base.py`.

Pagina fora do admin (ex.: login): estenda `layouts/auth.html`.

## 6. API WooCommerce (`apps/woo_api`)

### 6.1 Autenticacao

| Jeito | Como o ERP usa | Quem pode |
| --- | --- | --- |
| Chave ck_/cs_ (padrao Woo) | Basic Auth `ck_...:cs_...` ou `?consumer_key=&consumer_secret=` | a permissao da chave: leitura, escrita ou as duas |
| JWT (plugin do WordPress) | `POST /wp-json/jwt-auth/v1/token` e depois `Authorization: Bearer <token>` | usuario com a permissao `woo_api.usar_api` (ou superusuario) |

A chave pertence a **conta** (nao a um usuario) e e criada no admin (Nucleo >
Chaves de API). Quem entra com ela so enxerga os dados daquela conta. Ela aparece
inteira **uma vez so**; o banco guarda apenas o hash SHA-256.

```bash
curl -X POST https://hub.exemplo.com/wp-json/jwt-auth/v1/token \
  -H "Content-Type: application/json" -d '{"username": "erp", "password": "..."}'
# {"token": "...", "user_email": "...", "user_nicename": "erp", "user_display_name": "ERP"}
```

O token vale `JWT_ACESSO_DIAS` dias (7, como no plugin). O login tem limite de
20 tentativas por minuto.

### 6.2 Rotas

Base: `/wp-json/wc/v1/`. Sem barra no final, como no WordPress (com barra tambem funciona).

| Recurso | Lista / cria | Le / altera / exclui | Lote |
| --- | --- | --- | --- |
| Produtos | `products` | `products/<id>` | `products/batch` |
| Categorias | `products/categories` | `products/categories/<id>` | `products/categories/batch` |
| Clientes | `customers` | `customers/<id>` | `customers/batch` |
| Pedidos | `orders` | `orders/<id>` | `orders/batch` |

- Alterar aceita `PUT`, `PATCH` e `POST`, e so mexe no campo enviado.
- Lista: `page`, `per_page` (1 a 100), `offset`, `search`, `include`, `exclude`,
  `after`, `before`, `modified_after`, `orderby`, `order`, alem dos filtros de cada
  recurso (`sku`, `status`, `category`, `email`, `customer`...). Totais nos
  cabecalhos `X-WP-Total` e `X-WP-TotalPages`.
- Excluir: produto e pedido vao para a lixeira sem `force=true`; cliente e
  categoria exigem `force=true` (501 sem ele, igual ao Woo). No lote, sempre `force`.
- Lote: ate 100 objetos; cada item roda na sua transacao, e o item com erro
  volta como `{"id": ..., "error": {...}}` sem desfazer os outros.
- Datas: `date_created` no horario da loja (America/Sao_Paulo) e `date_created_gmt` em UTC.
- Dinheiro sai como texto com 2 casas (`"19.90"`). Numero no JSON de entrada
  (`19.9`) e lido como Decimal, nunca como float.
- `billing`/`shipping` guardam campos extras (cpf, cnpj, number, neighborhood)
  do plugin Brazilian Market e os devolvem iguais.

### 6.3 Erros

Mesmo formato e mesmos codigos do Woo, porque o ERP decide pelo `code`:

```json
{"code": "product_invalid_sku", "message": "SKU invalido ou repetido.", "data": {"status": 400, "resource_id": 12}}
```

Codigos usados: `rest_invalid_param`, `rest_missing_callback_param`,
`woocommerce_rest_<recurso>_invalid_id` (404), `product_invalid_sku`,
`registration-error-email-exists`, `term_exists`,
`woocommerce_rest_invalid_product_id`, `woocommerce_rest_invalid_customer_id`,
`woocommerce_rest_trash_not_supported` (501), `woocommerce_rest_already_trashed` (410),
`woocommerce_rest_authentication_error` (401), `jwt_auth_invalid_token` (403),
`[jwt_auth] incorrect_password` (403),
`woocommerce_rest_request_entity_too_large` (413).

**Excecao deliberada a regra "409 para conflito":** SKU, e-mail e categoria
repetidos voltam **400**, como no WooCommerce. O ERP foi feito para o Woo e
espera 400 com esses codigos. A regra do 409 continua valendo para o resto do projeto.

### 6.4 O que ainda nao existe

- variacoes de produto (`products/<id>/variations`): `variations` sai sempre `[]`;
- reembolsos, notas de pedido, webhooks, tags e atributos como rotas proprias,
  `system_status` e `reports`;
- cupom e so registrado em `coupon_lines`: o desconto precisa vir no `total` de cada item;
- criar pedido pela API **nao baixa estoque** nem soma `total_sales`;
- autenticacao OAuth 1.0a (Woo sobre HTTP): use HTTPS com Basic ou JWT.

## 7. Novo marketplace

Cada marketplace e um app: `apps/<marketplace>/` (ex.: `apps/mercado_livre/`).

```text
apps/mercado_livre/
  models.py      credenciais/conta e o vinculo "produto do hub <-> anuncio"
  cliente.py     chamadas HTTP a API do marketplace (so isso)
  sincronizar.py regras de ida e volta (produto, estoque, preco, pedido)
  tasks.py       @shared_task que o Celery roda (descoberto sozinho)
  admin.py       telas no tema (icone em STARHUB_MENU_ICONES)
  tests/
```

- Os dados canonicos ficam em `apps/loja`. O app do marketplace le e grava la;
  ele nao cria um catalogo paralelo.
- Chamada externa sempre em tarefa do Celery, nunca dentro da requisicao do admin.
  Em dev ela roda na hora; em prod vai para o worker.
- Tempo real (se precisar): rotas em `config/routing.py`.

## 8. Regras que valem aqui

- **Multi-tenant:** todo model de negocio herda `apps.core.models.BaseModel` e o
  `objects` so enxerga a conta ativa. Requisicao do admin ativa a conta pelo
  `TenantMiddleware`; a API Woo ativa depois de autenticar (`WooView.initial`).
  Celery, script e comando: `with tenant_context(conta): ...`. Sem conta ativa, a
  consulta levanta `TenantContextMissing` (de proposito). `all_objects` ignora a
  conta: so em rotina interna explicita (ex.: achar a chave ck_ antes de saber a conta).
- **Admin, usuario comum x superusuario** (`apps/core/admin_conta.py`): o comum ve so
  a conta dele e o form nao tem o campo conta (o registro recebe a dele). O
  superusuario ve todas as contas (coluna e filtro "Conta"), escolhe a conta ao
  criar e so a ve ao editar. Isso vale SO em `/admin/`: na API ele fica na conta dele.
  Todo ModelAdmin que herda `TemaModelAdmin` ganha esse comportamento sozinho.
- **Produto:** preco, SKU e estoque ficam na `VarianteProduto`; produto simples tem
  uma variante padrao (`criar_produto(nome, sku=..., price=...)`).
- **Pedido:** enderecos sao copias proprias (`core.Address`), nunca o endereco vivo
  do cliente; o item guarda nome/SKU/preco vendidos.

- Dinheiro: `apps/loja/dinheiro.py`. `dinheiro()` arredonda uma vez, na entrada,
  e recusa float. O total do pedido e a soma das linhas ja arredondadas
  (`apps/loja/totais.py`). Exemplo: 2 x R$ 10,05 com 10% = 9,05 + 9,05 = 18,10.
- Unicidade (SKU, e-mail, slug, chave) e garantida pelo **banco**. A conferencia
  antes de gravar serve so para dar a mensagem certa.
- Escrita na API: `transaction.atomic` + `select_for_update` e releitura depois do lock
  (`Recurso.obter_para_escrita`).

## 9. Verificacao

```powershell
python -m pytest                              # todos os testes
ruff check .
python scripts/check_tamanho_de_arquivo.py    # regra das 200 linhas
python manage.py check
python manage.py makemigrations --check --dry-run
```
