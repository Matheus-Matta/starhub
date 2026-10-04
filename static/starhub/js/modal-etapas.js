// Modal com etapas (templates/components/modal_etapas.html). Nao conhece nenhuma
// tela: tudo que muda por tela vem de atributos data-* (lista no componente).
(() => {
  "use strict";

  const marcados = (modal, nome) =>
    [...modal.querySelectorAll(`input[name="${nome}"]:checked:not(:disabled)`)];

  function aplicarVisibilidade(modal) {
    modal.querySelectorAll("[data-mostra-se]").forEach((bloco) => {
      const [nome, valor] = bloco.dataset.mostraSe.split("=");
      const escolhido = modal.querySelector(`input[name="${nome}"]:checked`);
      const visivel = !!escolhido && escolhido.value === valor;
      bloco.hidden = !visivel;
      // Escondido fica disabled: nao vai no POST nem conta na validacao.
      bloco.querySelectorAll("input").forEach((campo) => {
        campo.disabled = !visivel || campo.dataset.travado === "1";
      });
    });
  }

  function preencherResumo(modal) {
    const rotulo = (input) => input.dataset.rotulo || input.value;
    modal.querySelectorAll("[data-resumo]").forEach((alvo) => {
      const escolhido = marcados(modal, alvo.dataset.resumo)[0];
      alvo.textContent = escolhido ? rotulo(escolhido) : "";
    });
    modal.querySelectorAll("[data-resumo-lista]").forEach((lista) => {
      lista.replaceChildren(...marcados(modal, lista.dataset.resumoLista).map((input) => {
        const item = document.createElement("li");
        item.textContent = rotulo(input);
        return item;
      }));
    });
  }

  function iniciar(modal) {
    const etapas = [...modal.querySelectorAll("[data-etapa]")];
    const erro = modal.querySelector("[data-etapas-erro]");
    const voltar = modal.querySelector("[data-etapa-voltar]");
    const avancar = modal.querySelector("[data-etapa-avancar]");
    const concluir = modal.querySelector("[data-etapa-concluir]");
    let atual = 1;

    function mostrar(numero) {
      atual = numero;
      etapas.forEach((etapa) => { etapa.hidden = Number(etapa.dataset.etapa) !== numero; });
      modal.querySelectorAll("[data-etapa-indicador]").forEach((item) => {
        const n = Number(item.dataset.etapaIndicador);
        item.classList.toggle("ativa", n === numero);
        item.classList.toggle("feita", n < numero);
        if (n === numero) item.setAttribute("aria-current", "step");
        else item.removeAttribute("aria-current");
      });
      const ultima = numero === etapas.length;
      voltar.hidden = numero === 1;
      avancar.hidden = ultima;
      concluir.hidden = !ultima;
      erro.hidden = true;
      if (ultima) preencherResumo(modal);
      const foco = etapas[numero - 1].querySelector("input:checked:not(:disabled), input:not(:disabled)");
      if (foco && modal.open) foco.focus();
    }

    function validar() {
      const exigencia = etapas[atual - 1].querySelector("[data-exige-marcado]");
      const nome = exigencia && exigencia.dataset.exigeMarcado;
      if (nome && !marcados(modal, nome).length) {
        erro.textContent = exigencia.dataset.mensagemErro || "Escolha ao menos uma opcao.";
        erro.hidden = false;
        return false;
      }
      return true;
    }

    avancar.addEventListener("click", () => { if (validar()) mostrar(atual + 1); });
    voltar.addEventListener("click", () => mostrar(atual - 1));
    modal.querySelector("[data-fechar-etapas]").addEventListener("click", () => modal.close());
    // Enter num campo nao pode enviar o POST antes da ultima etapa.
    modal.querySelector("form").addEventListener("submit", (evento) => {
      if (atual !== etapas.length) {
        evento.preventDefault();
        avancar.click();
      }
    });
    modal.addEventListener("change", (evento) => {
      if (!evento.target.matches("input")) return;
      aplicarVisibilidade(modal);
      erro.hidden = true;
    });
    modal.querySelectorAll("[data-marcar-todos]").forEach((botao) => {
      botao.addEventListener("click", () => {
        modal.querySelectorAll(`input[name="${botao.dataset.marcarTodos}"]:not(:disabled)`)
          .forEach((campo) => { campo.checked = true; });
      });
    });
    // Esc fecha sozinho (dialog nativo); ao fechar volta para a primeira etapa.
    modal.addEventListener("close", () => mostrar(1));
    modal.addEventListener("click", (evento) => { if (evento.target === modal) modal.close(); });
    aplicarVisibilidade(modal);
    mostrar(1);
  }

  document.querySelectorAll("[data-modal-etapas]").forEach(iniciar);
  document.addEventListener("click", (evento) => {
    const botao = evento.target.closest("[data-abrir-modal-etapas]");
    if (!botao) return;
    const modal = document.getElementById(botao.dataset.abrirModalEtapas);
    // Sem isto, botao apontando para modal ausente falha calado (defeito ja visto).
    if (!modal) {
      console.warn(`modal-etapas: nao existe elemento com id "${botao.dataset.abrirModalEtapas}".`);
      return;
    }
    if (!modal.open) modal.showModal();
  });
})();
