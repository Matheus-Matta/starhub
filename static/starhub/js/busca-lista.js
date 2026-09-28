// Busca da listagem sem botao: envia sozinha 600ms depois da ultima tecla
// (debounce), com 2+ letras ou campo vazio (limpar a busca). A busca e do
// proprio Django (?q=), entao a pagina recarrega; na volta o foco e o cursor
// voltam para o fim do campo, para a pessoa continuar digitando.
(() => {
  "use strict";

  const ESPERA_MS = 600;
  const CHAVE_FOCO = "starhub.busca-lista-foco";

  document.querySelectorAll("form[data-busca-automatica]").forEach((form) => {
    const campo = form.querySelector('input[type="search"]');
    if (!campo) return;
    const inicial = campo.value;
    let espera = null;

    const enviar = () => {
      const termo = campo.value.trim();
      if (termo === inicial.trim() || (termo && termo.length < 2)) return;
      try { window.sessionStorage.setItem(CHAVE_FOCO, "1"); } catch (erro) { /* sem storage */ }
      if (form.requestSubmit) form.requestSubmit(); else form.submit();
    };

    campo.addEventListener("input", () => {
      clearTimeout(espera);
      espera = setTimeout(enviar, ESPERA_MS);
    });
    // O "x" do input search limpa o campo: mostra tudo de novo sem esperar.
    // (O evento "search" tambem dispara no Enter, que ja envia o form sozinho.)
    campo.addEventListener("search", () => {
      if (campo.value === "") { clearTimeout(espera); enviar(); }
    });
    form.addEventListener("submit", () => clearTimeout(espera));

    try {
      if (window.sessionStorage.getItem(CHAVE_FOCO) === "1") {
        window.sessionStorage.removeItem(CHAVE_FOCO);
        campo.focus();
        campo.setSelectionRange(campo.value.length, campo.value.length);
      }
    } catch (erro) { /* sem storage: so nao devolve o foco */ }
  });
})();
