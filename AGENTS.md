# Orientacoes para agentes de IA

Use linguagem simples e explique sempre com exemplos as duvidas e perguntas, de
forma facil de entender.

Este arquivo vale para todo o projeto **StarHub**: um hub de integracao com
marketplaces feito em Django, com a interface no admin do Django (tema proprio)
e uma API identica a do WooCommerce para o ERP.

**Leia `projects.md` antes de mexer no projeto.** Ele tem a arquitetura, o
dev x prod, o tema, a API Woo, o passo a passo de um marketplace novo e o que
ainda nao existe.

## Mapa rapido

| Assunto | Onde |
| --- | --- |
| Configuracao dev/prod, Celery, ASGI | `config/` |
| Tema do admin (site, componentes, menu) | `apps/core/`, `templates/`, `static/starhub/` |
| Produtos, categorias, clientes, pedidos | `apps/loja/` |
| API WooCommerce, JWT e chaves ck_/cs_ | `apps/woo_api/` |
| Cada marketplace | um app proprio em `apps/<marketplace>/` |

- Dev roda tudo num terminal (`python manage.py runserver`: Daphne + Celery na
  memoria). Prod roda em Docker (`docker-compose.yml`, imagem do GitHub): uvicorn,
  worker e beat em containers separados, Redis no compose e PostgreSQL de fora.
- `example_templetes_react_to_convert_html/` e o template comprado, so para
  consulta visual. Nao versione, nao copie arquivos dele para o projeto.

## Regras do tema

- A interface e o admin do Django. Tela nova e `ModelAdmin` ou pagina custom
  do admin (exemplo em `apps/woo_api/admin.py`, `guia_view`).
- Tudo e componente reutilizavel em `templates/components/`. Conteudo livre usa
  `{% componente "card" %}...{% endcomponente %}` com `{% slot %}`; formulario usa
  `components/forms.html`. Nada de `style=""` solto: crie a classe no CSS.
- Sobrescreva template do admin **mantendo os blocks do Django**. Block dentro de
  `{% include %}` nao pode ser sobrescrito pelos filhos: block que o admin
  preenche (ex.: `breadcrumbs`) fica no proprio `base.html`.
- Cor so por token (`static/starhub/css/tokens.css`). Confira tema claro e escuro.
- ModelAdmin novo herda de `TemaModelAdmin` (inline: `TemaTabularInline`), de
  `apps/core/admin_base.py`: e ela que liga calendario, switch e periodo. Select e
  multi-select viram widget do tema sozinhos (JS).
- Campo JSON nunca aparece cru. `metadados` e dicionario (`default=dict`) ganham
  widget sozinhos; lista com formato proprio: declare em `campos_json` do ModelAdmin
  (tags, imagens, chave/valor, lista, objeto). Ver `projects.md`, secao 5.3.
- Espacamento vertical so por `gap` do container (`--gap-pagina`). Card, modulo e
  aviso nao tem margem: nao ponha `margin-top/bottom` para separar blocos.

## Regras da API Woo

- A API copia o WooCommerce: mesmos nomes de campo, codigos de erro, paginacao
  (`X-WP-Total`) e formatos (dinheiro como texto `"19.90"`, datas sem fuso + `_gmt`).
  Antes de mudar um contrato, confira como o Woo real responde.
- Conflito de SKU, e-mail ou categoria devolve **400** com o codigo do Woo (e nao
  409): o ERP foi feito para o Woo. Essa excecao vale **so** para `apps/woo_api`.
- Campo, filtro ou rota nova entra com teste em `apps/woo_api/tests/`.

## Padroes de codigo

### O criterio que decide tudo

> **Entra o que aponta defeito. Fica de fora o que so discorda de uma escolha.**

Vale para regra de lint, para comentario de revisao e para o que se exige num
PR. Regra que grita em cima de decisao deliberada e desligada na primeira
urgencia, e ai para de pegar ate o que importava.

### Maximo 200 linhas por arquivo

Passou disso, quebre em modulos com **uma responsabilidade cada**. O corte e por
assunto, nao por camada.

```bash
python scripts/check_tamanho_de_arquivo.py            # confere
python scripts/check_tamanho_de_arquivo.py --atualizar  # grava a linha de base
```

Vale para `.py`, `.html`, `.css`, `.js` e `.svg` (migrations ficam de fora).
**Arquivo novo acima do limite nao tem excecao**: quebre. Arquivo que ja estava na
linha de base e cresceu tambem reprova: quebre, ou rode `--atualizar` e deixe o
crescimento visivel no diff. O que nao pode e crescer em silencio.

### As cinco que custam dinheiro

1. **Dinheiro nunca e `float`.** `Decimal` (use `apps/loja/dinheiro.py`).
   Arredonde onde o valor nasce, nao na gravacao.
2. **Total que e soma de varios soma valores ja arredondados.** Dois itens de
   R$ 10,05 com 10% de desconto dao R$ 18,10 (9,05 + 9,05), nao R$ 18,09.
3. **Escrita concorrente:** `transaction.atomic` + `select_for_update` (varias
   linhas: lock em ordem de id) e **releia o estado depois do lock**.
4. **A defesa contra duas gravacoes ao mesmo tempo e do BANCO** (indice unico,
   condicional se preciso), nunca um `if`: o `if` roda antes do lock do outro.
5. **409 e conflito de estado; 400 e entrada errada** (excecao: `apps/woo_api`,
   ver acima). Cliente que reenvia 400 para sempre entra em laco infinito com
   um conflito devolvido como 400.

### Integracao com marketplace

- Chamada a API externa roda em tarefa do Celery (`tasks.py` do app), nunca
  dentro da requisicao do admin.
- Os dados canonicos ficam em `apps/loja`; o app do marketplace nao cria
  catalogo paralelo.
- `QuerySet.update()` nao dispara signal nem `save()`: nao use onde a regra
  depende do `save()` (ex.: `Produto.save` calcula a situacao do estoque).

### Comentario, nome e teste

- O comentario explica **por que**, nunca **o que**. Mudou a linha, revise o
  comentario dela no mesmo commit.
- O dominio e escrito em **portugues** (`pedido`, `produto`, `estoque`). Nome de
  campo do WooCommerce fica em ingles so na borda da API (`apps/woo_api/recursos/`).
- Nome de teste e uma frase, e o docstring conta o defeito que ele impede.
- **Escreva o teste antes da correcao e veja-o falhar.** Ao corrigir um defeito,
  reverta a correcao por um instante e confirme que o teste pega. Teste que nunca
  falhou nao provou nada.
- `pytest.raises(Exception)` e proibido: passa ate com `AttributeError` de
  digitacao. Nomeie a excecao.

### Onde cada regra vive

| O que | Configuracao | Comando |
| --- | --- | --- |
| Lint Python | `pyproject.toml` (`[tool.ruff]`) | `ruff check .` |
| Testes | `pyproject.toml` (`[tool.pytest.ini_options]`) | `python -m pytest` |
| Tamanho de arquivo | `scripts/check_tamanho_de_arquivo.py` | `python scripts/check_tamanho_de_arquivo.py` |

Ao ligar ou desligar uma regra, **escreva o motivo ao lado dela** no arquivo de
configuracao.

## Validacao minima

Antes de concluir qualquer mudanca de codigo:

```powershell
python -m pytest
ruff check .
python scripts/check_tamanho_de_arquivo.py
python manage.py check
python manage.py makemigrations --check --dry-run
```

Mudou template ou CSS: abra a tela no navegador nos temas claro e escuro.
Mudou `config/settings/prod.py`: suba com `DJANGO_SETTINGS_MODULE=config.settings.prod`
e as variaveis do `.env.example` para ver que carrega.

Antes de concluir:

- execute `git diff --check`;
- nunca versione `.env`, `db.sqlite3`, `staticfiles/`, `media/` nem o template de exemplo;
- nunca crie, mova ou apague tag de release sem autorizacao explicita;
- informe claramente se houve so mudanca local, commit/push de branch ou publicacao.
