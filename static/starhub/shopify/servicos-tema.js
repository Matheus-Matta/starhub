// Bloco de servicos na pagina do produto do tema Shopify (Guia dos servicos no admin).
//
//   <div data-starhub-servicos data-url="https://hub/integracoes/shopify/servicos-publico/<uuid>/"
//        data-produto="{{ product.id }}"></div>
//
// Pergunta ao hub quais servicos valem para o produto (apps/shopify/servicos_publico.py)
// e mostra um checkbox por servico. Com algum marcado, o envio do formulario do produto
// vira um /cart/add.js com o produto e os servicos juntos, todos com a mesma
// propriedade _starhub_vinculo: e por ela que o hub liga o servico ao item no pedido.
// Nada marcado: o formulario segue o caminho normal do tema.
(() => {
  "use strict";

  const raiz = (window.Shopify && window.Shopify.routes && window.Shopify.routes.root) || "/";

  function montar(bloco, servicos) {
    if (!servicos.length) {
      bloco.hidden = true;
      return;
    }
    const grupo = document.createElement("fieldset");
    grupo.className = "starhub-servicos";
    const titulo = document.createElement("legend");
    titulo.textContent = bloco.dataset.titulo || "Servicos";
    grupo.append(titulo);
    servicos.forEach((servico) => {
      const linha = document.createElement("label");
      linha.className = "starhub-servico";
      const caixa = document.createElement("input");
      caixa.type = "checkbox";
      caixa.value = servico.variante;
      caixa.dataset.starhubServico = servico.nome;
      const texto = document.createElement("span");
      texto.textContent = `${servico.nome} (+ ${servico.preco_texto})`;
      linha.append(caixa, texto);
      grupo.append(linha);
    });
    const aviso = document.createElement("p");
    aviso.className = "starhub-servicos-erro";
    aviso.hidden = true;
    grupo.append(aviso);
    bloco.replaceChildren(grupo);
  }

  function formularioDe(bloco) {
    const seletor = bloco.dataset.formulario || 'form[action*="/cart/add"]';
    return bloco.closest("form") || document.querySelector(seletor);
  }

  function propriedades(form) {
    // Propriedades que o proprio tema pos no item (properties[Gravacao]) seguem junto.
    const saida = {};
    new FormData(form).forEach((valor, nome) => {
      const achado = /^properties\[(.+)\]$/.exec(nome);
      if (achado && typeof valor === "string") saida[achado[1]] = valor;
    });
    return saida;
  }

  async function adicionar(form, bloco, marcados) {
    const variante = form.querySelector('[name="id"]');
    const quantidade = Number((form.querySelector('[name="quantity"]') || {}).value) || 1;
    const vinculo = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
    const itens = [{ id: Number(variante.value), quantity: quantidade,
      properties: { ...propriedades(form), _starhub_vinculo: vinculo } }];
    marcados.forEach((caixa) => itens.push({ id: Number(caixa.value), quantity: quantidade,
      properties: { _starhub_vinculo: vinculo } }));
    const resposta = await fetch(`${raiz}cart/add.js`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ items: itens }),
    });
    if (!resposta.ok) {
      const erro = await resposta.json().catch(() => ({}));
      const aviso = bloco.querySelector(".starhub-servicos-erro");
      aviso.textContent = erro.description || "Nao foi possivel adicionar ao carrinho.";
      aviso.hidden = false;
      return;
    }
    window.location.href = `${raiz}cart`;
  }

  function ligar(bloco) {
    const form = formularioDe(bloco);
    if (!form) return;
    // Captura: roda antes do JS do tema (carrinho lateral), que so ve o envio sem servico.
    document.addEventListener("submit", (evento) => {
      if (evento.target !== form) return;
      const marcados = [...bloco.querySelectorAll("input[data-starhub-servico]:checked")];
      if (!marcados.length) return;
      evento.preventDefault();
      evento.stopImmediatePropagation();
      adicionar(form, bloco, marcados);
    }, true);
  }

  document.querySelectorAll("[data-starhub-servicos]").forEach((bloco) => {
    const url = new URL(bloco.dataset.url);
    url.searchParams.set("produto", bloco.dataset.produto);
    fetch(url, { headers: { Accept: "application/json" } })
      .then((resposta) => (resposta.ok ? resposta.json() : { servicos: [] }))
      .then((dados) => {
        montar(bloco, dados.servicos || []);
        if ((dados.servicos || []).length) ligar(bloco);
      })
      .catch(() => { bloco.hidden = true; });
  });
})();
