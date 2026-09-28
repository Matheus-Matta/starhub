// Select do tema: botao com a opcao escolhida + lista flutuante com check,
// e busca quando ha muitas opcoes. O <select> do Django continua no form,
// escondido e sincronizado (o form envia ele; o "+" do admin mexe nele).
(() => {
  "use strict";

  const { icone, normalizar, aoCarregar, flutuante } = window.StarHub;
  const BUSCA_A_PARTIR_DE = 8;

  function ignorar(select) {
    return select.multiple ||
      select.dataset.temaPronto ||
      "semTema" in select.dataset ||
      select.classList.contains("admin-autocomplete") ||
      select.classList.contains("selectfilter") ||
      select.classList.contains("selectfilterstacked") ||
      select.closest(".empty-form, .selector");
  }

  function focarVizinho(atual, passo) {
    const itens = Array.from(atual.parentElement.querySelectorAll(".sh-lista-item:not(:disabled)"));
    const proximo = itens[itens.indexOf(atual) + passo];
    if (proximo) {
      proximo.focus();
    }
  }

  function montarLista(select, gatilho, painel, filtro) {
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
      item.disabled = opcao.disabled;
      item.append(opcao.text || "—");
      if (opcao.selected) {
        item.classList.add("sh-selecionado");
        item.setAttribute("aria-selected", "true");
        item.appendChild(icone("check", "icon-sm sh-check"));
      }
      item.addEventListener("click", () => {
        select.value = opcao.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        flutuante.fechar(painel);
        gatilho.focus();
      });
      item.addEventListener("keydown", (evento) => {
        if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
          evento.preventDefault();
          focarVizinho(item, evento.key === "ArrowDown" ? 1 : -1);
        }
      });
      lista.appendChild(item);
    });
    if (!lista.children.length) {
      lista.innerHTML = '<div class="sh-lista-vazia">Nada encontrado</div>';
    }
  }

  function abrirLista(select, gatilho) {
    const painel = document.createElement("div");
    painel.innerHTML = '<div class="sh-lista-itens" role="listbox"></div>';
    let busca = null;
    if (select.options.length >= BUSCA_A_PARTIR_DE) {
      const caixa = document.createElement("div");
      caixa.className = "sh-lista-busca";
      busca = document.createElement("input");
      busca.type = "search";
      busca.placeholder = "Buscar...";
      busca.addEventListener("input", () =>
        montarLista(select, gatilho, painel, normalizar(busca.value)));
      busca.addEventListener("keydown", (evento) => {
        if (evento.key === "ArrowDown") {
          evento.preventDefault();
          const primeiro = painel.querySelector(".sh-lista-item:not(:disabled)");
          if (primeiro) primeiro.focus();
        }
      });
      caixa.appendChild(busca);
      painel.prepend(caixa);
    }
    montarLista(select, gatilho, painel, "");
    flutuante.abrir(painel, gatilho, { larguraDaAncora: true });
    const alvo = busca || painel.querySelector(".sh-selecionado") ||
      painel.querySelector(".sh-lista-item");
    if (alvo) {
      alvo.focus();
      if (!busca) alvo.scrollIntoView({ block: "nearest" });
    }
  }

  function montar(select) {
    select.dataset.temaPronto = "1";
    const gatilho = document.createElement("button");
    gatilho.type = "button";
    gatilho.className = "sh-select";
    gatilho.setAttribute("aria-haspopup", "listbox");
    const valor = document.createElement("span");
    valor.className = "sh-select-valor";
    gatilho.append(valor, icone("chevron-down", "icon-sm"));
    if (select.id) {
      gatilho.id = `${select.id}__tema`;
      document.querySelectorAll(`label[for="${select.id}"]`).forEach((rotulo) => {
        rotulo.htmlFor = gatilho.id;
      });
    }

    const atualizar = () => {
      const opcao = select.options[select.selectedIndex];
      valor.textContent = opcao && opcao.text ? opcao.text : "Selecione";
      valor.classList.toggle("sh-vazio", !select.value);
      gatilho.disabled = select.disabled;
    };
    atualizar();
    select.addEventListener("change", atualizar);
    // O popup "+" do admin acrescenta <option> direto no select.
    new MutationObserver(atualizar).observe(select, {
      childList: true, subtree: true, characterData: true, attributes: true,
    });

    gatilho.addEventListener("click", () => abrirLista(select, gatilho));
    gatilho.addEventListener("keydown", (evento) => {
      if (["ArrowDown", "ArrowUp"].includes(evento.key)) {
        evento.preventDefault();
        abrirLista(select, gatilho);
      }
    });
    select.classList.add("sh-nativo");
    select.tabIndex = -1;
    select.after(gatilho);
  }

  aoCarregar((raiz) => {
    raiz.querySelectorAll("select").forEach((select) => {
      if (!ignorar(select)) {
        montar(select);
      }
    });
  });
})();
