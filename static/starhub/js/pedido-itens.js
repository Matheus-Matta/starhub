// O SKU do item e um snapshot da variante escolhida, nunca uma entrada manual.
(() => {
  "use strict";

  function ligar() {
    const $ = window.django && window.django.jQuery;
    if (!$) return;

    function campoSku(select) {
      const nome = select.name.replace(/-variante$/, "-sku");
      return select.form && select.form.elements.namedItem(nome);
    }

    function preencher(select, sku) {
      const campo = campoSku(select);
      if (!campo) return;
      campo.value = sku || "";
      campo.dispatchEvent(new Event("change", { bubbles: true }));
    }

    $(document).on("select2:select", 'select[name$="-variante"]', function (evento) {
      preencher(this, evento.params.data.sku);
    });

    $(document).on("select2:clear", 'select[name$="-variante"]', function () {
      preencher(this, "");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ligar, { once: true });
  } else {
    ligar();
  }
})();
