// Mesmo papel do admin/js/popup_response.js do Django: avisa a pagina de origem
// que o registro foi salvo, para ela selecionar no campo. Janela (window.open)
// fala com o opener; o modal do tema (iframe) fala com o parent.
"use strict";
{
  const dados = JSON.parse(
    document.getElementById("django-admin-popup-response-constants").dataset.popupResponse
  );
  const origem = window.opener || window.parent;
  switch (dados.action) {
    case "change":
      origem.dismissChangeRelatedObjectPopup(window, dados.value, dados.obj, dados.new_value);
      break;
    case "delete":
      origem.dismissDeleteRelatedObjectPopup(window, dados.value);
      break;
    default:
      origem.dismissAddRelatedObjectPopup(window, dados.value, dados.obj);
      break;
  }
}
