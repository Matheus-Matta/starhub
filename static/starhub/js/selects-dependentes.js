// Select que depende de outro na mesma linha: <select data-depende-de="tipo"> com
// <option data-pai="3">. Escolheu o Tipo "Cor": o Valor mostra so Branco, Preto...
// (apps/loja/admin/opcoes.py). O "+" do valor abre o cadastro com o tipo ja escolhido.
(() => {
  "use strict";

  const originais = new WeakMap(); // select -> todas as <option> (inclusive as filtradas)

  function linhaDe(select) {
    return select.closest("tr, .form-row, .inline-related") || select.form;
  }

  function paiDe(select) {
    const nome = select.dataset.dependeDe;
    // Em inline o nome ganha prefixo ("opcoes-0-valor" -> "opcoes-0-tipo").
    const prefixo = select.name.slice(0, select.name.lastIndexOf("-") + 1);
    return linhaDe(select).querySelector(`select[name="${prefixo}${nome}"], select[name="${nome}"]`);
  }

  function filtrar(select, pai) {
    const todas = originais.get(select);
    // Opcao que o "+" acabou de criar (ainda nao conhecida): nasce do tipo escolhido.
    [...select.options].forEach((opcao) => {
      if (opcao.value && !todas.includes(opcao)) {
        opcao.dataset.pai = opcao.dataset.pai || pai.value;
        todas.push(opcao);
      }
    });
    const escolhido = select.value;
    const visiveis = todas.filter((opcao) => !opcao.value || opcao.dataset.pai === pai.value);
    select.replaceChildren(...visiveis);
    select.value = visiveis.some((opcao) => opcao.value === escolhido) ? escolhido : "";
    const mais = document.getElementById(`add_${select.id}`);
    if (mais) {
      const url = new URL(mais.href, window.location.href);
      if (pai.value) url.searchParams.set(pai.name.split("-").pop(), pai.value);
      mais.href = url.href;
    }
  }

  function montar(select) {
    if (originais.has(select) || select.closest(".empty-form")) return;
    const pai = paiDe(select);
    if (!pai) return;
    originais.set(select, [...select.options]);
    pai.addEventListener("change", () => {
      filtrar(select, pai);
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    filtrar(select, pai);
  }

  window.StarHub.aoCarregar((raiz) => {
    raiz.querySelectorAll("select[data-depende-de]").forEach(montar);
  });
})();
