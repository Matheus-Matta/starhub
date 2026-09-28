// Calendario do tema, em pt-BR. So desenha e avisa a escolha; quem liga no
// campo e o datas.js. Modos: "unico" (1 mes) e "periodo" (2 meses, faixa).
(() => {
  "use strict";

  const { icone } = window.StarHub;
  const SEMANA = ["D", "S", "T", "Q", "Q", "S", "S"];
  const mesAno = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" });

  const semHora = (data) => new Date(data.getFullYear(), data.getMonth(), data.getDate());
  const mesmoDia = (a, b) => Boolean(a && b) && a.getTime() === b.getTime();

  function criar({ modo = "unico", inicio = null, fim = null, aoEscolher }) {
    const periodo = modo === "periodo";
    const hoje = semHora(new Date());
    let de = inicio ? semHora(inicio) : null;
    let ate = fim ? semHora(fim) : null;
    let passando = null; // dia sob o mouse, para mostrar a faixa antes do 2o clique
    let visivel = new Date((de || hoje).getFullYear(), (de || hoje).getMonth(), 1);

    const raiz = document.createElement("div");
    raiz.className = "sh-calendario";

    function botaoNav(nome, passo, oculto) {
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "sh-cal-nav";
      botao.hidden = oculto;
      botao.setAttribute("aria-label", passo < 0 ? "Mes anterior" : "Proximo mes");
      botao.appendChild(icone(nome, "icon-sm"));
      botao.addEventListener("click", () => {
        visivel = new Date(visivel.getFullYear(), visivel.getMonth() + passo, 1);
        desenhar();
      });
      return botao;
    }

    function classeDoDia(dia) {
      const classes = ["sh-cal-dia"];
      if (mesmoDia(dia, hoje)) classes.push("sh-hoje");
      const fimFaixa = ate || (periodo && de && passando) || null;
      if (mesmoDia(dia, de) || mesmoDia(dia, ate)) {
        classes.push("sh-escolhido");
      } else if (de && fimFaixa) {
        const [a, b] = de < fimFaixa ? [de, fimFaixa] : [fimFaixa, de];
        if (dia > a && dia < b) classes.push("sh-faixa");
      }
      return classes.join(" ");
    }

    function escolher(dia) {
      if (!periodo) {
        de = dia;
        aoEscolher(dia, null);
        return;
      }
      if (!de || ate) {
        de = dia;
        ate = null;
        desenhar();
        return;
      }
      [de, ate] = dia < de ? [dia, de] : [de, dia];
      desenhar();
      aoEscolher(de, ate);
    }

    function mes(primeiro, indice, total) {
      const bloco = document.createElement("div");
      const topo = document.createElement("div");
      topo.className = "sh-cal-topo";
      const titulo = document.createElement("span");
      titulo.textContent = mesAno.format(primeiro);
      topo.append(botaoNav("chevron-left", -1, indice > 0), titulo,
        botaoNav("chevron-right", 1, indice < total - 1));

      const grade = document.createElement("div");
      grade.className = "sh-cal-grade";
      SEMANA.forEach((letra) => {
        const celula = document.createElement("span");
        celula.className = "sh-cal-semana";
        celula.textContent = letra;
        grade.appendChild(celula);
      });
      for (let i = 0; i < primeiro.getDay(); i += 1) {
        const vazio = document.createElement("span");
        vazio.className = "sh-cal-dia sh-fora";
        grade.appendChild(vazio);
      }
      const dias = new Date(primeiro.getFullYear(), primeiro.getMonth() + 1, 0).getDate();
      for (let n = 1; n <= dias; n += 1) {
        const dia = new Date(primeiro.getFullYear(), primeiro.getMonth(), n);
        const botao = document.createElement("button");
        botao.type = "button";
        botao.className = classeDoDia(dia);
        botao.textContent = String(n);
        botao.addEventListener("click", () => escolher(dia));
        if (periodo) {
          botao.addEventListener("mouseenter", () => {
            if (de && !ate && !mesmoDia(passando, dia)) {
              passando = dia;
              desenhar();
            }
          });
        }
        grade.appendChild(botao);
      }
      bloco.append(topo, grade);
      return bloco;
    }

    function desenhar() {
      raiz.replaceChildren();
      const meses = document.createElement("div");
      meses.className = "sh-cal-meses";
      const total = periodo ? 2 : 1;
      for (let i = 0; i < total; i += 1) {
        meses.appendChild(mes(new Date(visivel.getFullYear(), visivel.getMonth() + i, 1), i, total));
      }
      const rodape = document.createElement("div");
      rodape.className = "sh-cal-rodape";
      const limpar = document.createElement("button");
      limpar.type = "button";
      limpar.className = "btn btn-ghost btn-sm";
      limpar.textContent = "Limpar";
      limpar.addEventListener("click", () => { de = null; ate = null; aoEscolher(null, null); });
      rodape.appendChild(limpar);
      if (!periodo) {
        const botaoHoje = document.createElement("button");
        botaoHoje.type = "button";
        botaoHoje.className = "btn btn-outline btn-sm";
        botaoHoje.textContent = "Hoje";
        botaoHoje.addEventListener("click", () => escolher(hoje));
        rodape.appendChild(botaoHoje);
      }
      raiz.append(meses, rodape);
    }

    desenhar();
    return raiz;
  }

  window.StarHub.calendario = criar;
})();
