// Objeto com campos fixos (endereco, dimensoes) em grade de 12 colunas. Cada
// campo aceita largura (colunas), placeholder e mascara (mascaras.js); sem
// largura, divide a linha por config.colunas.
// Com config.extras, as chaves que nao estao na lista (o que o ERP mandar a
// mais) aparecem em "Outros campos" como chave/valor, e continuam salvas.
(() => {
  "use strict";

  const { el, registrar } = window.StarHub.json;

  registrar("objeto", ({ caixa, config, ler, escrever }) => {
    const campos = config.campos || [];
    const conhecidos = new Set(campos.map((campo) => campo.campo));
    const valor = ler({});
    const dados = typeof valor === "object" && !Array.isArray(valor) ? { ...valor } : {};
    let extras = Object.entries(dados)
      .filter(([chave]) => !conhecidos.has(chave))
      .map(([key, value]) => ({ key, value }));

    const avisar = () => {
      const saida = {};
      campos.forEach((campo) => { saida[campo.campo] = dados[campo.campo] ?? ""; });
      extras.forEach(({ key, value }) => {
        if (String(key || "").trim()) saida[String(key).trim()] = value;
      });
      escrever(saida);
    };

    if (!campos.length) {
      caixa.appendChild(window.StarHub.linhasChaveValor(extras, {
        aoMudar: (lista) => { extras = lista; avisar(); },
      }));
      return;
    }

    const grade = el("div", "sh-objeto");
    grade.style.setProperty("--sh-colunas", 12);
    const padrao = Math.floor(12 / (config.colunas || 2));
    campos.forEach((campo) => {
      const rotulo = el("label", `sh-objeto-campo sh-objeto-c${campo.largura || padrao}`);
      rotulo.appendChild(el("span", "", campo.rotulo));
      const entrada = el("input");
      entrada.type = "text";
      if (campo.tipo === "numero-texto") {
        entrada.inputMode = "decimal";
        entrada.placeholder = "0";
      }
      if (campo.placeholder) entrada.placeholder = campo.placeholder;
      entrada.value = dados[campo.campo] ?? "";
      // Mascara antes do "input" abaixo: assim o valor salvo ja sai formatado.
      if (campo.mascara) window.StarHub.mascarar(entrada, campo.mascara);
      entrada.addEventListener("input", () => { dados[campo.campo] = entrada.value; avisar(); });
      rotulo.appendChild(entrada);
      grade.appendChild(rotulo);
    });
    caixa.appendChild(grade);

    if (config.extras) {
      const outros = el("details", "sh-objeto-extras");
      if (extras.length) outros.open = true;
      outros.appendChild(el("summary", "", `Outros campos (${extras.length})`));
      outros.appendChild(window.StarHub.linhasChaveValor(extras, {
        aoMudar: (lista) => {
          extras = lista;
          outros.querySelector("summary").textContent = `Outros campos (${lista.length})`;
          avisar();
        },
      }));
      caixa.appendChild(outros);
    }
  });
})();
