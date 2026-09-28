// Base dos widgets de campo JSON (tags, metadados, listas, objetos, imagens).
// Cada tipo se registra com StarHub.json.registrar("tipo", montar). O valor
// que o form envia continua sendo o JSON do <textarea>: o widget le dele ao
// abrir e reescreve nele a cada mudanca. O servidor revalida tudo.
(() => {
  "use strict";

  const { aoCarregar } = window.StarHub;
  const tipos = {};

  function el(tag, classe, texto) {
    const elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined) elemento.textContent = texto;
    return elemento;
  }

  function botao(texto, classe, aoClicar, iconeNome) {
    const b = el("button", classe || "btn btn-outline btn-sm");
    b.type = "button";
    if (iconeNome) b.appendChild(window.StarHub.icone(iconeNome, "icon-sm"));
    if (texto) b.append(texto);
    b.addEventListener("click", aoClicar);
    return b;
  }

  function lerJSON(textarea, padrao) {
    try {
      const valor = JSON.parse(textarea.value || "null");
      return valor === null || valor === undefined ? padrao : valor;
    } catch (erro) {
      return padrao; // JSON quebrado: comeca vazio, o servidor acusa se enviar
    }
  }

  function montar(caixa) {
    const criar = tipos[caixa.dataset.jsonWidget];
    if (!criar || caixa.dataset.temaPronto || caixa.closest(".empty-form")) return;
    caixa.dataset.temaPronto = "1";
    const textarea = caixa.querySelector(".sh-json-valor");
    let config = {};
    try { config = JSON.parse(caixa.dataset.config || "{}"); } catch (erro) { config = {}; }
    textarea.classList.add("sh-nativo");
    textarea.tabIndex = -1;
    criar({
      caixa,
      textarea,
      config,
      ler: (padrao) => lerJSON(textarea, padrao),
      escrever(valor) {
        textarea.value = JSON.stringify(valor);
        textarea.dispatchEvent(new Event("change", { bubbles: true }));
      },
    });
  }

  function montarTodos(raiz, tipo) {
    const seletor = tipo ? `[data-json-widget="${tipo}"]` : "[data-json-widget]";
    raiz.querySelectorAll(seletor).forEach(montar);
  }

  window.StarHub.json = {
    el,
    botao,
    // Registrar monta na hora os campos daquele tipo que ja estao na pagina.
    registrar(tipo, criar) {
      tipos[tipo] = criar;
      montarTodos(document, tipo);
    },
  };
  aoCarregar((raiz) => montarTodos(raiz));
})();
