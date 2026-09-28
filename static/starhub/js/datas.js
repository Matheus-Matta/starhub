// Liga o calendario nos campos:
//  - input[data-calendario]: data unica (dd/mm/aaaa), com botao de calendario;
//    com data-periodo-fim="<campo>" abre em PERIODO e preenche os dois campos;
//  - [data-filtro-periodo]: filtro "Periodo" da gaveta da listagem (ISO + envio).
// Digitar a data a mao continua valendo: o Django valida o texto como sempre.
(() => {
  "use strict";

  const { icone, aoCarregar, flutuante, calendario } = window.StarHub;
  const dois = (n) => String(n).padStart(2, "0");
  const paraTexto = (d) => (d ? `${dois(d.getDate())}/${dois(d.getMonth() + 1)}/${d.getFullYear()}` : "");
  const paraIso = (d) => (d ? `${d.getFullYear()}-${dois(d.getMonth() + 1)}-${dois(d.getDate())}` : "");

  function lerData(texto) {
    const br = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec((texto || "").trim());
    const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec((texto || "").trim());
    const partes = br ? [br[3], br[2], br[1]] : iso ? [iso[1], iso[2], iso[3]] : null;
    if (!partes) return null;
    const data = new Date(Number(partes[0]), Number(partes[1]) - 1, Number(partes[2]));
    return Number.isNaN(data.getTime()) ? null : data;
  }

  function definir(campo, data) {
    if (!campo) return;
    campo.value = paraTexto(data);
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // O campo final pode ser data simples ("fim") ou a parte data de um
  // data+hora do admin ("fim_0").
  function campoParceiro(campo, nome) {
    const form = campo.form || document;
    // Em inline o nome ganha prefixo ("variantes-0-"): o parceiro tem o mesmo.
    const corte = campo.name.lastIndexOf("-");
    const prefixo = corte >= 0 ? campo.name.slice(0, corte + 1) : "";
    const nomes = [...new Set([prefixo + nome, nome])];
    return form.querySelector(nomes.map((n) => `[name="${n}_0"], [name="${n}"]`).join(", "));
  }

  function abrirNoCampo(campo, ancora) {
    const fimNome = campo.dataset.periodoFim;
    const parceiro = fimNome ? campoParceiro(campo, fimNome) : null;
    let painel = null;
    const cal = calendario({
      modo: parceiro ? "periodo" : "unico",
      inicio: lerData(campo.value),
      fim: parceiro ? lerData(parceiro.value) : null,
      aoEscolher(de, ate) {
        definir(campo, de);
        if (parceiro) definir(parceiro, ate);
        if (!parceiro || !de || ate) flutuante.fechar(painel);
      },
    });
    painel = document.createElement("div");
    painel.appendChild(cal);
    flutuante.abrir(painel, ancora);
  }

  function montarCampo(campo) {
    campo.dataset.temaPronto = "1";
    campo.setAttribute("autocomplete", "off");
    const caixa = document.createElement("span");
    caixa.className = "sh-campo-data";
    campo.before(caixa);
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "sh-abrir-calendario";
    botao.setAttribute("aria-label", "Abrir calendario");
    botao.appendChild(icone("calendar", "icon-sm"));
    caixa.append(campo, botao);
    botao.addEventListener("click", () => abrirNoCampo(campo, caixa));
    campo.addEventListener("keydown", (evento) => {
      if (evento.key === "ArrowDown" && evento.altKey) {
        evento.preventDefault();
        abrirNoCampo(campo, caixa);
      }
    });
  }

  function montarFiltro(form) {
    form.dataset.temaPronto = "1";
    const de = form.querySelector("[data-periodo-de]");
    const ate = form.querySelector("[data-periodo-ate]");
    const gatilho = form.querySelector("[data-abrir-periodo]");
    const rotulo = gatilho.querySelector("span");
    const mostrar = () => {
      const a = lerData(de.value);
      const b = lerData(ate.value);
      rotulo.textContent = a || b ? `${paraTexto(a) || "..."} - ${paraTexto(b) || "..."}` : "Escolha o periodo";
      rotulo.classList.toggle("sh-vazio", !(a || b));
    };
    mostrar();
    gatilho.addEventListener("click", () => {
      let painel = null;
      const cal = calendario({
        modo: "periodo",
        inicio: lerData(de.value),
        fim: lerData(ate.value),
        aoEscolher(inicio, fim) {
          if (inicio && !fim) return;
          de.value = paraIso(inicio);
          ate.value = paraIso(fim);
          mostrar();
          flutuante.fechar(painel);
          form.submit();
        },
      });
      painel = document.createElement("div");
      painel.appendChild(cal);
      flutuante.abrir(painel, gatilho);
    });
  }

  aoCarregar((raiz) => {
    raiz.querySelectorAll("input[data-calendario]").forEach((campo) => {
      if (!campo.dataset.temaPronto && !campo.closest(".empty-form")) montarCampo(campo);
    });
    raiz.querySelectorAll("form[data-filtro-periodo]").forEach((form) => {
      if (!form.dataset.temaPronto) montarFiltro(form);
    });
  });
})();
