// Imagens (variante: varias; categoria: uma). Miniaturas com texto alternativo,
// arrastar pela imagem (ou setas, pelo teclado) para reordenar: a primeira e a
// principal, a capa (na variante padrao, a capa do produto). Remover. Novas
// imagens: arrastar/soltar ou clicar (vao no <input type=file> e sobem ao
// salvar) ou colar uma URL.
(() => {
  "use strict";

  const { el, botao, registrar } = window.StarHub.json;

  registrar("imagens", ({ caixa, config, ler, escrever }) => {
    const multiplas = config.multiplas !== false;
    const inicial = ler(multiplas ? [] : null);
    const imagens = (Array.isArray(inicial) ? inicial : inicial ? [inicial] : [])
      .filter((item) => item && item.src);
    const arquivo = caixa.querySelector("input[data-arquivos]");
    let pendentes = [];
    let arrastando = null; // indice da imagem sendo arrastada para outra posicao

    const galeria = el("div", "sh-galeria");
    const avisar = () => escrever(multiplas ? imagens : imagens[0] || null);

    function sincronizarArquivos() {
      const transferencia = new DataTransfer();
      pendentes.forEach((item) => transferencia.items.add(item));
      arquivo.files = transferencia.files;
    }

    function cartao(src, legenda, acoes, extra) {
      const card = el("figure", "sh-imagem");
      const img = el("img");
      img.src = src;
      img.alt = "";
      img.loading = "lazy";
      const barra = el("div", "sh-imagem-acoes");
      acoes.forEach((acao) => barra.appendChild(acao));
      card.append(img, barra);
      if (legenda) card.appendChild(legenda);
      if (extra) card.appendChild(extra);
      return card;
    }

    function desenhar() {
      galeria.replaceChildren();
      imagens.forEach((imagem, indice) => {
        const acoes = [];
        if (multiplas && indice > 0) {
          acoes.push(botao("", "sh-imagem-botao", () => {
            imagens.splice(indice - 1, 0, imagens.splice(indice, 1)[0]);
            desenhar(); avisar();
          }, "chevron-left"));
        }
        if (multiplas && indice < imagens.length - 1) {
          acoes.push(botao("", "sh-imagem-botao", () => {
            imagens.splice(indice + 1, 0, imagens.splice(indice, 1)[0]);
            desenhar(); avisar();
          }, "chevron-right"));
        }
        acoes.push(botao("", "sh-imagem-botao sh-perigo", () => {
          imagens.splice(indice, 1);
          desenhar(); avisar();
        }, "x"));
        const alt = el("input");
        alt.type = "text";
        alt.placeholder = "Texto alternativo";
        alt.value = imagem.alt || "";
        alt.addEventListener("input", () => { imagem.alt = alt.value; avisar(); });
        const selo = multiplas && indice === 0 ? el("span", "badge badge-primary sh-principal", "Capa") : null;
        const card = cartao(imagem.src, alt, acoes, selo);
        if (multiplas) arrastavel(card, indice);
        galeria.appendChild(card);
      });
      pendentes.forEach((item, indice) => {
        const tirar = botao("", "sh-imagem-botao sh-perigo", () => {
          pendentes.splice(indice, 1);
          sincronizarArquivos(); desenhar();
        }, "x");
        const aviso = el("span", "sh-imagem-pendente", "Sobe ao salvar");
        galeria.appendChild(cartao(URL.createObjectURL(item), aviso, [tirar]));
      });
      zona.hidden = !multiplas && (imagens.length + pendentes.length) > 0;
    }

    // Arrasta pela imagem, nao pelo card: com o card inteiro arrastavel, selecionar
    // o texto alternativo com o mouse puxaria a imagem junto.
    function arrastavel(card, indice) {
      const alca = card.querySelector("img");
      alca.classList.add("sh-imagem-alca");
      alca.title = "Arraste para mudar a ordem";
      alca.addEventListener("pointerdown", () => { card.draggable = true; });
      card.addEventListener("dragstart", (evento) => {
        arrastando = indice;
        evento.dataTransfer.effectAllowed = "move";
        evento.dataTransfer.setData("text/plain", String(indice));
        card.classList.add("sh-imagem-movendo");
      });
      card.addEventListener("dragend", () => {
        card.draggable = false;
        arrastando = null;
        galeria.querySelectorAll(".sh-imagem").forEach((c) => c.classList.remove("sh-imagem-movendo", "sh-imagem-alvo"));
      });
      card.addEventListener("dragover", (evento) => {
        if (arrastando === null) return; // arquivo vindo de fora: e da zona de upload
        evento.preventDefault();
        card.classList.add("sh-imagem-alvo");
      });
      card.addEventListener("dragleave", () => card.classList.remove("sh-imagem-alvo"));
      card.addEventListener("drop", (evento) => {
        if (arrastando === null) return;
        evento.preventDefault();
        const origem = arrastando;
        arrastando = null;
        if (origem === indice) return;
        imagens.splice(indice, 0, imagens.splice(origem, 1)[0]);
        desenhar(); avisar();
      });
    }

    function receber(lista) {
      const aceitas = Array.from(lista).filter((item) => item.type.startsWith("image/"));
      if (!aceitas.length) return;
      if (!multiplas) {
        imagens.splice(0);
        avisar();
        pendentes = [aceitas[0]];
      } else {
        pendentes = pendentes.concat(aceitas);
      }
      sincronizarArquivos();
      desenhar();
    }

    const zona = el("div", "sh-zona-upload");
    zona.tabIndex = 0;
    zona.setAttribute("role", "button");
    zona.append(window.StarHub.icone("archive", "icon-lg"),
      el("strong", "", multiplas ? "Arraste imagens aqui" : "Arraste a imagem aqui"),
      el("span", "", "ou clique para escolher (PNG, JPG, GIF, WEBP ate 5 MB)"));
    zona.addEventListener("click", () => arquivo.click());
    zona.addEventListener("keydown", (evento) => {
      if (["Enter", " "].includes(evento.key)) { evento.preventDefault(); arquivo.click(); }
    });
    ["dragenter", "dragover"].forEach((tipo) => zona.addEventListener(tipo, (evento) => {
      evento.preventDefault();
      zona.classList.add("sh-arrastando");
    }));
    ["dragleave", "drop"].forEach((tipo) => zona.addEventListener(tipo, () => {
      zona.classList.remove("sh-arrastando");
    }));
    zona.addEventListener("drop", (evento) => {
      evento.preventDefault();
      receber(evento.dataTransfer.files);
    });
    // O input de arquivo e substituido pela lista "pendentes" a cada escolha.
    arquivo.addEventListener("change", () => {
      const escolhidos = Array.from(arquivo.files).filter((item) => !pendentes.includes(item));
      receber(escolhidos);
    });

    const porUrl = el("div", "sh-imagem-url");
    const url = el("input");
    url.type = "url";
    url.placeholder = "https://... (colar endereco de imagem)";
    const adicionarUrl = () => {
      const src = url.value.trim();
      if (!/^https?:\/\//i.test(src)) { url.focus(); return; }
      if (!multiplas) { imagens.splice(0); pendentes = []; sincronizarArquivos(); }
      imagens.push({ src, name: "", alt: "" });
      url.value = "";
      desenhar(); avisar();
    };
    url.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter") { evento.preventDefault(); adicionarUrl(); }
    });
    porUrl.append(url, botao("Adicionar URL", "btn btn-outline btn-sm", adicionarUrl, "plus"));

    caixa.append(galeria, zona, porUrl);
    desenhar();
  });
})();
