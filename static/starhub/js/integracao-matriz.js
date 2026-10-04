(function () {
  "use strict";

  document.addEventListener("click", function (evento) {
    const botao = evento.target.closest("[data-integracao-marcar]");
    if (!botao) return;

    const matriz = botao.closest(".card").querySelector(".integracao-matriz");
    const acao = botao.dataset.integracaoMarcar;
    let seletor = 'input[type="checkbox"]';
    if (acao === "receber" || acao === "enviar") {
      seletor = `[data-direcao="${acao}"] input[type="checkbox"]`;
    }
    matriz.querySelectorAll(seletor).forEach(function (campo) {
      if (campo.disabled) return;
      campo.checked = acao !== "nenhum";
      campo.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
})();
