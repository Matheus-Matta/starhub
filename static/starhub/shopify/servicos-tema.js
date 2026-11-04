// Bloco de servicos da pagina de produto Shopify. Os campos e grupos vem do hub.
(() => {
  "use strict";

  const raiz = (window.Shopify && window.Shopify.routes && window.Shopify.routes.root) || "/";

  function campoData(rotulo) {
    const linha = document.createElement("label");
    linha.className = "starhub-agendamento";
    const texto = document.createElement("span");
    texto.textContent = rotulo;
    const campo = document.createElement("input");
    campo.type = "date";
    campo.min = new Date().toISOString().slice(0, 10);
    campo.dataset.starhubAgendamento = "";
    linha.append(texto, campo);
    return linha;
  }

  function textoOpcao(servico) {
    const caixa = document.createElement("span");
    const titulo = document.createElement("strong");
    titulo.textContent = `${servico.rotulo || servico.nome} (+ ${servico.preco_texto})`;
    caixa.append(titulo);
    if (servico.descricao) {
      const descricao = document.createElement("small");
      descricao.textContent = servico.descricao;
      caixa.append(descricao);
    }
    return caixa;
  }

  function opcao(servico, agrupado) {
    const linha = document.createElement("label");
    linha.className = `starhub-servico${servico.tipo_campo === "cards" ? " starhub-servico--card" : ""}`;
    const campo = document.createElement("input");
    campo.type = agrupado && ["radio", "cards"].includes(servico.tipo_campo)
      ? "radio" : "checkbox";
    campo.name = agrupado ? `starhub-${servico.grupo}` : `starhub-${servico.id}`;
    campo.value = servico.variante;
    campo.checked = Boolean(servico.selecionado);
    campo.dataset.starhubServico = servico.nome;
    linha.append(campo, textoOpcao(servico));
    if (!agrupado && servico.obrigatorio) linha.dataset.starhubObrigatorio = "";
    return linha;
  }

  function lista(servicos) {
    const campo = document.createElement("select");
    campo.dataset.starhubServico = "";
    const vazio = document.createElement("option");
    vazio.value = "";
    vazio.textContent = "Selecione";
    campo.append(vazio);
    servicos.forEach((servico) => {
      const item = document.createElement("option");
      item.value = servico.variante;
      item.textContent = `${servico.rotulo || servico.nome} (+ ${servico.preco_texto})`;
      item.selected = Boolean(servico.selecionado);
      campo.append(item);
    });
    return campo;
  }

  function grupo(servicos) {
    const primeiro = servicos[0];
    const caixa = document.createElement("fieldset");
    caixa.className = `starhub-servico-grupo starhub-servico-grupo--${primeiro.tipo_campo}`;
    if (primeiro.obrigatorio) caixa.dataset.starhubObrigatorio = "";
    const titulo = document.createElement("legend");
    titulo.textContent = primeiro.titulo_grupo || "Escolha uma opcao";
    caixa.append(titulo);
    if (primeiro.tipo_campo === "select") caixa.append(lista(servicos));
    else servicos.forEach((servico) => caixa.append(opcao(servico, true)));
    return caixa;
  }

  function montar(bloco, servicos) {
    if (!servicos.length && !bloco.dataset.agendamento) {
      bloco.hidden = true;
      return;
    }
    const caixa = document.createElement("fieldset");
    caixa.className = "starhub-servicos";
    const titulo = document.createElement("legend");
    titulo.textContent = bloco.dataset.titulo || "Servicos";
    caixa.append(titulo);
    const grupos = new Map();
    servicos.forEach((servico) => {
      const chave = servico.grupo || `servico-${servico.id}`;
      if (!grupos.has(chave)) grupos.set(chave, []);
      grupos.get(chave).push(servico);
    });
    grupos.forEach((itens) => caixa.append(
      itens[0].grupo ? grupo(itens) : opcao(itens[0], false)));
    if (bloco.dataset.agendamento) caixa.append(campoData(bloco.dataset.agendamento));
    const aviso = document.createElement("p");
    aviso.className = "starhub-servicos-erro";
    aviso.hidden = true;
    caixa.append(aviso);
    bloco.replaceChildren(caixa);
  }

  function formularioDe(bloco) {
    return bloco.closest("form") || document.querySelector(
      bloco.dataset.formulario || 'form[action*="/cart/add"]');
  }

  function marcados(raizSelecao) {
    return [...raizSelecao.querySelectorAll("[data-starhub-servico]")].filter(
      (campo) => campo.tagName === "SELECT" ? campo.value : campo.checked);
  }

  function validar(bloco) {
    const vazio = [...bloco.querySelectorAll("[data-starhub-obrigatorio]")].find(
      (item) => !marcados(item).length);
    const aviso = bloco.querySelector(".starhub-servicos-erro");
    if (!vazio) {
      aviso.hidden = true;
      return true;
    }
    const titulo = vazio.querySelector("legend");
    aviso.textContent = `Escolha uma opcao${titulo ? ` em ${titulo.textContent}` : ""}.`;
    aviso.hidden = false;
    vazio.querySelector("input, select").focus();
    return false;
  }

  function propriedades(form) {
    const saida = {};
    new FormData(form).forEach((valor, nome) => {
      const achado = /^properties\[(.+)\]$/.exec(nome);
      if (achado && typeof valor === "string") saida[achado[1]] = valor;
    });
    return saida;
  }

  async function postar(caminho, corpo) {
    return fetch(`${raiz}${caminho}`, { method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(corpo) });
  }

  async function adicionar(form, bloco, escolhas, data) {
    const variante = form.querySelector('[name="id"]');
    const quantidade = Number((form.querySelector('[name="quantity"]') || {}).value) || 1;
    const vinculo = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
    const itens = [{ id: Number(variante.value), quantity: quantidade,
      properties: { ...propriedades(form), _starhub_vinculo: vinculo } }];
    escolhas.forEach((campo) => itens.push({ id: Number(campo.value), quantity: quantidade,
      properties: { _starhub_vinculo: vinculo } }));
    let resposta = await postar("cart/add.js", { items: itens });
    if (resposta.ok && data) resposta = await postar(
      "cart/update.js", { attributes: { agendamento: data } });
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
    document.addEventListener("submit", (evento) => {
      if (evento.target !== form) return;
      if (!validar(bloco)) {
        evento.preventDefault();
        evento.stopImmediatePropagation();
        return;
      }
      const escolhas = marcados(bloco);
      const data = (bloco.querySelector("input[data-starhub-agendamento]") || {}).value || "";
      if (!escolhas.length && !data) return;
      evento.preventDefault();
      evento.stopImmediatePropagation();
      adicionar(form, bloco, escolhas, data);
    }, true);
  }

  document.querySelectorAll("[data-starhub-servicos]").forEach((bloco) => {
    const url = new URL(bloco.dataset.url);
    url.searchParams.set("produto", bloco.dataset.produto);
    fetch(url, { headers: { Accept: "application/json" } })
      .then((resposta) => (resposta.ok ? resposta.json() : { servicos: [] }))
      .then((dados) => { montar(bloco, dados.servicos || []); if (!bloco.hidden) ligar(bloco); })
      .catch(() => { bloco.hidden = true; });
  });
})();
