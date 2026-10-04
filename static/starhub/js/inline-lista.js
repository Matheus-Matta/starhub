// Inline em formato de lista (templates/admin/edit_inline/lista.html).
//
// "+ Adicionar ..." do titulo aciona o "adicionar" do inlines.js do Django, que fica
// escondido no fim da tabela: a linha nova nasce pela mecanica do Django (indices,
// TOTAL_FORMS), sem reimplementar nada.
//
// Lixeira: linha nova (nao salva) sai de vez pelo "remover" do Django; linha salva
// ganha o DELETE marcado e some da tela (so sai do banco ao salvar). Enquanto isso,
// a barra do rodape conta as removidas e oferece "Desfazer".
(() => {
  "use strict";

  const marcaDe = (linha) => linha.querySelector('input[type="checkbox"][name$="-DELETE"]');

  function atualizar(grupo) {
    const barra = grupo.querySelector(".sh-inline-desfazer");
    if (!barra) return;
    const total = grupo.querySelectorAll("tr.sh-removida").length;
    barra.hidden = total === 0;
    const nome = total === 1 ? barra.dataset.singular : barra.dataset.plural;
    barra.querySelector("[data-inline-contagem]").textContent = `${total} ${nome} para remover ao salvar.`;
  }

  function remover(linha) {
    const grupo = linha.closest(".sh-inline-lista");
    const descartar = linha.querySelector(".inline-deletelink");
    if (descartar) {
      descartar.click();
    } else if (marcaDe(linha)) {
      marcaDe(linha).checked = true;
      marcaDe(linha).dispatchEvent(new Event("change", { bubbles: true }));
      linha.classList.add("sh-removida");
    }
    atualizar(grupo);
  }

  function desfazer(grupo) {
    grupo.querySelectorAll("tr.sh-removida").forEach((linha) => {
      marcaDe(linha).checked = false;
      marcaDe(linha).dispatchEvent(new Event("change", { bubbles: true }));
      linha.classList.remove("sh-removida");
    });
    atualizar(grupo);
  }

  document.addEventListener("click", (evento) => {
    const alvo = evento.target.closest("[data-inline-adicionar], [data-inline-remover], [data-inline-desfazer]");
    if (!alvo) return;
    evento.preventDefault();
    if (alvo.hasAttribute("data-inline-adicionar")) {
      const adicionar = document.querySelector(`#${alvo.dataset.inlineAdicionar}-group .add-row a`);
      if (adicionar) adicionar.click();
    } else if (alvo.hasAttribute("data-inline-remover")) {
      remover(alvo.closest("tr.form-row"));
    } else {
      desfazer(alvo.closest(".sh-inline-lista"));
    }
  });

  // Pagina voltou com erro de validacao: o que ja estava marcado continua fora da tela.
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".sh-inline-lista").forEach((grupo) => {
      grupo.querySelectorAll("tr.form-row").forEach((linha) => {
        if (marcaDe(linha) && marcaDe(linha).checked) linha.classList.add("sh-removida");
      });
      atualizar(grupo);
    });
  });
})();
