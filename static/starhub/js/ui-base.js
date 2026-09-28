// Base dos widgets: painel flutuante e icone do sprite.
// O painel vai para o <body> com position: fixed, entao card com overflow,
// gaveta de filtros ou tabela com rolagem nunca cortam a lista/calendario.
(() => {
  "use strict";

  const abertos = [];
  const usoDoSprite = document.querySelector("svg.icon use");
  const sprite = usoDoSprite ? usoDoSprite.getAttribute("href").split("#")[0] : "";

  function icone(nome, classe) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    const uso = document.createElementNS(ns, "use");
    svg.setAttribute("class", `icon ${classe || ""}`.trim());
    svg.setAttribute("aria-hidden", "true");
    uso.setAttribute("href", `${sprite}#${nome}`);
    svg.appendChild(uso);
    return svg;
  }

  function posicionar(painel, ancora) {
    const caixa = ancora.getBoundingClientRect();
    const margem = 8;
    let topo = caixa.bottom + 6;
    // Sem espaco embaixo e com espaco em cima: abre para cima.
    if (topo + painel.offsetHeight > window.innerHeight - margem &&
        caixa.top - painel.offsetHeight - 6 > margem) {
      topo = caixa.top - painel.offsetHeight - 6;
    }
    const esquerda = Math.min(caixa.left, window.innerWidth - painel.offsetWidth - margem);
    painel.style.top = `${Math.max(margem, topo)}px`;
    painel.style.left = `${Math.max(margem, esquerda)}px`;
  }

  function fechar(painel) {
    const indice = abertos.findIndex((item) => item.painel === painel);
    if (indice === -1) {
      return;
    }
    const [item] = abertos.splice(indice, 1);
    item.painel.remove();
    item.ancora.classList.remove("sh-aberto");
    if (item.aoFechar) {
      item.aoFechar();
    }
  }

  function fecharTodos() {
    abertos.slice().forEach((item) => fechar(item.painel));
  }

  function abrir(painel, ancora, opcoes = {}) {
    fecharTodos();
    painel.classList.add("sh-flutuante");
    if (opcoes.larguraDaAncora) {
      painel.style.minWidth = `${ancora.getBoundingClientRect().width}px`;
    }
    document.body.appendChild(painel);
    ancora.classList.add("sh-aberto");
    abertos.push({ painel, ancora, aoFechar: opcoes.aoFechar });
    posicionar(painel, ancora);
  }

  document.addEventListener("mousedown", (evento) => {
    abertos.slice().forEach((item) => {
      if (!item.painel.contains(evento.target) && !item.ancora.contains(evento.target)) {
        fechar(item.painel);
      }
    });
  });

  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && abertos.length) {
      const { ancora } = abertos[abertos.length - 1];
      fecharTodos();
      ancora.focus();
    }
  });

  const reposicionar = () => abertos.forEach((item) => posicionar(item.painel, item.ancora));
  window.addEventListener("resize", reposicionar);
  window.addEventListener("scroll", reposicionar, true);

  // Tira acento e caixa: "Canecas" acha "canecas" e "cafe" acha "Café".
  const normalizar = (texto) =>
    (texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  // Roda `montar` agora e em cada linha nova de inline ("Adicionar outro(a)").
  function aoCarregar(montar) {
    const rodar = (raiz) => montar(raiz || document);
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => rodar());
    } else {
      rodar();
    }
    document.addEventListener("formset:added", (evento) => rodar(evento.target));
  }

  window.StarHub = Object.assign(window.StarHub || {}, {
    icone, normalizar, aoCarregar,
    flutuante: { abrir, fechar, fecharTodos, posicionar },
  });
})();
