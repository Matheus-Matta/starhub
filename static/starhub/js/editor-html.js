(() => {
  "use strict";

  const script = document.currentScript;
  const cssFrame = new URL("../css/editor-html-frame.css", script.src).href;

  const botoes = [
    ["undo", "Desfazer", "↶"],
    ["redo", "Refazer", "↷"],
    ["bold", "Negrito", "B", "negrito"],
    ["italic", "Italico", "I", "italico"],
    ["insertUnorderedList", "Lista com marcadores", "• Lista"],
    ["insertOrderedList", "Lista numerada", "1. Lista"],
    ["createLink", "Adicionar link", "Link"],
    ["unlink", "Remover link", "Sem link"],
    ["removeFormat", "Limpar formatacao", "Limpar"],
  ];

  function botao(comando, titulo, texto, modificador) {
    const elemento = document.createElement("button");
    elemento.type = "button";
    elemento.className = `editor-html__botao${modificador ? ` editor-html__botao--${modificador}` : ""}`;
    elemento.dataset.comando = comando;
    elemento.title = titulo;
    elemento.setAttribute("aria-label", titulo);
    elemento.textContent = texto;
    return elemento;
  }

  function grupo(...elementos) {
    const elemento = document.createElement("div");
    elemento.className = "editor-html__grupo";
    elemento.append(...elementos);
    return elemento;
  }

  function seletorFormato() {
    const seletor = document.createElement("select");
    seletor.className = "editor-html__formato";
    seletor.title = "Formato do texto";
    seletor.setAttribute("aria-label", "Formato do texto");
    [["p", "Paragrafo"], ["h2", "Titulo"], ["h3", "Subtitulo"],
      ["blockquote", "Citacao"]].forEach(([valor, rotulo]) => {
      const opcao = document.createElement("option");
      opcao.value = valor;
      opcao.textContent = rotulo;
      seletor.appendChild(opcao);
    });
    return seletor;
  }

  function documentoDoEditor(iframe) {
    return iframe.contentDocument;
  }

  function ligarTelaCheia(caixa, fundo, controle, iframe) {
    const atualizarBotao = (aberto) => {
      const titulo = aberto ? "Fechar tela cheia" : "Abrir editor em tela cheia";
      controle.title = titulo;
      controle.setAttribute("aria-label", titulo);
      controle.setAttribute("aria-pressed", String(aberto));
      controle.textContent = aberto ? "Fechar" : "Tela cheia";
    };
    const fechar = () => {
      caixa.classList.remove("editor-html--modal");
      caixa.removeAttribute("role");
      caixa.removeAttribute("aria-modal");
      fundo.hidden = true;
      document.documentElement.classList.remove("editor-html-modal-aberto");
      atualizarBotao(false);
      controle.focus();
    };
    controle.addEventListener("click", () => {
      if (caixa.classList.contains("editor-html--modal")) {
        fechar();
        return;
      }
      caixa.classList.add("editor-html--modal");
      caixa.setAttribute("role", "dialog");
      caixa.setAttribute("aria-modal", "true");
      fundo.hidden = false;
      document.documentElement.classList.add("editor-html-modal-aberto");
      atualizarBotao(true);
      iframe.contentDocument?.body?.focus();
    });
    fundo.addEventListener("click", fechar);
    document.addEventListener("keydown", (evento) => {
      if (evento.key === "Escape" && caixa.classList.contains("editor-html--modal")) {
        evento.preventDefault();
        fechar();
      }
    });
    atualizarBotao(false);
  }

  function montar(textarea) {
    if (textarea.closest(".editor-html")) {
      return;
    }
    const caixa = document.createElement("div");
    caixa.className = "editor-html";
    const barra = document.createElement("div");
    barra.className = "editor-html__barra";
    barra.setAttribute("role", "toolbar");
    barra.setAttribute("aria-label", "Formatacao do texto");
    const formato = seletorFormato();
    const controles = botoes.map((dados) => botao(...dados));
    const codigo = botao("codigo", "Editar codigo HTML", "</>");
    const telaCheia = botao("tela-cheia", "Abrir editor em tela cheia", "Tela cheia");
    telaCheia.removeAttribute("data-comando");
    barra.append(
      grupo(controles[0], controles[1]), grupo(formato), grupo(...controles.slice(2, 6)),
      grupo(...controles.slice(6)), grupo(codigo, telaCheia),
    );

    const fundo = document.createElement("div");
    fundo.className = "editor-html-modal__fundo";
    fundo.hidden = true;
    const iframe = document.createElement("iframe");
    iframe.className = "editor-html__area";
    iframe.title = `Editor visual: ${textarea.getAttribute("aria-label") || textarea.name}`;
    iframe.setAttribute("sandbox", "allow-same-origin");
    iframe.addEventListener("load", () => iniciar(caixa, textarea, iframe, formato, codigo),
      { once: true });
    iframe.srcdoc = `<!doctype html><html data-theme="${document.documentElement.dataset.theme}"><head>`
      + `<meta charset="utf-8"><link rel="stylesheet" href="${cssFrame}"></head>`
      + '<body contenteditable="true" role="textbox" aria-multiline="true"></body></html>';

    textarea.before(caixa);
    caixa.before(fundo);
    caixa.append(barra, iframe, textarea);
    ligarTelaCheia(caixa, fundo, telaCheia, iframe);
  }

  function iniciar(caixa, textarea, iframe, formato, codigo) {
    const doc = documentoDoEditor(iframe);
    const area = doc.body;
    area.innerHTML = textarea.value;
    textarea.hidden = true;

    const executar = (comando, valor = null) => {
      area.focus();
      doc.execCommand(comando, false, valor);
      textarea.value = area.innerHTML;
      area.focus();
    };
    caixa.querySelectorAll("[data-comando]").forEach((controle) => {
      if (controle === codigo) {
        return;
      }
      controle.addEventListener("mousedown", (evento) => evento.preventDefault());
      controle.addEventListener("click", () => {
        const comando = controle.dataset.comando;
        if (comando === "createLink") {
          const url = window.prompt("Informe o endereco do link (https://...):");
          if (url) {
            executar(comando, url);
          }
          return;
        }
        executar(comando);
      });
    });
    formato.addEventListener("change", () => executar("formatBlock", formato.value));
    area.addEventListener("input", () => { textarea.value = area.innerHTML; });

    codigo.addEventListener("click", () => {
      const mostrarCodigo = textarea.hidden;
      if (mostrarCodigo) {
        textarea.value = area.innerHTML;
      } else {
        area.innerHTML = textarea.value;
      }
      textarea.hidden = !mostrarCodigo;
      iframe.hidden = mostrarCodigo;
      codigo.classList.toggle("ativo", mostrarCodigo);
      codigo.setAttribute("aria-pressed", String(mostrarCodigo));
      (mostrarCodigo ? textarea : area).focus();
    });

    textarea.form?.addEventListener("submit", () => {
      if (textarea.hidden) {
        textarea.value = area.innerHTML;
      }
    });
    new MutationObserver(() => {
      doc.documentElement.dataset.theme = document.documentElement.dataset.theme;
    }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }

  const carregar = () => document.querySelectorAll("textarea[data-editor-html]").forEach(montar);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", carregar);
  } else {
    carregar();
  }
  document.addEventListener("formset:added", carregar);
})();
