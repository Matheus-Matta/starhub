// Comportamento da casca do tema. JS puro, sem dependencia.
// O botao de tema (claro/escuro/auto) e do proprio Django: admin/js/theme.js
// procura qualquer .theme-toggle na pagina.
(function () {
  "use strict";

  var CHAVE_RECOLHIDO = "starhub.sidebar-recolhido";
  var corpo = document.body;

  function lerPreferencia() {
    try {
      return window.localStorage.getItem(CHAVE_RECOLHIDO) === "1";
    } catch (erro) {
      return false; // navegador bloqueou o storage: segue com o menu aberto
    }
  }

  function gravarPreferencia(recolhido) {
    try {
      window.localStorage.setItem(CHAVE_RECOLHIDO, recolhido ? "1" : "0");
    } catch (erro) {
      /* sem storage a preferencia so vale ate recarregar */
    }
  }

  if (lerPreferencia()) {
    corpo.classList.add("sidebar-collapse");
  }

  document.addEventListener("click", function (evento) {
    var alvo = evento.target.closest("[data-acao]");
    if (alvo) {
      var acao = alvo.getAttribute("data-acao");
      if (acao === "recolher-menu") {
        var recolhido = corpo.classList.toggle("sidebar-collapse");
        gravarPreferencia(recolhido);
      } else if (acao === "abrir-menu") {
        corpo.classList.add("sidebar-open");
      } else if (acao === "fechar-menu") {
        corpo.classList.remove("sidebar-open");
      } else if (acao === "abrir-filtros") {
        abrirFiltros();
      } else if (acao === "fechar-filtros") {
        corpo.classList.remove("drawer-aberto");
      } else if (acao === "dropdown") {
        var dropdown = alvo.closest("[data-dropdown]");
        var aberto = dropdown.classList.toggle("open");
        alvo.setAttribute("aria-expanded", aberto ? "true" : "false");
        evento.stopPropagation();
        return;
      }
    }
    // Clique fora fecha qualquer dropdown aberto.
    document.querySelectorAll("[data-dropdown].open").forEach(function (item) {
      if (!item.contains(evento.target)) {
        item.classList.remove("open");
      }
    });
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "Escape") {
      return;
    }
    corpo.classList.remove("sidebar-open");
    corpo.classList.remove("drawer-aberto");
    document.querySelectorAll("[data-dropdown].open").forEach(function (item) {
      item.classList.remove("open");
    });
  });

  // Gaveta de filtros. Clicar num filtro recarrega a pagina; a gaveta volta
  // aberta para a pessoa combinar outro filtro sem clicar em "Filtros" de novo.
  var CHAVE_GAVETA = "starhub.gaveta-filtros";

  function abrirFiltros() {
    corpo.classList.add("drawer-aberto");
    var primeiro = document.querySelector("#changelist-filter .drawer-corpo a");
    if (primeiro) {
      primeiro.focus({ preventScroll: true });
    }
  }

  document.querySelectorAll("#changelist-filter .drawer-corpo").forEach(function (gaveta) {
    gaveta.addEventListener("click", function (evento) {
      if (evento.target.closest("a")) {
        try { window.sessionStorage.setItem(CHAVE_GAVETA, "1"); } catch (erro) { /* sem storage */ }
      }
    });
  });

  try {
    if (window.sessionStorage.getItem(CHAVE_GAVETA) === "1") {
      window.sessionStorage.removeItem(CHAVE_GAVETA);
      if (document.getElementById("changelist-filter")) {
        abrirFiltros();
      }
    }
  } catch (erro) { /* sem storage a gaveta so abre pelo botao */ }

  function marcarRolagem() {
    corpo.classList.toggle("is-scrolled", window.scrollY > 0);
  }

  window.addEventListener("scroll", marcarRolagem, { passive: true });
  marcarRolagem();
  // Trilha: o Django escreve "Inicio › Loja › Produtos" como texto solto.
  // Troca cada "›" pela seta do template, sem mexer nos links.
  function setaDaTrilha(sprite) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    var uso = document.createElementNS("http://www.w3.org/2000/svg", "use");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    uso.setAttribute("href", sprite + "#chevron-right");
    svg.appendChild(uso);
    return svg;
  }

  var usoExistente = document.querySelector("svg.icon use");
  var sprite = usoExistente ? usoExistente.getAttribute("href").split("#")[0] : null;
  document.querySelectorAll(".app-header .breadcrumbs").forEach(function (trilha) {
    if (!sprite) {
      return;
    }
    Array.prototype.slice.call(trilha.childNodes).forEach(function (no) {
      if (no.nodeType !== Node.TEXT_NODE || no.textContent.indexOf("›") === -1) {
        return;
      }
      no.textContent.split("›").forEach(function (parte, indice) {
        if (indice > 0) {
          trilha.insertBefore(setaDaTrilha(sprite), no);
        }
        if (parte.trim()) {
          var texto = document.createElement("span");
          texto.textContent = parte.trim();
          trilha.insertBefore(texto, no);
        }
      });
      trilha.removeChild(no);
    });
  });

  // Ctrl+K / Cmd+K foca a busca do header (o "Ctrl K" desenhado no campo).
  document.addEventListener("keydown", function (evento) {
    if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === "k") {
      var busca = document.querySelector("[data-atalho-busca]");
      if (busca && busca.offsetParent !== null) {
        evento.preventDefault();
        busca.focus();
        busca.select();
      }
    }
  });
})();
