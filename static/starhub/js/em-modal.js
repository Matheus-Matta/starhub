// Carregado no <head>, antes de pintar: marca o <html> quando a pagina esta
// DENTRO do modal de relacao (iframe com _popup). O modal.css esconde entao o
// cabecalho e a barra de salvar da propria pagina: quem mostra titulo e botoes
// e o modal (static/starhub/js/modal-relacionado.js). Aberta como janela ou
// direto no navegador, a pagina continua com os botoes dela.
if (window.parent !== window && new URLSearchParams(window.location.search).has("_popup")) {
  document.documentElement.classList.add("em-modal");
}
