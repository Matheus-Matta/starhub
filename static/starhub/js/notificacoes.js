// Sino do cabecalho: o servidor empurra o aviso novo pelo WebSocket /ws/notificacoes/
// (apps/notificacoes/consumers.py). Aqui so se poe o aviso no topo da lista, soma no
// contador e mostra um aviso rapido na tela. Caiu a conexao: tenta de novo com espera.
(function () {
  "use strict";

  var raiz = document.querySelector("[data-notificacoes]");
  if (!raiz || !window.WebSocket) {
    return;
  }
  var contador = raiz.querySelector("[data-notificacoes-contador]");
  var lista = raiz.querySelector("[data-notificacoes-lista]");
  var espera = 2000;

  function texto(tag, classe, valor) {
    var elemento = document.createElement(tag);
    if (classe) {
      elemento.className = classe;
    }
    elemento.textContent = valor;
    return elemento;
  }

  function somar() {
    contador.textContent = String((parseInt(contador.textContent, 10) || 0) + 1);
    contador.hidden = false;
  }

  function colocarNaLista(aviso) {
    var vazio = lista.querySelector("[data-notificacoes-vazio]");
    if (vazio) {
      vazio.remove();
    }
    var item = document.createElement("li");
    item.className = "notificacao notificacao-nova";
    var link = document.createElement("a");
    link.className = "notificacao-link";
    link.href = aviso.link || "#";
    link.appendChild(texto("strong", "", aviso.titulo));
    if (aviso.mensagem) {
      link.appendChild(texto("span", "notificacao-texto", aviso.mensagem));
    }
    link.appendChild(texto("span", "notificacao-quando", aviso.criada_em));
    item.appendChild(link);
    lista.insertBefore(item, lista.firstChild);
  }

  function avisoRapido(aviso) {
    var caixa = texto("div", "notificacao-toast", "");
    caixa.setAttribute("role", "status");
    caixa.appendChild(texto("strong", "", aviso.titulo));
    if (aviso.mensagem) {
      caixa.appendChild(texto("span", "", aviso.mensagem));
    }
    document.body.appendChild(caixa);
    setTimeout(function () { caixa.remove(); }, 6000);
  }

  function conectar() {
    var protocolo = location.protocol === "https:" ? "wss://" : "ws://";
    var socket = new WebSocket(protocolo + location.host + raiz.dataset.notificacoes);
    socket.onopen = function () { espera = 2000; };
    socket.onmessage = function (evento) {
      var aviso = JSON.parse(evento.data);
      colocarNaLista(aviso);
      somar();
      avisoRapido(aviso);
    };
    socket.onclose = function (evento) {
      if (evento.code === 4401) {
        return;  // sem login: nao adianta tentar de novo
      }
      setTimeout(conectar, espera);
      espera = Math.min(espera * 2, 60000);
    };
  }

  conectar();
})();
