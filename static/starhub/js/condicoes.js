// Mostra e esconde campos, secoes e inlines conforme o valor de outro campo.
// As regras vem do ModelAdmin (atributo `condicoes`, ver apps/core/admin_condicoes.py)
// num <script id="sh-condicoes" type="application/json"> do change_form.
//
// Exemplo: produto do tipo "Variavel" mostra os tipos de variante; "Bundle" mostra
// os componentes; switch "Controlar estoque" desligado esconde a quantidade.
// Nada muda no que e enviado: so a tela. Campo com erro nunca some.
(() => {
  "use strict";

  const dados = document.getElementById("sh-condicoes");
  const form = document.querySelector("#content-main form");
  if (!dados || !form) return;
  const config = JSON.parse(dados.textContent);
  const lista = (regra) => (Array.isArray(regra) ? regra : [regra]);

  function valorDe(controle) {
    if (controle.type === "checkbox") return controle.checked;
    if (controle.multiple) return [...controle.selectedOptions].map((opcao) => opcao.value);
    return (controle.value || "").trim();
  }

  function vale(regra, achar) {
    const controle = achar(regra.campo);
    if (!controle) return true; // campo so de leitura (sem input): nao decide nada
    const valor = valorDe(controle);
    if ("em" in regra) return regra.em.includes(valor);
    if ("marcado" in regra) return valor === regra.marcado;
    const preenchido = Array.isArray(valor) ? valor.length > 0 : valor !== "";
    return preenchido === regra.preenchido;
  }

  // Alvo "#id"/".classe" e seletor (inline, secao); o resto e nome de campo, e
  // some a celula dele (ou a linha inteira, se ele esta sozinho nela).
  function alvoDe(chave, achar, raiz) {
    if (/^[#.]/.test(chave)) return raiz.querySelector(chave);
    const campo = achar(chave);
    return campo ? campo.closest(".celula, td, .form-row") : null;
  }

  function mostrar(alvo, visivel) {
    if (!alvo) return;
    const comErro = alvo.querySelector(".errorlist li, .errors .errorlist");
    alvo.classList.toggle("sh-oculto", !visivel && !comErro);
    // Linha em que todas as celulas sumiram some junto: nao sobra um vao no form.
    const linha = alvo.closest(".form-row");
    if (linha && linha !== alvo) {
      const celulas = [...linha.querySelectorAll(".celula")];
      linha.classList.toggle(
        "sh-oculto", celulas.length > 0 && celulas.every((c) => c.classList.contains("sh-oculto"))
      );
    }
  }

  function aplicar(regras, achar, raiz) {
    Object.entries(regras).forEach(([chave, regra]) => {
      mostrar(alvoDe(chave, achar, raiz), lista(regra).some((item) => vale(item, achar)));
    });
  }

  // Data e hora do admin vem em dois inputs ("inicio_0", "inicio_1"): acha pelo primeiro.
  const pelaNome = (raiz, nome) => raiz.querySelector(`[name="${nome}"], [name="${nome}_0"]`);

  function aplicarTudo() {
    aplicar(config.form || {}, (nome) => pelaNome(form, nome), document);
    Object.entries(config.inlines || {}).forEach(([prefixo, regras]) => {
      document.querySelectorAll(`#${prefixo}-group [id^="${prefixo}-"]`).forEach((linha) => {
        const indice = linha.id.slice(prefixo.length + 1);
        if (!/^\d+$/.test(indice)) return; // "variantes-empty" e o molde de linha nova
        aplicar(regras, (nome) => pelaNome(linha, `${prefixo}-${indice}-${nome}`), linha);
      });
    });
  }

  form.addEventListener("change", aplicarTudo);
  form.addEventListener("input", aplicarTudo);
  document.addEventListener("formset:added", aplicarTudo);
  aplicarTudo();
})();
