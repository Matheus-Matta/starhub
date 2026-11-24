// Dialog "Agrupar produtos simples" do produto (templates/admin/loja/produto/_dialog_agrupar.html,
// apps/loja/admin/produtos_agrupar.py). Etapa 1: busca no servidor (nome ou SKU) e marca;
// os marcados ficam no topo e nao somem ao buscar de novo. Etapa 2: o servidor sugere o
// nome do pai e o valor de cada um; o operador confere, informa a opcao e envia o form.
(() => {
  "use strict";
  const modal = document.getElementById("modal-agrupar");
  const raiz = modal && modal.querySelector("[data-agrupar]");
  if (!raiz) return;
  const ESPERA_MS = 300;
  const busca = raiz.querySelector("[data-agrupar-busca]");
  const escolhidos = raiz.querySelector("[data-agrupar-escolhidos]");
  const resultados = raiz.querySelector("[data-agrupar-resultados]");
  const estado = raiz.querySelector("[data-agrupar-estado]");
  const nome = modal.querySelector("[data-agrupar-nome]");
  const opcao = modal.querySelector("[data-agrupar-opcao]");
  const opcaoId = modal.querySelector("[data-agrupar-opcao-id]");
  const valores = modal.querySelector("[data-agrupar-valores]");
  const listaValores = modal.querySelector("#agrupar-valores-existentes");
  const opcoes = JSON.parse(modal.querySelector("#agrupar-opcoes-dados").textContent);
  const erro = modal.querySelector("[data-etapas-erro]");
  let espera = null;
  let pedido = 0;
  let nomeEditado = false;

  const marcados = () => [...escolhidos.querySelectorAll('input[name="produtos"]')];
  const normalizar = (texto) => texto.trim().toLocaleLowerCase("pt-BR");
  const tipoAtual = () => opcoes.find((tipo) => normalizar(tipo.nome) === normalizar(opcao.value));

  function sincronizarOpcao() {
    const tipo = tipoAtual();
    opcaoId.value = tipo?.id || "";
    listaValores.replaceChildren(...(tipo?.valores || []).map((valor) => {
      const item = document.createElement("option");
      item.value = valor.nome;
      return item;
    }));
    valores.querySelectorAll('[data-agrupar-valor]').forEach(sincronizarValor);
  }

  function sincronizarValor(entrada) {
    const tipo = tipoAtual();
    const valor = tipo?.valores.find(
      (item) => normalizar(item.nome) === normalizar(entrada.value));
    entrada.nextElementSibling.value = valor?.id || "";
  }

  function linha(produto, marcado) {
    const rotulo = document.createElement("label");
    rotulo.className = "agrupar-item";
    const caixa = document.createElement("input");
    caixa.type = "checkbox";
    caixa.name = "produtos";
    caixa.value = produto.id;
    caixa.checked = marcado;
    caixa.dataset.produto = JSON.stringify(produto);
    const texto = document.createElement("span");
    const titulo = document.createElement("strong");
    titulo.textContent = produto.nome;
    const detalhe = document.createElement("small");
    const preco = produto.preco ? `R$ ${produto.preco.replace(".", ",")}` : "sem preco";
    const estoque = produto.estoque ?? "-";
    detalhe.textContent = `${produto.sku || "sem SKU"} · ${preco} · estoque ${estoque}`;
    texto.append(titulo, detalhe);
    rotulo.append(caixa, texto);
    return rotulo;
  }

  async function buscar() {
    const numero = ++pedido;
    estado.textContent = "Buscando...";
    const url = `${raiz.dataset.urlBuscar}?q=${encodeURIComponent(busca.value.trim())}`;
    try {
      const resposta = await fetch(url, { headers: { Accept: "application/json" } });
      if (!resposta.ok) throw new Error(String(resposta.status));
      const dados = await resposta.json();
      if (numero !== pedido) return; // resposta de uma busca antiga chegou depois
      const ja = new Set(marcados().map((caixa) => caixa.value));
      const livres = dados.produtos.filter((p) => !ja.has(String(p.id)));
      resultados.replaceChildren(...livres.map((p) => linha(p, false)));
      estado.textContent = livres.length ? "" : "Nenhum outro produto simples com esse nome ou SKU.";
    } catch (falha) {
      if (numero === pedido) estado.textContent = "Nao foi possivel buscar. Tente de novo.";
    }
  }

  // Marcou: sobe para os escolhidos. Desmarcou: sai (a busca mostra de novo).
  raiz.addEventListener("change", (evento) => {
    const caixa = evento.target;
    if (!caixa.matches('input[name="produtos"]')) return;
    if (caixa.checked) escolhidos.append(caixa.closest(".agrupar-item"));
    else caixa.closest(".agrupar-item").remove();
  });
  busca.addEventListener("input", () => {
    clearTimeout(espera);
    espera = setTimeout(buscar, ESPERA_MS);
  });
  nome.addEventListener("input", () => { nomeEditado = true; });

  function campoValor(item) {
    const tr = document.createElement("tr");
    const celulas = [item.nome, item.sku || "-"].map((texto) => {
      const td = document.createElement("td");
      td.textContent = texto;
      return td;
    });
    const entrada = document.createElement("input");
    Object.assign(entrada, { type: "text", className: "vTextField", name: `valor_${item.id}`,
                             value: item.valor, maxLength: 100 });
    entrada.dataset.agruparValor = "";
    entrada.setAttribute("list", "agrupar-valores-existentes");
    entrada.setAttribute("placeholder", "Escolha ou digite um novo");
    entrada.setAttribute("aria-label", `Valor da opcao de ${item.nome}`);
    const id = document.createElement("input");
    Object.assign(id, { type: "hidden", name: `valor_id_${item.id}` });
    entrada.addEventListener("input", () => sincronizarValor(entrada));
    const td = document.createElement("td");
    td.append(entrada, id);
    tr.append(...celulas, td);
    sincronizarValor(entrada);
    return tr;
  }

  async function sugerir() {
    const ids = marcados().map((caixa) => caixa.value).join(",");
    const digitados = Object.fromEntries([...valores.querySelectorAll("input")]
      .map((entrada) => [entrada.name, entrada.value]));
    try {
      const resposta = await fetch(`${raiz.dataset.urlSugestao}?ids=${ids}`);
      const dados = await resposta.json();
      if (!nomeEditado) nome.value = dados.nome;
      // Volta e avanca de novo nao apaga o que a pessoa ja corrigiu.
      valores.replaceChildren(...dados.itens.map((item) => campoValor(
        { ...item, valor: digitados[`valor_${item.id}`] ?? item.valor })));
    } catch (falha) {
      erro.textContent = "Nao foi possivel montar a sugestao. Volte e avance de novo.";
      erro.hidden = false;
    }
  }

  modal.addEventListener("modal-etapas:etapa", (evento) => {
    if (evento.detail.etapa === 2) sugerir();
  });
  opcao.addEventListener("input", sincronizarOpcao);
  modal.querySelector("form").addEventListener("submit", (evento) => {
    const vazios = [...modal.querySelectorAll('[data-etapa="2"] input[type="text"]')]
      .filter((entrada) => !entrada.value.trim());
    if (!vazios.length) return;
    evento.preventDefault();
    erro.textContent = "Preencha o nome, a opcao e o valor de cada produto.";
    erro.hidden = false;
    vazios[0].focus();
  });
  // Abre ja buscando pelo comeco do nome deste produto: as irmas aparecem sem digitar.
  // No clique (e nao ao carregar a pagina): produto aberto so para editar nao busca nada.
  document.addEventListener("click", (evento) => {
    if (!evento.target.closest('[data-abrir-modal-etapas="modal-agrupar"]')) return;
    if (busca.dataset.iniciada) return;
    busca.dataset.iniciada = "1";
    busca.value = raiz.dataset.buscaInicial || "";
    buscar();
  });
})();
