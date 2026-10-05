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
| Processos | **um terminal so**: `python manage.py runserver` | uvicorn, worker e beat em **containers separados** |
| Celery | roda a tarefa na hora, dentro do processo (`CELERY_TASK_ALWAYS_EAGER`) | worker lendo o Redis |
| Channels / cache | memoria | Redis |
| Banco | `db.sqlite3` | PostgreSQL (fora do compose) |
| Estaticos | runserver | WhiteNoise (no proprio app) |

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

Dados para testar (10+ por model, imagens `static/starhub/img/demos`): `python manage.py
gerar_demo` (conta do `ACCOUNT_ADMIN` do .env ou `--conta <slug>`). `--limpar` recria e
`--remover` apaga, mexendo so no que o demo criou (`apps/loja/demo/`). Recusa com
`DEBUG=False`.

Rodar em prod (Docker). A imagem sai do GitHub (`.github/workflows/docker.yml`): push
na `main` testa (ruff, pytest, checks) e publica `ghcr.io/matheus-matta/starhub:latest`
e `:sha-<commit>`; tag `v1.2.3` publica `:v1.2.3`. No servidor, com `docker-compose.yml`
e o `.env` (parte PRODUCAO do `.env.example`: banco, CORS, segredo, dominios):

```bash
docker login ghcr.io            # pacote privado: usuario do GitHub + token com read:packages
docker compose pull && docker compose up -d
docker compose logs -f web worker
docker compose run --rm web python manage.py criar_conta_inicial   # primeira vez
```

| Servico | O que roda |
| --- | --- |
| `migrate` | `migrate --noinput` uma vez a cada subida; os outros esperam ele terminar |
| `web` | `uvicorn config.asgi:application` (HTTP + WebSocket), `WEB_WORKERS` processos, porta `WEB_PORT` |
| `worker` | `celery -A config worker` (`CELERY_CONCURRENCY` tarefas) |
| `beat` | `celery -A config beat` (hoje sem tarefa agendada) |
| `redis` | fila do Celery, cache e channel layer (volume `redis`) |

- **Proxy na frente** (nginx, Caddy, Traefik) faz o TLS e repassa ao `web` com
  `X-Forwarded-Proto` e o `Upgrade` do WebSocket (`/ws/`). Sem proxy, so para teste:
  `DJANGO_SSL_REDIRECT=0`.
- **Estaticos**: WhiteNoise serve `/static/` (gerado no build da imagem). **Media**
  (`/media/`, volume `media` compartilhado por web e worker) e servida pelo app com
  `SERVIR_MEDIA=1`; com o nginx servindo a pasta, ponha `0`.
- **CORS**: `CORS_ALLOWED_ORIGINS` (dominios da loja) e `CORS_URLS_REGEX` (rotas;
  padrao: avaliacoes do tema). **Banco**: `POSTGRES_*`, `POSTGRES_SSLMODE`.
- **Logs** saem no `docker compose logs` (`LOG_LEVEL`).

## 4. Estrutura

```text
config/                 settings (base/dev/prod), urls, asgi, celery, routing (WebSocket)
apps/core/              tema do admin + nucleo multi-tenant: Account, User, AccessProfile,
                        BaseModel, Address, ExternalReference e tabelas legadas ocultas
apps/core/tenant/       conta ativa (ContextVar), TenantManager, middleware, validators
apps/integracoes/       configuracao comum das lojas + historico das tarefas de integracao
apps/shopify/           cliente, consultas, webhooks e tarefas Celery do Shopify
apps/woocommerce/       cliente REST v3, importacao, webhooks, envio e tarefas do WooCommerce
apps/suri/              Suri Shop (by Totvs, venda pelo WhatsApp): catalogo, pedidos e envio
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
| `TextoHTMLField` | editor visual de texto rico, com opcao de editar o HTML |
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
No admin do filho, `pai_da_lista = "produto"` esconde nesse modal o campo do pai
e a secao "Conta" (a conta vem do pai).

Inline curto (poucas colunas) com a mesma cara de lista: `template =
"admin/edit_inline/lista.html"` no inline, com `relacao_so_adicionar` nos selects
(so o "+", sem lapis/olho). Exemplos: `OpcoesInline` e `ComponenteInline` (loja).

#### Grupos fixos e perfis iniciais

`apps/core/perfis_padrao.py` define os grupos fixos (Administrador, Gerente, Vendas,
Catalogo, Estoque, Financeiro, Atendimento, Somente leitura, Integracao API) e as
permissoes de cada um. A migration `core.0003` cria os grupos e os perfis das contas
que ja existiam; conta nova ganha os perfis (`is_system`) pelo sinal `post_save`; e
todo `migrate` reacerta as permissoes dos grupos (model novo entra sem migration).
Perfil do sistema nao e excluido nem troca de codigo/grupo no admin.

#### Botao "Logs" da edicao

Toda pagina de edicao (TemaMixin) mostra "Logs" para quem pode ver logs: abre
"Entradas de log" (auditlog) filtrada so por aquele registro (`?registro=<tipo>-<pk>`),
mais recentes primeiro. Usuario comum so ve logs da conta dele (a conta vai no
`additional_data` do log). Tudo em `apps/core/admin_logs.py`.
Cada log tambem guarda a ORIGEM (`apps/core/origem.py`): `admin`, `woo_api` (com a
chave ou o usuario do JWT) ou `sistema`; aparece na coluna "usuario" e no filtro
"origem". Integracao nova (Shopify etc.) envolve o trabalho em
`with origem("shopify", via="Loja X"):`.

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
- Coluna **codigo externo** (`apps/loja/admin/codigo_externo.py`): o id do vinculo do
  marketplace de origem (`gid://shopify/Product/123` aparece `123`; pedido usa
  `external_number`); sem vinculo, `-`. Todo registro tem `uuid` (BaseModel), mas ele
  so aparece no detalhe, somente leitura; a chave primaria e o `id` da API Woo seguem
  inteiros. Onde usar qual: **uuid** no endereco dos webhooks, em que o id em sequencia
  deixaria testar 1, 2, 3 (avaliacoes do tema ficaram com o id, a pedido), e
  em identificador que vai para outro sistema e precisa ser estavel (handle
  `avaliacao-<uuid>` na Shopify). **id inteiro** na API Woo (contrato do ERP), no admin
  e nas tarefas internas.
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
A integracao tambem aceita produtos e categorias em `/wp-json/wc/v3/products`: consulta,
categorias podem ser criadas e alteradas, mas produtos existentes aceitam somente alteracao
de `regular_price`, `sale_price` e `stock_quantity`. Filtros/corpos aparecem no terminal.

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
- Servicos do pedido (montagem, impermeabilizacao...) ficam em
  `starhub.servicos` do pedido. No GET de `orders` cada servico sai no
  `line_items[].meta_data` do seu item duas vezes: `{"key": "starhub", ...}` e
  `epofw_field_<n>` no formato do plugin EPOFW (value em texto JSON), que e o que
  o ERP le (`apps/woo_api/recursos/pedidos_epofw.py`). Na volta os dois formatos
  sao aceitos; vindo os dois, vale o `starhub`, sem duplicar.

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

### 6.4 Modo "encaminhar pedidos a loja WooCommerce"

Opcao em Integracoes > WooCommerce, no topo da tela, que so o superusuario ve e muda
(`ConfiguracaoIntegracao.encaminhar_pedidos`, padrao desligado). Desligada, nada muda.
Ligada, as rotas de pedido (`wc/v1/orders...` e `wc/v3/orders...`, lista, detalhe e
lote) autenticam o ERP como sempre e depois repassam a requisicao inteira para a loja
Woo: mesma rota depois de `/wp-json/`, mesma query (sem a credencial do ERP), mesmo
corpo, autenticada com a chave `ck_/cs_` da configuracao. A resposta da loja volta ao
ERP como veio: status, JSON, `X-WP-Total`, `X-WP-TotalPages` e `Link` (reescrito para o
endereco do hub). Erro da loja volta igual; loja sem resposta = 502
`starhub_loja_indisponivel`. Cada encaminhamento vira uma tarefa "Encaminhar pedido a
loja" com a requisicao e a resposta. Codigo: `apps/woo_api/views/encaminhar.py` (gancho
no `initial` das views de pedido) e `apps/woocommerce/encaminhar.py` (o repasse HTTP).
Produtos, clientes e categorias nao sao encaminhados.

### 6.5 O que ainda nao existe

- variacoes de produto (`products/<id>/variations`): `variations` sai sempre `[]`;
- reembolsos, notas de pedido, webhooks, tags e atributos como rotas proprias,
  `system_status` e `reports`;
- cupom e so registrado em `coupon_lines`: o desconto precisa vir no `total` de cada item;
- criar pedido pela API **nao baixa estoque** nem soma `total_sales`;
- autenticacao OAuth 1.0a (Woo sobre HTTP): use HTTPS com Basic ou JWT.

## 7. Integracoes com marketplaces

### 7.1 Configuracao da loja

`apps/integracoes` guarda a parte comum a qualquer marketplace. Existe uma
`ConfiguracaoIntegracao` por conta e plataforma (Shopify, WooCommerce, Suri Shop). Cada uma tem
uma entrada na secao Integracoes da barra lateral, com o logo da plataforma, que abre
uma pagina unica (a mesma tela, `templates/admin/integracoes/configuracao.html`; o que
muda por plataforma fica em `TELAS`, `apps/integracoes/admin.py`).

A pagina tem dominio permanente da loja, token de acesso, segredo do app
e URL publica dos webhooks. Nome (`Shopify`) e versao da API sao internos e fixos;
o URL de webhook inicia com protocolo e dominio da pagina aberta. Token e segredo
ficam criptografados e nunca voltam preenchidos para o navegador. A matriz de
permissoes separa **Receber** e **Enviar**, por recurso e operacao amigavel: Buscar,
Criar, Atualizar e Excluir.

Os botoes da pagina fazem o seguinte:

- **Sincronizar loja:** enfileira uma tarefa Celery, consulta somente os recursos
  com `Receber > Buscar` habilitado e cadastra localmente. Produtos vem 10 por pagina
  ate a ultima (custo 923 de 1000); produto com mais de 10 variantes, colecoes ou fotos
  e completado por uma busca por id (`apps/shopify/produtos_busca.py`). Nesta
  importacao o produto que ja existe no hub e **sobrescrito** pelo da loja (nome,
  textos, SEO, status, slug, tags, categorias, variantes); webhook, produto faltante
  de pedido e eco de exportacao mantem o do hub. Item que da erro nao derruba a
  sincronizacao: vai para a lista de falhas e os outros seguem (erro de credencial ou
  rede com a loja continua derrubando);
- **Cadastrar webhooks:** usa a Admin GraphQL API para registrar somente os eventos
  `Receber > Criar/Atualizar/Excluir` habilitados. Antes, remove as assinaturas que
  ja usam os mesmos endpoints para que o recadastro seja seguro;
- **Ver tarefas:** abre `ExecucaoIntegracao`, com estado, progresso, etapa e mensagem.
  Tarefa que terminou com 1+ item com erro ou aviso fica **Concluida com falhas**
  (`completed_errors`); a tela mostra a tabela "Falhas por item" (recurso, item no hub,
  id no marketplace, motivo), vinda do campo `falhas` (`apps/integracoes/falhas.py`).
  Tudo falhou ou erro geral continua **Falhou**.

Pedido de marketplace: `number` e sempre do hub (`SH-...`); o numero da loja (ex.
`1001` do Shopify) fica em `external_number`. A migracao `loja.0014` moveu os pedidos
importados antes dessa regra.

O receptor fica em
`/integracoes/shopify/webhook/<uuid da configuracao>/<recurso>/`. O endereco antigo,
com o id inteiro no lugar do uuid, continua aceito para os webhooks cadastrados antes
da troca; "Cadastrar webhooks" remove os antigos e cadastra com o uuid. Ele valida o HMAC com
o segredo do app e devolve `202` depois de enfileirar o processamento. Assim a
requisicao do Shopify nao espera a gravacao do catalogo. A matriz **Enviar** e
usada pelo envio do hub para os marketplaces (secao 7.2).
Se chegar `update` antes do `create`, o item ausente e criado e vinculado somente
quando `Receber > Criar` estiver habilitado para aquele recurso.
Produtos novos sao adaptados ao catalogo canonico com todas as variantes, opcoes,
SKU, preco, promocao, estoque e codigo de barras. Imagens de `create` e `update`
sao validadas, baixadas do CDN Shopify para `/media/produtos/` e vinculadas as
variantes; o ID externo evita baixar novamente em webhooks repetidos.
Cupons sao identificados pelo **nome** na conta (indice unico `cupom_nome_conta_unico`);
o `code` do Cupom e interno, aleatorio e fica fora do admin. Codigo de pedido que o
hub ainda nao conhece e consultado no Shopify (`codeDiscountNodeByCode`) e o cupom
nasce completo (tipo, valor, datas, limites, minimo, clientes, produtos/colecoes,
combinacao) em `apps/shopify/cupons.py` + `cupons_mapa.py`; o que o Cupom nao tem vai
para `metadata["shopify"]`. O codigo usado fica numa `ExternalReference`
`cupons_codigos`, entao o proximo pedido com ele nao consulta o Shopify de novo.
Em desenvolvimento (`DEBUG=True`), o terminal registra os cabecalhos de contexto e
o JSON recebido, sem registrar o HMAC ou qualquer credencial; em producao, nao.

As tabelas antigas de politica/estado/canal nao aparecem mais no admin. Elas foram
mantidas no banco nesta transicao para nao apagar dados existentes sem uma migracao
de conversao explicita.

### 7.2 Envio do hub para os marketplaces

Um unico ponto leva as alteracoes do hub aos marketplaces: os signals de
`apps/integracoes/sinais.py` (pre_save, post_save, post_delete e o M2M de
categorias/tags do produto) chamam o `Distribuidor`
(`apps/integracoes/envio/distribuidor.py`). O fluxo de um save:

1. **Recurso:** Produto -> `produtos`, Categoria -> `categorias`, Cliente ->
   `clientes`, Pedido -> `pedidos`, Cupom -> `cupons`, Avaliacao -> `avaliacoes`. Variante que so mudou
   `inventory_quantity`, `stock_status` ou `low_stock_amount` -> `estoque` (pk da
   variante); qualquer outra mudanca, variante nova ou excluida -> `produtos` update
   do produto pai. `inventory_policy` e `manage_inventory` contam como produto: no
   marketplace sao campos da variante, nao quantidade no local.
2. **Mudou de verdade?** O pre_save guarda a linha do banco e o post_save compara
   (ignora `updated_at`/`updated_by`; `"19.90"` e `Decimal("19.90")` sao iguais).
   Sem mudanca, nada sai.
3. **Destinos:** as `ConfiguracaoIntegracao` ativas da conta cuja plataforma tem
   enviador registrado, **menos a da origem** (`apps.core.origem.atual()`), e so as
   com `Enviar > recurso > operacao` ligado. O que veio do Shopify vai para os outros,
   nunca volta ao Shopify; o que nasceu no admin, na API Woo ou num comando vai para
   todos.
4. **Depois do commit, um por registro:** `envio/transacao.py` agenda com
   `transaction.on_commit` (rollback nao envia) e junta varias gravacoes do mesmo
   registro na mesma transacao num envio so (create + update = create; + delete =
   delete).
5. **Tarefa:** `apps/integracoes/tasks.py::enviar_alteracao` roda na conta da
   configuracao e com a origem = plataforma de destino (o que ela gravar no hub nao
   volta para ela), confere de novo a matriz e chama o marketplace. O rastro fica em
   **Tarefas** (menu Nucleo) (tipo *Enviar alteracao*): `produtos update 15:
   atualizado`. Operacao que o marketplace nao aceita (`EnvioNaoSuportado`) conclui
   como `ignorado: ...`; erro de rede/API repete 3 vezes com espera (30s, 60s, 120s)
   no worker e depois fica **Falhou** com a mensagem. Em dev (Celery eager) nao
   repete: falha na hora, sem travar a tela.

**Requisicao e resposta.** Tarefa de webhook recebido (Shopify, WooCommerce, Suri) e de
pedido encaminhado a loja (secao 6.4) mostra os cards "Requisicao recebida" (metodo,
caminho, query, cabecalhos e corpo em JSON) e "Resposta" (status, cabecalhos e corpo).
Ficam em `parametros["requisicao"]`/`["resposta"]` (`apps/integracoes/trafego.py`);
cabecalho ou query com credencial (Authorization, cookie, consumer_key) nao e guardado
e corpo acima de 200 mil caracteres e cortado.

**Tela da tarefa e Retomar.** A tarefa aberta mostra uma barra que anda sozinha
por WebSocket (`/ws/tarefas/<id>/`, `apps/integracoes/consumers.py`, exige login,
permissao e a conta da tarefa): cada gravacao de andamento da tarefa empurra o estado
(`apps/integracoes/tempo_real.py`), sem a tela perguntar. O formato e o do
`celery_progress` (`ProgressRecorder` no Celery + `websockets.js` na tela); o banco
continua sendo a verdade (`apps/integracoes/progresso.py`). A sincronizacao conta os itens da loja antes
(`ShopifyClient.contar`) e anda por item: "Produtos: 350 de 1200". Tarefa que
falhou volta para a fila na MESMA linha pelo botao **Retomar** ou pela acao em lote
(`apps/integracoes/retomar.py`). Envio e webhook guardam em
`parametros["reenvio"]` o que precisam para isso; webhook de antes dessa versao nao
guardou o corpo e nao pode ser retomado (use Sincronizar loja). No dev, a tarefa
roda dentro do runserver: parar ou reiniciar o servidor marca as abertas como
**Falhou** (`apps/integracoes/orfas.py`), em vez de deixar "Processando" para sempre.

Imagens da importacao sao baixadas para o MEDIA. Foto acima de 5 MB vem reduzida
pela CDN da Shopify (`width=2048`, depois 1600 e 1200); foto que nao baixa vira
aviso na tarefa e nao derruba o produto nem as outras fotos.

No marketplace, `EnviadorRecurso.enviar` (base) trava a linha canonica
(`select_for_update`) e rele o vinculo (`ExternalReference`) depois do lock: com
vinculo atualiza; sem vinculo cria e vincula (em `update`, so se `Enviar > criar`
estiver ligado); `delete` exclui e desfaz o vinculo.

Nao geram envio (nao disparam signal): `QuerySet.update()`, `bulk_create`,
`bulk_update`, `tag.produtos.add(...)` pelo lado da tag e filhos fora do mapa
(item do pedido, endereco do cliente, midia) enquanto o pai nao for salvo. Quem
precisa que a mudanca saia usa `save()`.

### 7.3 Avaliacoes de produto (tema Shopify)

O cliente logado avalia o produto pelo tema da loja; o hub guarda, o operador
modera e so a aprovada vai para a loja. O hub e a fonte da verdade.

```text
tema (Liquid assina o token) --POST multipart--> /integracoes/shopify/avaliacoes/<id da configuracao>/
  -> Avaliacao PENDENTE (apps/loja)  -> moderacao no admin (Loja > Avaliacoes)
  -> aprovar/rejeitar = save() -> Distribuidor -> recurso "avaliacoes" -> tarefa Celery
  -> metaobject avaliacao_produto + media/total/lista no produto da loja
```

- **Model:** `apps/loja/models/avaliacao.py` (`Avaliacao`, `FotoAvaliacao`). Uma por
  cliente e produto (indice unico `avaliacao_unica_por_cliente`), nota 1 a 5
  (check), ate 3 fotos, comentario ate 1500. `compra_verificada` = existe pedido
  do cliente com o produto em `Pedido.PAGOS`. Regras em `apps/loja/services/avaliacoes.py`.
- **Quem e o cliente:** token `"<customer.id>:<product.id>:<timestamp>"` assinado
  no Liquid com `hmac_sha256` e o segredo das configuracoes do tema
  (`settings.reviews_secret`). O mesmo segredo vai em Integracoes > Shopify >
  Segredo das avaliacoes (nao e o client secret do app). Vale 2 horas.
  Detalhes em `apps/shopify/avaliacoes_token.py`.
- **API** (`apps/shopify/avaliacoes_api.py`), o endereco aparece na tela da integracao:

| Metodo | Corpo / query | Respostas |
| --- | --- | --- |
| `POST` | multipart: `payload`, `sig`, `nota`, `comentario`, `fotos` (ate 3, PNG/JPG/GIF/WEBP ate 5 MB) | 201 criada; 400 entrada errada (`campo` diz qual); 401 token; 404 produto; 409 ja avaliou, produto fechado ou cliente ainda nao sincronizado; 429 limite |
| `GET` | `?payload=...&sig=...` | `{"avaliou": true, "status": "pendente"}` |

  Erro sai como `{"erro": "<codigo>", "mensagem": "...", "campo": "..."}`. Limite:
  10 envios por hora por IP (`DEFAULT_THROTTLE_RATES["avaliacoes"]`).
- **Importar planilha** (botao na lista de avaliacoes, `apps/loja/admin/avaliacoes_importar.py`):
  o lojista cria as proprias avaliacoes. .xlsx ou .csv (modelo para baixar na tela) com
  `email`, `nome`, `sobrenome`, `sku`, `nota`, `comentario` e, opcionais, `nome_publico`,
  `status` (vazio = aprovada) e `data`. Roda numa tarefa "Importar avaliacoes"
  (`apps/loja/tasks.py`) com barra, falhas por linha e Retomar. Cliente novo nasce so no
  hub (`_sem_envio`, nao vira conta na loja); mesmo cliente + produto atualiza em vez de
  duplicar (`apps/loja/services/avaliacoes_importacao.py`).
- **Moderacao:** acoes "Aprovar e publicar" e "Rejeitar" na lista, ou o campo
  status na edicao (motivo aparece ao rejeitar). O texto do cliente nao e editavel.
- **Envio** (`apps/shopify/envio/avaliacoes.py`): ligue Enviar > Avaliacoes >
  Criar, Atualizar e Excluir. Aprovada vira metaobject `avaliacao_produto` gravado por
  `metaobjectUpsert` com handle `avaliacao-<uuid>` (envio repetido nao duplica);
  fotos vao para Files (`fileCreate`, a Shopify baixa da URL publica do hub, a
  mesma dos webhooks). Rejeitada ou excluida que estava publicada sai da loja com
  as fotos. Na primeira vez o hub cria as definicoes. Escopos do app:
  `write_metaobject_definitions`, `write_metaobjects`, `write_files`, `write_products`.
- **O que o tema le** (contrato com o tema):

| Onde | Tipo | Conteudo |
| --- | --- | --- |
| `product.metafields.custom.reviews` | `list.metaobject_reference` | ate 50 aprovadas, as mais novas primeiro |
| `product.metafields.custom.rating_value` | `number_decimal` | media com 1 casa (`"4.3"`) |
| `product.metafields.custom.review_count` | `number_integer` | total de aprovadas |
| metaobject `avaliacao_produto` | campos | `product`, `author` ("Ana L."), `rating`, `body`, `photos` (`list.file_reference`), `verified`, `date` |

  Sem nenhuma aprovada os tres metafields sao apagados (o tema esconde o bloco).
- **Producao:** `AVALIACOES_ORIGENS` no `.env` com os dominios da loja (CORS so
  desta rota) e `client_max_body_size 16m` no nginx (3 fotos de 5 MB).

### 7.4 WooCommerce (`apps/woocommerce`)

Mesmo formato do Shopify: tela em Integracoes > WooCommerce, matriz Receber/Enviar,
Sincronizar loja, Cadastrar webhooks, Tarefas e Retomar. Nao tem relacao com
`apps/woo_api` (a API que o hub expoe ao ERP): aqui o hub e cliente de uma loja Woo.

- **Conexao:** endereco da loja (`https://sualoja.com.br`), chave `ck_` e segredo `cs_`
  de WooCommerce > Configuracoes > Avancado > API REST (leitura e escrita). O cliente
  (`cliente.py`) usa a REST v3 com Basic Auth; no primeiro 401 passa a chave na query
  string (hospedagem que descarta o cabecalho Authorization). Paginacao por
  `X-WP-TotalPages`, contagem da barra por `X-WP-Total`.
- **Sincronizar loja** (`sincronizar.py`): categorias (todas a mao, a pai entra antes
  da filha), produtos (variavel busca `products/<id>/variations`), clientes
  (`role=all`), cupons, pedidos e "estoque" (so a quantidade das variantes ja
  vinculadas). A loja manda no texto do produto e do cliente; webhook so atualiza
  preco, estoque e logistica. Item com erro vira falha e os outros seguem.
- **Vinculos** (`vinculos.py`): `produtos`, `variantes` (pai no
  `external_parent_id`), `categorias`, `clientes`, `cupons`, `pedidos`,
  `itens_pedido`, `midias`. Sem vinculo, slug (categoria), SKU (produto/variante),
  e-mail (cliente) e nome (cupom) reaproveitam o registro do hub.
- **Pedido** (`importar_pedidos.py`): status do Woo = status do hub; valores de cada
  linha (subtotal/total/impostos) como vieram, frete/taxas/cupons em
  `linhas_frete/linhas_taxa/linhas_cupom`, totais por `recalcular_totais`. Item cujo
  produto o hub nao tem: o produto e buscado na loja e importado inteiro. Item que
  sumiu do pedido na loja sai do pedido do hub.
- **Webhooks:** "Cadastrar webhooks" cria um por topico ligado (`product.*`,
  `customer.*`, `order.*`, `coupon.*`; Woo nao tem webhook de categoria nem de
  estoque) em `/integracoes/woocommerce/webhook/<uuid>/<recurso>/`, com o segredo `cs_`
  assinando. O receptor confere `X-WC-Webhook-Signature` (HMAC-SHA256 base64),
  responde 200 ao ping do cadastro (`webhook_id=...`) e 202 depois de enfileirar.
  `delete` desativa o registro no hub.
- **Frete:** zonas de entrega a partir das tabelas por faixa de CEP (secao 7.7).
- **Envio** (`envio/`): produtos (variacoes em lote por `variations/batch`; imagens
  ja na loja vao pelo id, novas pela URL publica do hub), estoque (produto simples no
  produto, variacao na rota dela), categorias, clientes, cupons e pedidos (so status
  e endereco de entrega; pedido nasce na loja). Tags nao vao: a API do Woo so aceita
  tag por id.
- **Execucao comum:** `apps/integracoes/execucao.py` roda as tarefas do Shopify e do
  Woo (progresso, falhas, Concluida com falhas); cada app passa o proprio contexto.

### 7.5 Suri Shop (`apps/suri`)

Loja do Suri (by Totvs), que vende pelo WhatsApp. Referencia: colecao Postman
"Suri" (pasta Shop), em https://sejasuri.gitbook.io/manual-de-integracao/api.
Mesma tela, matriz, Sincronizar, Tarefas e Retomar das outras lojas.

- **Conexao:** endpoint do chatbot (`https://cbxxxx.azurewebsites.net`; o `/api` e
  do hub) e token, ambos do Portal do Suri > Configuracoes. Bearer token. Resposta em
  envelope `{"success", "data", "error"}`. Numero do JSON e lido como `Decimal` e
  escrito de volta com o texto exato (`cliente._json`): preco nao passa por float.
- **Receber** (`sincronizar.py`): categorias (a arvore `children`), produtos (lista
  paginada por `token`), estoque (so das variantes ja vinculadas) e pedidos (os dos
  ultimos 30 dias, padrao da API). Produto com `attributes` e variavel; cada
  `dimensions[]` (um SKU) vira variante. Estoque do hub = soma das lojas do Suri.
- **Pedido** (`importar_pedidos.py`): status 0 (carrinho) nao entra; 1 pendente,
  2 processando, 3 cancelado, 4 falhou; logistica 4 (entregue) com pago = concluido.
  Frete em `linhas_frete`, `feeAmount` e o desconto do pedido inteiro
  (`orderDiscountAmount`, taxa negativa) em `linhas_taxa`. Total diferente do
  `totalAmount` do Suri vira aviso na tarefa. Comprador sem e-mail (WhatsApp) fica sem
  Cliente, com nome/telefone/endereco no pedido. Quantidade fracionada (quilo) vira
  aviso: o item do hub e inteiro.
- **Webhook:** "Cadastrar webhooks" define o endereco unico da loja (`POST shop/hook`)
  como `/integracoes/suri/webhook/<uuid>/`. O Suri nao assina e a doc nao traz o
  corpo: o receptor so tira o id do pedido (`id`, `orderId`, `order.id`...) e rele o
  pedido pela API com o token. Um POST forjado so faria reler um pedido verdadeiro.
- **Enviar** (`envio/`): categorias (a arvore da raiz, POST ou PUT), produtos (objeto
  inteiro, PUT do Suri e substituicao total; id `sh-<pk>` para o que nasceu no hub;
  categoria vai antes se faltar, porque o Suri exige), estoque (`PUT
  shop/products/<id>/stocks`, todo o estoque na primeira loja de `shop/stores`) e
  pedidos (pago, cancelado e logistica "entregue"; o estado do Suri fica no metadata
  do vinculo para nao repetir a chamada). Clientes nao vao: a API do Suri exige o
  canal de WhatsApp do contato.
- **Frete:** resposta de orcamento do pedido em montagem (secao 7.7).
- **Nao verificado contra o Suri real** (sem credencial no desenvolvimento): o corpo
  do webhook de pedidos, a lista de metodos de pagamento alem de cartao (0) e Pix (3)
  e se `PUT shop/products` sem `images` mantem as fotos. A doc so diz que
  `images: null` apaga; por isso a chave nem vai quando o hub nao tem foto publica.

### 7.6 Novo marketplace

Cada marketplace e um app: `apps/<marketplace>/` (ex.: `apps/mercado_livre/`).

```text
apps/mercado_livre/
  cliente.py     chamadas HTTP a API do marketplace (so isso)
  sincronizar.py regras de ida e volta (produto, estoque, preco, pedido)
  tasks.py       @shared_task que o Celery roda (descoberto sozinho)
  webhooks.py    normalizacao dos eventos recebidos
  envio/         um EnviadorRecurso por recurso + o Marketplace registrado
  tests/
```

Para **enviar** ao marketplace basta herdar e registrar; o Distribuidor e a tarefa
nao mudam:

```python
from apps.integracoes.envio.base import EnviadorRecurso, EnvioNaoSuportado, Marketplace
from apps.integracoes.envio.registro import registrar


class ProdutoML(EnviadorRecurso):
    recurso = "produtos"
    modelo = Produto

    def criar(self, obj):            # devolve o id externo; a base grava o vinculo
        ...
    def atualizar(self, obj, external_id):
        ...
    # excluir nao implementado: a base levanta EnvioNaoSuportado (vira "ignorado")


@registrar
class MercadoLivreMarketplace(Marketplace):
    plataforma = "mercado_livre"      # igual a ConfiguracaoIntegracao.Plataforma
    recursos = (ProdutoML,)
```

O `ready()` do app importa o modulo com o `@registrar`, e a plataforma entra em
`ConfiguracaoIntegracao.Plataforma` (migration). O codigo de origem que o app usa em
`with origem(...)` tem que ser o mesmo `plataforma`: e ele que impede o eco.

- Credenciais, matriz de permissoes e execucoes ficam em `apps/integracoes`; o
  app do marketplace implementa somente as diferencas da API externa.
- Os dados canonicos ficam em `apps/loja`. O app do marketplace le e grava la;
  ele nao cria um catalogo paralelo.
- Chamada externa sempre em tarefa do Celery, nunca dentro da requisicao do admin.
  Em dev ela roda na hora; em prod vai para o worker.
- Tempo real (se precisar): rotas em `config/routing.py`.

Onde ligar o app novo (o WooCommerce e o exemplo completo):

| O que | Onde |
| --- | --- |
| plataforma e origem | `ConfiguracaoIntegracao.Plataforma` + `Origin` (migrations) |
| app e URLs | `INSTALLED_APPS`, `config/urls.py` (`integracoes/<app>/`) |
| tela | `TELAS` em `apps/integracoes/admin.py` + rota `<app>_view` + form |
| menu com logo | `STARHUB_MENU_PAGINAS` (`"marca:<app>"`) + `static/starhub/img/marcas/<app>.svg` (ou `.png` em `IMAGENS`, `apps/core/admin_utils.py`, como o Suri) |
| Sincronizar loja | `IMPORTADORES` em `apps/integracoes/sincronizacao.py` |
| Retomar | `POR_PLATAFORMA` em `apps/integracoes/retomar.py` |
| tarefas | `tasks.py` com `apps.integracoes.execucao.executar(..., canal="<app>")` |

**Importar planilha em qualquer tela.** `ImportarPlanilhaMixin`
(`apps/integracoes/admin_importar.py`) poe o botao na lista, a pagina com as colunas, o
modelo .csv para baixar e cria a tarefa; `apps/integracoes/importar_planilha.executar`
roda a importacao (barra, falhas por linha, Retomar). Quem usa so declara as colunas e a
regra de uma linha (`importar_linha(dados) -> (obj, criado)` ou `LinhaInvalida`). Hoje:
avaliacoes e faixas de frete. A leitura (.xlsx/.csv) fica em `apps/core/planilha.py`.

### 7.7 Logistica: cotacao de frete (`apps/logistica`)

Cadastro e calculo do frete, levado ao checkout das lojas pela marca "oferecer no
checkout das lojas" de cada tabela (Shopify, WooCommerce e Suri, abaixo). Menu
**Logistica > Tabelas de frete**; a tela muda pela forma de cobranca (`condicoes`).

- **Por distancia (km):** CEP de origem, preco por km, taxa fixa, valor minimo e
  distancia maxima opcional. Valor = taxa + km x preco/km (cada parte arredondada ao
  centavo), nunca abaixo do minimo. Ex.: 12,3 km x R$ 2,35 + R$ 10 = R$ 38,91.
- **Por faixa de CEP:** lista de faixas (CEP inicial, final, valor, prazo). Faixas que se
  cruzam sao recusadas no cadastro; se mesmo assim mais de uma contiver o CEP, vale a
  mais estreita (excecao de bairro vence a faixa da cidade).
- **APIs gratuitas** (`apps/logistica/geo.py`): CEP -> coordenada pela AwesomeAPI
  (reserva: BrasilAPI v2; depois a cidade, pelo Nominatim), guardada em `CoordenadaCep` (cada CEP e consultado uma vez);
  distancia de carro pelo OSRM publico. Sem OSRM, linha reta x 1,3 e a cotacao avisa que e
  estimativa. O OSRM publico e de demonstracao: com volume, use servidor proprio (`ROTA`).
- **Importar planilha** (botao na lista de tabelas): faixas em massa com `tabela`,
  `cep_inicial`, `cep_final`, `valor` e `prazo_dias`. Tabela que nao existe nasce "Por
  faixa de CEP"; mesma faixa atualiza; faixa que cruza outra e recusada na linha. A opcao
  "substituir" apaga antes as faixas das tabelas da planilha (`apps/logistica/importacao.py`).
- **Frete no checkout da Shopify (CarrierService):** marque "oferecer no checkout" nas
  tabelas e clique **Cadastrar frete no checkout** em Integracoes > Shopify (tarefa;
  escopo `write_shipping`; loja com calculadora de terceiros liberada). A Shopify chama
  `POST /integracoes/shopify/frete/<uuid>/` (HMAC do segredo do app) a cada CEP do
  checkout e espera 3 s: cada tabela que atende vira uma opcao (`service_code` `HUB_<id>`,
  valor em centavos, prazo em dias uteis). No checkout cada API externa tem 0,8 s e o
  total 2,2 s; coordenadas e rotas ficam em `CoordenadaCep`/`DistanciaCep` (2a cotacao do
  mesmo CEP ~0,02 s). CEP que as bases nao conhecem e localizado pela cidade que o
  checkout manda (Nominatim). O frete escolhido volta no `orders/create` em
  `linhas_frete[].method_id` (`HUB_<id>`). Codigo: `apps/shopify/frete*.py`.
  Card **Frete no checkout** em Integracoes > Shopify: checklist com o que falta
  (escopos, plano, cadastro, zona de envio, CEP dos locais, origem das tabelas, peso,
  tabelas marcadas, embalagem). **Verificar configuracao** roda numa tarefa so de leitura
  na loja (`frete_diagnostico.py`); a tela le o ultimo resultado (`frete_checklist.py`).
- **Frete no WooCommerce (zonas de entrega):** card **Frete do hub** em Integracoes >
  WooCommerce, botoes Ligar/Desligar (tarefa "Cadastrar frete no checkout"). O Woo nao
  cota fora; o hub cria zonas `StarHub <cep>-<cep>` com um metodo "taxa fixa" por
  tabela (`apps/woocommerce/frete*.py`). O Woo usa uma zona por CEP, entao o CEP e
  cortado nos limites de todas as faixas e cada pedaco e cotado pelo `cotar` (faixas
  sobrepostas de tabelas diferentes aparecem juntas; dentro da tabela vale a mais
  estreita, como no hub). So faixa de CEP: tabela por distancia fica de fora, com aviso.
  Com o frete ligado, salvar ou apagar tabela/faixa reenvia as zonas (uma tarefa por
  commit); a importacao de planilha reenvia uma vez no fim (`apps/logistica/sinais.py`).
  Zonas criadas a mao na loja nao sao tocadas.
- **Frete no Suri (orcamento):** card **Frete do hub** em Integracoes > Suri Shop. O Suri
  nao chama o hub no checkout; com o frete ligado, o pedido em montagem (status 0) que
  chega pelo webhook com CEP e sem entrega escolhida recebe a cotacao mais barata das
  tabelas (CEP ou distancia) por `POST shop/orders/budget` (`apps/suri/frete.py`).
  Mesmo CEP e mesmos itens nao reenviam. Nao verificado no Suri real: como ele avisa
  que o pedido espera orcamento e o `id` do corpo.
- **Usar no codigo:** `apps.logistica.cotacao.cotar(tabela, "20040-020")` devolve
  `Cotacao(valor, prazo_dias, distancia_km, detalhe)` ou levanta `FreteIndisponivel` com
  o motivo. Botao **Simular cotacao** na tabela para conferir um CEP.

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
