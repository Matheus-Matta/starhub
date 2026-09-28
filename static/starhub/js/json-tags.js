// Etiquetas criadas na hora (estilo Tagify): digite e aperte Enter, virgula
// ou Tab. Backspace no campo vazio apaga a ultima; colar "a, b, c" cria tres.
// StarHub.criarTags tambem e usado pela coluna "tags" do json-lista.js.
(() => {
  "use strict";

  const { icone, normalizar, flutuante } = window.StarHub;
  const { el, registrar } = window.StarHub.json;

  function criarTags(valores, { sugestoes = [], placeholder = "Digite e aperte Enter", aoMudar }) {
    let lista = [...valores];
    const caixa = el("div", "sh-tags");
    const campo = el("input");
    campo.type = "text";
    campo.placeholder = placeholder;
    let painel = null;

    const avisar = () => aoMudar([...lista]);

    function desenhar() {
      caixa.querySelectorAll(".sh-chip").forEach((chip) => chip.remove());
      lista.forEach((nome, indice) => {
        const chip = el("span", "sh-chip", nome);
        const tirar = el("button");
        tirar.type = "button";
        tirar.setAttribute("aria-label", `Remover ${nome}`);
        tirar.appendChild(icone("x", "icon-sm"));
        tirar.addEventListener("click", () => {
          lista.splice(indice, 1);
          desenhar();
          avisar();
        });
        chip.appendChild(tirar);
        caixa.insertBefore(chip, campo);
      });
      campo.placeholder = lista.length ? "" : placeholder;
    }

    function adicionar(texto) {
      let mudou = false;
      texto.split(/[,;\n]/).map((parte) => parte.trim()).filter(Boolean).forEach((nome) => {
        if (!lista.some((atual) => normalizar(atual) === normalizar(nome))) {
          lista.push(nome);
          mudou = true;
        }
      });
      campo.value = "";
      fecharSugestoes();
      if (mudou) {
        desenhar();
        avisar();
      }
    }

    function fecharSugestoes() {
      if (painel) flutuante.fechar(painel);
      painel = null;
    }

    function mostrarSugestoes() {
      const termo = normalizar(campo.value);
      const opcoes = sugestoes
        .filter((nome) => !lista.some((atual) => normalizar(atual) === normalizar(nome)))
        .filter((nome) => !termo || normalizar(nome).includes(termo))
        .slice(0, 8);
      fecharSugestoes();
      if (!opcoes.length || !termo) return;
      painel = el("div");
      const itens = el("div", "sh-lista-itens");
      opcoes.forEach((nome) => {
        const item = el("button", "sh-lista-item", nome);
        item.type = "button";
        item.addEventListener("mousedown", (evento) => evento.preventDefault());
        item.addEventListener("click", () => { adicionar(nome); campo.focus(); });
        itens.appendChild(item);
      });
      painel.appendChild(itens);
      flutuante.abrir(painel, caixa, { larguraDaAncora: true, aoFechar: () => { painel = null; } });
    }

    campo.addEventListener("keydown", (evento) => {
      if (["Enter", ","].includes(evento.key) || (evento.key === "Tab" && campo.value.trim())) {
        evento.preventDefault();
        adicionar(campo.value);
      } else if (evento.key === "Backspace" && !campo.value && lista.length) {
        lista.pop();
        desenhar();
        avisar();
      } else if (evento.key === "ArrowDown" && painel) {
        evento.preventDefault();
        const primeiro = painel.querySelector(".sh-lista-item");
        if (primeiro) primeiro.focus();
      }
    });
    campo.addEventListener("input", mostrarSugestoes);
    campo.addEventListener("paste", (evento) => {
      const texto = (evento.clipboardData || window.clipboardData).getData("text");
      if (/[,;\n]/.test(texto)) {
        evento.preventDefault();
        adicionar(texto);
      }
    });
    campo.addEventListener("blur", () => { if (campo.value.trim()) adicionar(campo.value); });
    caixa.addEventListener("click", (evento) => { if (evento.target === caixa) campo.focus(); });

    caixa.appendChild(campo);
    desenhar();
    return caixa;
  }

  window.StarHub.criarTags = criarTags;

  // Campo "tags" do Woo: [{"id", "name", "slug"}]. Tag que ja existia mantem
  // o id/slug; tag nova vai so com o nome.
  registrar("tags", ({ caixa, config, ler, escrever }) => {
    const originais = new Map();
    const nomes = ler([]).map((item) => {
      const objeto = typeof item === "object" && item ? item : { name: String(item) };
      originais.set(normalizar(objeto.name), objeto);
      return objeto.name;
    });
    caixa.appendChild(criarTags(nomes, {
      sugestoes: config.sugestoes || [],
      aoMudar: (lista) => escrever(config.simples ? lista
        : lista.map((nome) => originais.get(normalizar(nome)) || { name: nome })),
    }));
  });
})();
