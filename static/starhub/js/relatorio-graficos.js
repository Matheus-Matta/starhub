// Graficos do relatorio (templates/admin/relatorio.html) com o Chart.js.
// Os dados vem prontos do servidor (#relatorio-graficos, apps/core/relatorios/graficos.py):
// {titulo, tipo: "barra" | "linha" | "rosca", rotulos, moeda, series: [{nome, dados}]}.
// Dinheiro chega em texto ("200.00"): aqui so vira numero para desenhar. As cores
// saem dos tokens do tema; trocar claro/escuro redesenha.
(function () {
  const fonte = document.getElementById("relatorio-graficos");
  if (!fonte || typeof Chart === "undefined") return;
  const graficos = JSON.parse(fonte.textContent);
  const reais = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const inteiro = new Intl.NumberFormat("pt-BR");
  const TIPOS = { barra: "bar", linha: "line", rosca: "doughnut" };
  // Uma cor por fatia da rosca; com 7 status, 5 tons repetiam a cor de duas fatias.
  const TONS = ["--primary", "--success", "--warning", "--info", "--destructive",
                "--secondary-foreground", "--muted-foreground", "--mono"];
  let desenhados = [];

  function cor(token) {
    return getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  }

  function formatar(valor, moeda) {
    return moeda ? reais.format(valor) : inteiro.format(valor);
  }

  function conjunto(grafico, serie) {
    const dados = serie.dados.map(Number);
    if (grafico.tipo === "rosca") {
      const cores = dados.map((_, i) => cor(TONS[i % TONS.length]));
      return { label: serie.nome, data: dados, backgroundColor: cores,
               borderColor: cor("--background"), borderWidth: 2 };
    }
    const primaria = cor("--primary");
    return { label: serie.nome, data: dados, borderColor: primaria, backgroundColor: primaria,
             // Linha reta: a curva suavizada desenhava valor que nao existe entre dois dias.
             borderRadius: 4, tension: 0, pointRadius: 2, fill: false };
  }

  function opcoes(grafico) {
    const texto = cor("--muted-foreground");
    const linha = cor("--border");
    const rotulo = (ctx) => `${ctx.dataset.label}: ${formatar(ctx.parsed.y ?? ctx.parsed, grafico.moeda)}`;
    const base = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: grafico.tipo === "rosca", position: "bottom",
                  labels: { color: texto, boxWidth: 10 } },
        tooltip: { callbacks: { label: rotulo } },
      },
    };
    if (grafico.tipo === "rosca") return base;
    base.scales = {
      x: { ticks: { color: texto, maxRotation: 0, autoSkip: true }, grid: { display: false } },
      y: { beginAtZero: true, grid: { color: linha },
           ticks: { color: texto, precision: 0,
                    callback: (valor) => formatar(valor, grafico.moeda) } },
    };
    return base;
  }

  function desenhar() {
    desenhados.forEach((grafico) => grafico.destroy());
    desenhados = [];
    document.querySelectorAll("canvas[data-grafico]").forEach((tela) => {
      const grafico = graficos[Number(tela.dataset.grafico)];
      if (!grafico) return;
      desenhados.push(new Chart(tela, {
        type: TIPOS[grafico.tipo] || "bar",
        data: { labels: grafico.rotulos,
                datasets: grafico.series.map((serie) => conjunto(grafico, serie)) },
        options: opcoes(grafico),
      }));
    });
  }

  desenhar();
  // O botao de tema troca o data-theme do <html>; o "automatico" segue o sistema.
  new MutationObserver(desenhar).observe(document.documentElement,
    { attributes: true, attributeFilter: ["data-theme"] });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", desenhar);
})();
