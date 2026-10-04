// Listas com botoes que abrem o formulario do filho num modal (ex.: variantes na
// pagina do produto). Contrato dos atributos em apps/core/admin_lista_modal.py.
//
// Salvou no modal: a lista precisa mostrar o que mudou. Se nada foi mexido no
// form do pai, so recarrega; se foi, salva o pai com "Salvar e continuar", para o
// que foi digitado nao se perder.
(() => {
  "use strict";

  const form = document.querySelector("#content-main form");
  if (!form || !window.StarHub || !window.StarHub.abrirModal) return;
  const GATILHO = "[data-modal-url], [data-modal-salvar-antes]";

  // Retrato do form depois que os widgets montaram (load): comparar diz se houve edicao.
  const retrato = () => new URLSearchParams(new FormData(form)).toString();
  let inicial = null;

  function enviarPai(extras) {
    Object.entries(extras).forEach(([nome, valor]) => {
      const campo = document.createElement("input");
      campo.type = "hidden";
      campo.name = nome;
      campo.value = valor;
      form.appendChild(campo);
    });
    form.requestSubmit();
  }

  function mostrarOQueMudou() {
    if (inicial !== null && retrato() === inicial) {
      // GET de novo (e nao reload): se a pagina veio de um POST, nao reenvia o form.
      window.location.assign(window.location.href);
      return;
    }
    enviarPai({ _continue: "1" });
  }

  function abrir(gatilho) {
    const alterado = inicial !== null && retrato() !== inicial;
    // Botao com chave ("+ Adicionar variante") e pai alterado sem salvar (ex.: tipo
    // trocado para Variavel): salva antes, senao o filho seria validado contra o
    // pai antigo. Na volta a chave abre o modal sozinha.
    if (gatilho.hasAttribute("data-modal-salvar-antes") || (alterado && gatilho.dataset.modalChave)) {
      enviarPai({ _continue: "1", _abrir_modal: gatilho.dataset.modalChave || "" });
      return;
    }
    window.StarHub.abrirModal({
      url: gatilho.dataset.modalUrl,
      titulo: gatilho.dataset.modalTitulo || "Editar",
      nome: `lista-${gatilho.dataset.modalChave || "item"}__1`,
      aoSalvar: mostrarOQueMudou,
    });
  }

  // Clique na linha ou no botao (o mais proximo ganha: "Excluir" dentro da linha).
  form.addEventListener("click", (evento) => {
    const gatilho = evento.target.closest(GATILHO);
    if (!gatilho) return;
    evento.preventDefault();
    abrir(gatilho);
  });
  // Linha da lista com foco (Tab): Enter abre, como o clique.
  form.addEventListener("keydown", (evento) => {
    const gatilho = evento.target.matches && evento.target.matches(`tr${GATILHO.split(",")[0]}`);
    if (gatilho && evento.key === "Enter") {
      evento.preventDefault();
      abrir(evento.target);
    }
  });

  window.addEventListener("load", () => {
    inicial = retrato();
    // Veio da criacao pelo botao "salvar antes": abre o modal da chave e limpa a URL
    // (senao um F5 abriria de novo).
    const endereco = new URL(window.location.href);
    const chave = endereco.searchParams.get("abrir_modal");
    const gatilho = chave && form.querySelector(`[data-modal-chave="${CSS.escape(chave)}"][data-modal-url]`);
    if (chave) {
      endereco.searchParams.delete("abrir_modal");
      window.history.replaceState(null, "", endereco.href);
    }
    if (gatilho) abrir(gatilho);
  });
})();
