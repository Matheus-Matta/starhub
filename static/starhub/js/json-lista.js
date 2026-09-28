// Tabela de linhas com colunas tipadas (frete, taxas, cupons, atributos).
// config.colunas: [{campo, rotulo, tipo}] com tipo texto | numero | dinheiro
// | switch | tags | escolha (select de coluna.opcoes) | valor (10, true, ["a"]:
// o servidor converte). Chaves que a tela nao mostra (id, taxes...) ficam.
(() => {
  "use strict";

  const { el, botao, registrar } = window.StarHub.json;

  const LARGURAS = { tags: "minmax(180px, 2fr)", switch: "90px", dinheiro: "140px", numero: "110px",
    escolha: "minmax(150px, 1fr)" };

  // Texto que o servidor leria como outro tipo ("10", "true") vai entre aspas
  // para continuar texto; numero, booleano e lista aparecem como JSON.
  function valorParaTexto(valor) {
    if (valor === undefined || valor === null) return "";
    if (typeof valor !== "string") return JSON.stringify(valor);
    try { JSON.parse(valor); return JSON.stringify(valor); } catch (erro) { return valor; }
  }

  function valorInicial(coluna) {
    if (coluna.tipo === "switch") return true;
    if (coluna.tipo === "tags") return [];
    if (coluna.tipo === "escolha") return (coluna.opcoes || [])[0]?.valor ?? "";
    return "";
  }

  function controle(coluna, linha, avisar) {
    const valor = linha[coluna.campo];
    if (coluna.tipo === "switch") {
      const caixa = el("label", "sh-lista-switch");
      const marca = el("input", "switch");
      marca.type = "checkbox";
      marca.checked = Boolean(valor);
      marca.setAttribute("aria-label", coluna.rotulo);
      marca.addEventListener("change", () => { linha[coluna.campo] = marca.checked; avisar(); });
      caixa.appendChild(marca);
      return caixa;
    }
    if (coluna.tipo === "tags") {
      return window.StarHub.criarTags(Array.isArray(valor) ? valor : [], {
        placeholder: "Enter para criar",
        aoMudar: (lista) => { linha[coluna.campo] = lista; avisar(); },
      });
    }
    if (coluna.tipo === "escolha") {
      const lista = el("select");
      lista.setAttribute("aria-label", coluna.rotulo);
      (coluna.opcoes || []).forEach((opcao) => {
        const item = el("option", "", opcao.rotulo);
        item.value = opcao.valor;
        item.selected = opcao.valor === valor;
        lista.appendChild(item);
      });
      lista.addEventListener("change", () => { linha[coluna.campo] = lista.value; avisar(); });
      return lista;
    }
    const campo = el("input");
    campo.type = coluna.tipo === "numero" ? "number" : "text";
    campo.setAttribute("aria-label", coluna.rotulo);
    if (coluna.tipo === "dinheiro") {
      campo.inputMode = "decimal";
      campo.placeholder = "0,00";
      campo.classList.add("sh-num");
      // Mostra com virgula; o servidor normaliza para "10.50" (formato Woo).
      campo.value = valor ? String(valor).replace(".", ",") : "";
    } else if (coluna.tipo === "valor") {
      campo.value = valorParaTexto(valor);
    } else {
      campo.value = valor ?? "";
    }
    if (coluna.placeholder) campo.placeholder = coluna.placeholder;
    campo.addEventListener("input", () => { linha[coluna.campo] = campo.value; avisar(); });
    return campo;
  }

  registrar("lista", ({ caixa, config, ler, escrever }) => {
    const colunas = config.colunas || [];
    const linhas = ler([]).filter((item) => item && typeof item === "object");
    const grade = colunas.map((coluna) => LARGURAS[coluna.tipo] || "minmax(120px, 1fr)")
      .concat("36px").join(" ");
    const raiz = el("div", "sh-lista-tabela");
    const corpo = el("div", "sh-lista-linhas");
    const avisar = () => escrever(linhas);

    const topo = el("div", "sh-lista-cabecalho");
    topo.style.gridTemplateColumns = grade;
    colunas.forEach((coluna) => topo.appendChild(el("span", "", coluna.rotulo)));
    topo.appendChild(el("span"));

    function desenhar() {
      corpo.replaceChildren();
      topo.hidden = !linhas.length;
      if (!linhas.length) corpo.appendChild(el("div", "sh-kv-vazio", "Nenhuma linha ainda."));
      linhas.forEach((linha, indice) => {
        const linhaEl = el("div", "sh-lista-linha");
        linhaEl.style.gridTemplateColumns = grade;
        colunas.forEach((coluna) => linhaEl.appendChild(controle(coluna, linha, avisar)));
        const tirar = botao("", "btn btn-ghost btn-icon btn-sm", () => {
          linhas.splice(indice, 1);
          desenhar();
          avisar();
        }, "x");
        tirar.setAttribute("aria-label", "Remover linha");
        linhaEl.appendChild(tirar);
        corpo.appendChild(linhaEl);
      });
    }

    const adicionar = botao(config.botao || "Adicionar linha", "btn btn-outline btn-sm sh-json-add", () => {
      const nova = {};
      colunas.forEach((coluna) => { nova[coluna.campo] = valorInicial(coluna); });
      linhas.push(nova);
      desenhar();
      avisar();
      const campo = corpo.querySelector(".sh-lista-linha:last-child input");
      if (campo) campo.focus();
    }, "plus");

    raiz.append(topo, corpo, adicionar);
    caixa.appendChild(raiz);
    desenhar();
  });
})();
