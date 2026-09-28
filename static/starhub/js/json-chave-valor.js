// Metadados (meta_data do Woo): linhas "chave = valor" com + e lixeira.
// Valor que veio como objeto/numero aparece como JSON e volta como JSON se
// ainda for JSON valido; assim um metadado estruturado do ERP nao vira texto.
(() => {
  "use strict";

  const { el, botao, registrar } = window.StarHub.json;

  function linhasChaveValor(itens, { aoMudar, rotuloChave = "Chave", rotuloValor = "Valor" }) {
    const raiz = el("div", "sh-kv");
    const corpo = el("div", "sh-kv-linhas");
    const linhas = itens.map((item) => ({ ...item, estruturado: typeof item.value === "object" && item.value !== null }));

    const tipado = (valor) => typeof valor === "number" || typeof valor === "boolean";

    function valorSalvo(linha, texto) {
      if (!linha.estruturado && !tipado(linha.valorOriginal)) return texto;
      try { return JSON.parse(texto); } catch (erro) { return texto; }
    }

    const avisar = () => aoMudar(linhas.map(({ estruturado, valorOriginal, ...resto }) => resto));

    function desenhar() {
      corpo.replaceChildren();
      if (!linhas.length) corpo.appendChild(el("div", "sh-kv-vazio", "Nenhum campo ainda."));
      linhas.forEach((linha, indice) => {
        const linhaEl = el("div", "sh-kv-linha");
        const chave = el("input");
        chave.type = "text";
        chave.placeholder = rotuloChave;
        chave.value = linha.key || "";
        chave.addEventListener("input", () => { linha.key = chave.value; avisar(); });
        const valor = el("input");
        valor.type = "text";
        valor.placeholder = rotuloValor;
        if (linha.valorOriginal === undefined) linha.valorOriginal = linha.value;
        valor.value = linha.estruturado || tipado(linha.value)
          ? JSON.stringify(linha.value) : (linha.value ?? "");
        valor.addEventListener("input", () => { linha.value = valorSalvo(linha, valor.value); avisar(); });
        const tirar = botao("", "btn btn-ghost btn-icon btn-sm", () => {
          linhas.splice(indice, 1);
          desenhar();
          avisar();
        }, "x");
        tirar.setAttribute("aria-label", "Remover linha");
        linhaEl.append(chave, valor, tirar);
        corpo.appendChild(linhaEl);
      });
    }

    const adicionar = botao("Adicionar campo", "btn btn-outline btn-sm sh-json-add", () => {
      linhas.push({ key: "", value: "" });
      desenhar();
      corpo.querySelector(".sh-kv-linha:last-child input").focus();
    }, "plus");
    raiz.append(corpo, adicionar);
    desenhar();
    return raiz;
  }

  window.StarHub.linhasChaveValor = linhasChaveValor;

  registrar("chave-valor", ({ caixa, ler, escrever }) => {
    const itens = ler([]).filter((item) => item && typeof item === "object");
    caixa.appendChild(linhasChaveValor(itens, { aoMudar: escrever }));
  });
})();
