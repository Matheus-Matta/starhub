// Dialogo de confirmacao (templates/components/confirmar.html): botao submit com
// data-confirmar="texto" so envia depois do Confirmar. Usado em acao que altera a loja
// real (cadastrar frete, webhooks, retomar envio): um clique por engano nao pode escrever la.
(() => {
  "use strict";
  const dialogo = document.getElementById("sh-confirmar");
  if (!dialogo || typeof dialogo.showModal !== "function") return;
  const titulo = dialogo.querySelector("[data-confirmar-titulo]");
  const texto = dialogo.querySelector("[data-confirmar-texto]");
  const ok = dialogo.querySelector("[data-confirmar-ok]");
  const lista = dialogo.querySelector("[data-confirmar-itens]");

  // data-confirmar-lista="id": frases de um json_script da pagina (ex.: o que falta).
  const preencherLista = (idDados) => {
    const fonte = idDados && document.getElementById(idDados);
    const itens = fonte ? JSON.parse(fonte.textContent || "[]") : [];
    lista.replaceChildren(...itens.map((frase) => {
      const item = document.createElement("li");
      item.textContent = frase;
      return item;
    }));
    lista.hidden = itens.length === 0;
  };
  let pendente = null;

  document.addEventListener("click", (evento) => {
    const botao = evento.target.closest("button[data-confirmar]");
    if (!botao || !botao.form || botao.dataset.confirmado === "1") return;
    evento.preventDefault();
    pendente = botao;
    titulo.textContent = botao.dataset.confirmarTitulo || "Confirmar acao";
    texto.textContent = botao.dataset.confirmar;
    preencherLista(botao.dataset.confirmarLista);
    ok.textContent = botao.dataset.confirmarBotao || "Confirmar";
    ok.classList.toggle("btn-destructive", "confirmarPerigo" in botao.dataset);
    ok.classList.toggle("btn-primary", !("confirmarPerigo" in botao.dataset));
    dialogo.showModal();
    ok.focus();
  });

  ok.addEventListener("click", () => {
    const botao = pendente;
    dialogo.close();
    if (!botao) return;
    // requestSubmit(botao) manda o name/value do botao (ex.: acao=frete), como o clique.
    botao.dataset.confirmado = "1";
    botao.form.requestSubmit(botao);
    delete botao.dataset.confirmado;
  });

  dialogo.querySelector("[data-confirmar-cancelar]").addEventListener("click", () => {
    pendente = null;
    dialogo.close();
  });
  dialogo.addEventListener("close", () => { pendente = null; });
})();
