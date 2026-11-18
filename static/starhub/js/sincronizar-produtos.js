// Acao em massa "Sincronizar com integracao" na lista de produtos
// (apps/loja/admin/produtos_sincronizar.py). Ao executar a acao, abre o dialog
// (templates/admin/loja/produto/_dialog_sincronizar.html) para escolher a integracao;
// a escolha vai no campo "integracao" do proprio form da acao, que segue para o Django
// com a selecao (inclusive "selecionar todos") intacta.
(() => {
  "use strict";
  const ACAO = "sincronizar_com_integracao";
  const lista = document.getElementById("changelist-form");
  const modal = document.getElementById("modal-sincronizar-produtos");
  if (!lista || !modal) return;
  const formModal = modal.querySelector("form");
  const quantos = modal.querySelector("[data-sincronizar-quantos]");
  let botaoAcao = null;

  const acaoEscolhida = () => {
    const selects = [...lista.querySelectorAll('select[name="action"]')];
    return selects.some((select) => select.value === ACAO);
  };
  const totalSelecionado = () => {
    const todos = lista.querySelector('input[name="select_across"]');
    if (todos && todos.value === "1") return "Todos os produtos do filtro atual";
    return `${lista.querySelectorAll("input.action-select:checked").length} produto(s)`;
  };
  const algoSelecionado = () => {
    const todos = lista.querySelector('input[name="select_across"]');
    return (todos && todos.value === "1") ||
      lista.querySelector("input.action-select:checked") !== null;
  };

  lista.addEventListener("submit", (evento) => {
    // Sem selecao o Django ja avisa "selecione itens"; com a integracao escolhida, segue.
    if (!acaoEscolhida() || !algoSelecionado() || lista.querySelector('input[name="integracao"]')) {
      return;
    }
    evento.preventDefault();
    botaoAcao = evento.submitter || null;
    if (quantos) quantos.textContent = totalSelecionado();
    if (!modal.open) modal.showModal();
  });

  // Captura no <dialog>: roda ANTES do modal-etapas.js (que, na 1a etapa, so avanca),
  // entao a etapa lida aqui e a do momento do envio. Envia so a partir da confirmacao.
  modal.addEventListener("submit", (evento) => {
    evento.preventDefault();
    const confirmacao = modal.querySelector('[data-etapa="2"]');
    if (confirmacao && confirmacao.hidden) return;
    const escolhida = formModal.querySelector('input[name="integracao"]:checked:not(:disabled)');
    if (!escolhida) return;
    const campo = document.createElement("input");
    campo.type = "hidden";
    campo.name = "integracao";
    campo.value = escolhida.value;
    lista.appendChild(campo);
    modal.close();
    // requestSubmit(botao) manda o "index" do botao clicado, como o clique original.
    if (botaoAcao && botaoAcao.form === lista) lista.requestSubmit(botaoAcao);
    else lista.requestSubmit();
  }, true);
})();
