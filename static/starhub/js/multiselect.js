// Multi-select do tema (ex.: Categorias): etiquetas com "x" dentro da caixa
// e lista flutuante com busca e caixinhas. Substitui a caixa de lista do
// navegador (Ctrl+clique). O <select multiple> do Django segue escondido.
(() => {
  "use strict";

  const { icone, normalizar, aoCarregar, flutuante } = window.StarHub;

  function ignorar(select) {
    return !select.multiple ||
      select.dataset.temaPronto ||
      "semTema" in select.dataset ||
      select.classList.contains("admin-autocomplete") ||
      select.classList.contains("selectfilter") ||
      select.classList.contains("selectfilterstacked") ||
      select.closest(".empty-form, .selector");
  }

  function avisar(select) {
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function montarLista(select, painel, filtro) {
    const lista = painel.querySelector(".sh-lista-itens");
    lista.replaceChildren();
    Array.from(select.options).forEach((opcao) => {
      if (filtro && !normalizar(opcao.text).includes(filtro)) {
        return;
      }
      const item = document.createElement("button");
      item.type = "button";
      item.className = "sh-lista-item";
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", String(opcao.selected));
      const marca = document.createElement("input");
      marca.type = "checkbox";
      marca.tabIndex = -1;
      marca.checked = opcao.selected;
      marca.setAttribute("aria-hidden", "true");
      item.append(marca, opcao.text);
      item.addEventListener("click", () => {
        opcao.selected = !opcao.selected;
        marca.checked = opcao.selected;
        item.setAttribute("aria-selected", String(opcao.selected));
        avisar(select);
      });
      lista.appendChild(item);
    });
    if (!lista.children.length) {
      lista.innerHTML = '<div class="sh-lista-vazia">Nada encontrado</div>';
    }
    const total = Array.from(select.options).filter((opcao) => opcao.selected).length;
    painel.querySelector(".sh-contagem").textContent = `${total} selecionado(s)`;
  }

  function abrirLista(select, caixa) {
    const painel = document.createElement("div");
    painel.innerHTML =
      '<div class="sh-lista-busca"><input type="search" placeholder="Buscar..."></div>' +
      '<div class="sh-lista-itens" role="listbox" aria-multiselectable="true"></div>' +
      '<div class="sh-lista-rodape"><span class="sh-contagem"></span>' +
      '<button type="button" class="btn btn-ghost btn-sm">Limpar</button></div>';
    const busca = painel.querySelector("input");
    const redesenhar = () => montarLista(select, painel, normalizar(busca.value));
    busca.addEventListener("input", redesenhar);
    painel.querySelector(".sh-lista-rodape button").addEventListener("click", () => {
      Array.from(select.options).forEach((opcao) => { opcao.selected = false; });
      avisar(select);
      redesenhar();
    });
    select.addEventListener("change", redesenhar);
    montarLista(select, painel, "");
    flutuante.abrir(painel, caixa, {
      larguraDaAncora: true,
      aoFechar: () => select.removeEventListener("change", redesenhar),
    });
    busca.focus();
  }

  function desenharEtiquetas(select, chips) {
    chips.replaceChildren();
    const escolhidas = Array.from(select.options).filter((opcao) => opcao.selected);
    if (!escolhidas.length) {
      chips.innerHTML = '<span class="sh-vazio">Selecione</span>';
      return;
    }
    escolhidas.forEach((opcao) => {
      const chip = document.createElement("span");
      chip.className = "sh-chip";
      const tirar = document.createElement("button");
      tirar.type = "button";
      tirar.setAttribute("aria-label", `Remover ${opcao.text}`);
      tirar.appendChild(icone("x", "icon-sm"));
      tirar.addEventListener("click", (evento) => {
        evento.stopPropagation();
        opcao.selected = false;
        avisar(select);
      });
      chip.append(opcao.text, tirar);
      chips.appendChild(chip);
    });
  }

  function montar(select) {
    select.dataset.temaPronto = "1";
    const caixa = document.createElement("div");
    caixa.className = "sh-multi";
    caixa.tabIndex = 0;
    caixa.setAttribute("role", "combobox");
    caixa.setAttribute("aria-haspopup", "listbox");
    const chips = document.createElement("div");
    chips.className = "sh-chips";
    caixa.append(chips, icone("chevron-down", "icon-sm"));

    const atualizar = () => desenharEtiquetas(select, chips);
    atualizar();
    select.addEventListener("change", atualizar);
    new MutationObserver(atualizar).observe(select, { childList: true, subtree: true });

    caixa.addEventListener("click", () => abrirLista(select, caixa));
    caixa.addEventListener("keydown", (evento) => {
      if (["Enter", " ", "ArrowDown"].includes(evento.key)) {
        evento.preventDefault();
        abrirLista(select, caixa);
      }
    });
    if (select.id) {
      document.querySelectorAll(`label[for="${select.id}"]`).forEach((rotulo) => {
        rotulo.addEventListener("click", (evento) => {
          evento.preventDefault();
          caixa.focus();
        });
      });
    }
    select.classList.add("sh-nativo");
    select.tabIndex = -1;
    select.after(caixa);
  }

  aoCarregar((raiz) => {
    raiz.querySelectorAll("select[multiple]").forEach((select) => {
      if (!ignorar(select)) {
        montar(select);
      }
    });
  });
})();
