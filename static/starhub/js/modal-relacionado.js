// "+" (adicionar), lapis (alterar), olho (ver) e lixeira ao lado de um campo de
// relacao: em vez da janela nova do Django (window.open com _popup=1), abre um
// modal com a mesma pagina num iframe. Ao salvar, o Django seleciona o registro
// no campo (dismissAddRelatedObjectPopup) e o modal fecha.
//
// Como funciona sem reescrever o Django:
// - o Django dispara "django:show-related" antes de abrir a janela; cancelar o
//   evento e o jeito previsto de trocar a janela por outra coisa;
// - o iframe recebe o MESMO nome que a janela teria ("id_cliente__1"): e por ele
//   que o Django acha o campo a preencher;
// - a pagina de resposta (templates/admin/popup_response.html) chama o
//   window.parent quando nao ha window.opener (caso do iframe);
// - win.close() nao fecha iframe: as funcoes dismiss* sao embrulhadas para
//   fechar o modal depois de preencher o campo.
(() => {
  "use strict";

  // Pagina aberta DENTRO do modal: o "Cancelar" (data-fechar-modal) pede ao
  // pai para fechar; aberta como janela (sem modal), fecha a janela.
  document.addEventListener("click", (evento) => {
    if (!evento.target.closest("[data-fechar-modal]")) return;
    evento.preventDefault();
    const pai = window.parent !== window ? window.parent : null;
    if (pai && pai.StarHub && pai.StarHub.fecharModalDe) pai.StarHub.fecharModalDe(window);
    else if (window.opener) window.close();
  });

  const $ = window.django && window.django.jQuery;
  if (!$) return; // pagina sem campos de relacao (sem o jQuery do admin)

  // Mesmo indice que o RelatedObjectLookups.js do Django usa no nome da janela.
  function indiceDoPopup() {
    if (!document.getElementsByName("_popup").length) return 0;
    return parseInt(window.name.substring(window.name.lastIndexOf("__") + 2), 10) || 0;
  }

  function nomeDaJanela(link) {
    return `${link.id.replace(/^(change|add|delete|view)_/, "")}__${indiceDoPopup() + 1}`;
  }

  // Remove na hora: o evento "close" do <dialog> chega depois (tarefa separada) e,
  // ate la, o modal fechado ainda estaria no DOM.
  function fechar(dialogo) {
    if (dialogo.open) dialogo.close();
    dialogo.remove();
  }

  // Botao de salvar do form DENTRO do iframe (escondido pelo modal.css): o rodape
  // do modal clica nele. Sem ele (tela so de ver, confirmacao de exclusao): null.
  function botaoSalvar(quadro) {
    try {
      const doc = quadro.contentDocument;
      return doc && (doc.querySelector(".form-workspace-tools [name='_save']")
        || doc.querySelector("[name='_save']"));
    } catch (erro) {
      return null; // outra origem: sem acesso ao conteudo
    }
  }

  function criarRodape(dialogo, quadro) {
    const rodape = document.createElement("div");
    rodape.className = "sh-modal-rodape";
    const cancelar = document.createElement("button");
    cancelar.type = "button";
    cancelar.className = "btn btn-outline";
    cancelar.textContent = "Cancelar";
    cancelar.addEventListener("click", () => fechar(dialogo));
    const salvar = document.createElement("button");
    salvar.type = "button";
    salvar.className = "btn btn-mono";
    salvar.hidden = true;
    salvar.addEventListener("click", () => {
      const alvo = botaoSalvar(quadro);
      if (!alvo || salvar.disabled) return;
      salvar.disabled = true; // clique duplo nao cria dois registros
      salvar.textContent = "Salvando...";
      alvo.click();
    });
    // A cada pagina carregada no iframe (form, form com erro, resposta): acerta os botoes.
    quadro.addEventListener("load", () => {
      const alvo = botaoSalvar(quadro);
      salvar.hidden = !alvo;
      salvar.disabled = false;
      salvar.textContent = alvo ? alvo.textContent.trim() || "Salvar" : "Salvar";
      cancelar.textContent = alvo ? "Cancelar" : "Fechar";
    });
    rodape.append(cancelar, salvar);
    return rodape;
  }

  // Modal generico: url (pagina do admin com _popup), titulo, nome do iframe (o
  // Django acha o campo a preencher por ele) e aoSalvar opcional: com ele, salvar
  // chama aoSalvar(id, texto) em vez de preencher um campo (ex.: modal-lista.js).
  function abrirModal({ url, titulo, nome, aoSalvar }) {
    const endereco = new URL(url, window.location.href);
    endereco.searchParams.set("_popup", "1");

    const dialogo = document.createElement("dialog");
    dialogo.className = "sh-modal";
    dialogo.setAttribute("aria-label", titulo);
    dialogo.aoSalvar = aoSalvar || null;

    const topo = document.createElement("div");
    topo.className = "sh-modal-topo";
    const rotulo = document.createElement("span");
    rotulo.className = "sh-modal-titulo";
    rotulo.textContent = titulo;
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "btn btn-ghost btn-icon btn-sm";
    botao.setAttribute("aria-label", "Fechar");
    botao.appendChild(window.StarHub.icone("x", "icon-sm"));
    botao.addEventListener("click", () => fechar(dialogo));
    topo.append(rotulo, botao);

    const quadro = document.createElement("iframe");
    quadro.className = "sh-modal-corpo";
    quadro.name = nome;
    quadro.title = titulo;
    quadro.src = endereco.href;

    dialogo.append(topo, quadro, criarRodape(dialogo, quadro));
    // Clique no fundo escuro (fora da caixa) fecha; Esc o <dialog> ja fecha sozinho.
    dialogo.addEventListener("click", (evento) => { if (evento.target === dialogo) fechar(dialogo); });
    dialogo.addEventListener("close", () => dialogo.remove());
    document.body.appendChild(dialogo);
    dialogo.showModal();
    return dialogo;
  }

  function abrir(link) {
    const titulo = link.title || "Registro relacionado";
    return abrirModal({ url: link.href, titulo, nome: nomeDaJanela(link) });
  }

  function dialogoDa(janela) {
    return [...document.querySelectorAll("dialog.sh-modal")]
      .find((dialogo) => dialogo.querySelector("iframe")?.contentWindow === janela);
  }

  ["dismissAddRelatedObjectPopup", "dismissChangeRelatedObjectPopup",
    "dismissDeleteRelatedObjectPopup"].forEach((nome) => {
    const original = window[nome];
    window[nome] = function (janela, ...resto) {
      const dialogo = dialogoDa(janela);
      if (dialogo && dialogo.aoSalvar) {
        // Modal sem campo para preencher (inline): quem abriu decide o que fazer.
        const aoSalvar = dialogo.aoSalvar;
        fechar(dialogo);
        aoSalvar(...resto);
        return undefined;
      }
      const resultado = typeof original === "function"
        ? original.call(this, janela, ...resto) : undefined;
      if (dialogo) fechar(dialogo);
      return resultado;
    };
  });

  $("body").on("django:show-related", ".related-widget-wrapper-link", function (evento) {
    evento.preventDefault();
    abrir(this);
  });

  function fecharModalDe(janela) {
    const dialogo = dialogoDa(janela);
    if (dialogo) fechar(dialogo);
  }

  window.StarHub = Object.assign(window.StarHub || {}, {
    abrirModal, abrirModalRelacionado: abrir, fecharModalDe,
  });
})();
