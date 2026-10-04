// Barra de progresso da tarefa de integracao (templates/admin/integracoes/execucaointegracao).
// Um WebSocket so (/ws/tarefas/<id>/, apps/integracoes/consumers.py): o servidor empurra o
// andamento quando a tarefa grava, sem a tela perguntar. Usa o CeleryWebSocketProgressBar
// do celery_progress e acrescenta a reconexao (o servidor reiniciando derruba o socket).
// Quando a tarefa termina, recarrega a pagina: mensagem final, falhas e duracao vem do banco.
(() => {
  "use strict";
  const area = document.querySelector("[data-tarefa-progresso]");
  if (!area || typeof CeleryWebSocketProgressBar === "undefined") return;
  const barra = area.querySelector("[data-tarefa-barra]");
  const etapa = area.querySelector("[data-tarefa-etapa]");
  const percentual = area.querySelector("[data-tarefa-percentual]");
  const ESPERA_RECONEXAO = 3000;

  const mostrar = (_barra, _mensagem, progresso) => {
    const valor = Math.max(0, Math.min(100, Number(progresso.percent) || 0));
    barra.value = valor;
    barra.textContent = `${Math.round(valor)}%`;
    percentual.textContent = `${Math.round(valor)}%`;
    const contagem = progresso.total ? `${progresso.current} de ${progresso.total} · ` : "";
    const texto = progresso.description || (progresso.pending ? "Na fila, aguardando o worker" : "");
    etapa.textContent = contagem + texto;
  };
  const recarregar = () => window.setTimeout(() => window.location.reload(), 600);

  class BarraDaTarefa extends CeleryWebSocketProgressBar {
    async connect() {
      const protocolo = location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${protocolo}://${location.host}${this.progressUrl}`);
      let terminou = false;
      // Ao abrir (e a cada reconexao) pede o estado atual: o que andou com o socket fora.
      socket.onopen = () => socket.send(JSON.stringify({ type: "check_task_completion" }));
      socket.onmessage = (evento) => {
        let dados;
        try {
          dados = JSON.parse(evento.data);
        } catch (_erro) {
          return;
        }
        if (this.onData(dados) !== false) {
          terminou = true;
          socket.close();
        }
      };
      socket.onclose = (evento) => {
        if (terminou) return;
        if (evento.code === 4403) {
          etapa.textContent = "Sem permissao para acompanhar esta tarefa ao vivo. Recarregue a pagina.";
          return;
        }
        etapa.textContent = "Conexao perdida, reconectando...";
        window.setTimeout(() => this.connect(), ESPERA_RECONEXAO);
      };
    }
  }

  BarraDaTarefa.initProgressBar(area.dataset.tarefaProgresso, {
    progressBarElement: barra,
    progressBarMessageElement: etapa,
    onProgress: mostrar,
    onSuccess: recarregar,
    onTaskError: recarregar,
    onError: (_barra, _mensagem, erro) => {
      etapa.textContent = `Nao foi possivel atualizar o progresso (${erro || "erro"}). Recarregue a pagina.`;
    },
  });
})();
