// Linha de detalhe da listagem (templates/components/linha_detalhe.html): o botao da
// coluna "Acoes" abre, logo abaixo da linha, o conteudo do <template> ao lado dele
// (itens do pedido, variacoes do produto). Clicar de novo fecha.
(() => {
  "use strict";

  function fechar(linha, botao) {
    linha.nextElementSibling.remove();
    linha.classList.remove("sh-expandida");
    botao.setAttribute("aria-expanded", "false");
  }

  function abrir(linha, botao) {
    const detalhe = document.createElement("tr");
    detalhe.className = "sh-linha-detalhe";
    const celula = document.createElement("td");
    celula.colSpan = linha.cells.length;
    celula.appendChild(botao.parentElement.querySelector("template.sh-detalhe-conteudo").content.cloneNode(true));
    detalhe.appendChild(celula);
    linha.after(detalhe);
    linha.classList.add("sh-expandida");
    botao.setAttribute("aria-expanded", "true");
  }

  document.addEventListener("click", (evento) => {
    const botao = evento.target.closest("[data-detalhe]");
    if (!botao) return;
    evento.preventDefault();
    const linha = botao.closest("tr");
    const aberta = linha.nextElementSibling && linha.nextElementSibling.classList.contains("sh-linha-detalhe");
    if (aberta) fechar(linha, botao);
    else abrir(linha, botao);
  });
})();
