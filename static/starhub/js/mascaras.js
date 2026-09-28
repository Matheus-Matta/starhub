// Mascaras de digitacao: <input data-mascara="cep|cpf|cnpj|cpf-cnpj|telefone|uf|pais|moeda|digitos">.
// So ajudam a digitar e avisam ao sair do campo; quem valida de verdade e o
// servidor (o admin do Django usa novalidate). CPF/CNPJ chegam com pontos e o
// form grava so os digitos (CampoSoDigitos); o Address normaliza o CEP.
// Valor estrangeiro passa livre: CEP com letras e telefone com "+" nao mudam.
(() => {
  "use strict";

  const UFS = new Set(("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO").split(" "));
  const digitos = (valor) => valor.replace(/\D/g, "");
  const letras = (valor, tamanho) => valor.replace(/[^a-z]/gi, "").slice(0, tamanho).toUpperCase();

  // "0" do padrao e um digito; o resto e literal ("00000-000").
  function encaixar(numeros, padrao) {
    let saida = "";
    let i = 0;
    for (const simbolo of padrao) {
      if (i >= numeros.length) break;
      saida += simbolo === "0" ? numeros[i++] : simbolo;
    }
    return saida;
  }

  function digitoVerificador(numeros, pesos) {
    const soma = pesos.reduce((total, peso, i) => total + Number(numeros[i]) * peso, 0);
    const resto = soma % 11;
    return resto < 2 ? 0 : 11 - resto;
  }

  function cpfValido(numeros) {
    if (numeros.length !== 11 || /^(\d)\1+$/.test(numeros)) return false;
    const pesos = (inicio) => Array.from({ length: inicio - 1 }, (_, i) => inicio - i);
    return digitoVerificador(numeros, pesos(10)) === Number(numeros[9])
      && digitoVerificador(numeros, pesos(11)) === Number(numeros[10]);
  }

  function cnpjValido(numeros) {
    if (numeros.length !== 14 || /^(\d)\1+$/.test(numeros)) return false;
    const primeiro = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    return digitoVerificador(numeros, primeiro) === Number(numeros[12])
      && digitoVerificador(numeros, [6, ...primeiro]) === Number(numeros[13]);
  }

  const estrangeiro = (valor) => /[a-z]/i.test(valor);

  // formatar: aplicado a cada tecla. erro: mensagem ao sair do campo (ou "").
  const MASCARAS = {
    cep: {
      formatar: (v) => (estrangeiro(v) ? v : encaixar(digitos(v).slice(0, 8), "00000-000")),
      erro: (v) => (!estrangeiro(v) && digitos(v).length !== 8 ? "CEP incompleto: sao 8 digitos." : ""),
    },
    cpf: {
      formatar: (v) => encaixar(digitos(v).slice(0, 11), "000.000.000-00"),
      erro: (v) => (cpfValido(digitos(v)) ? "" : "CPF invalido."),
    },
    cnpj: {
      formatar: (v) => encaixar(digitos(v).slice(0, 14), "00.000.000/0000-00"),
      erro: (v) => (cnpjValido(digitos(v)) ? "" : "CNPJ invalido."),
    },
    "cpf-cnpj": {
      formatar: (v) => (digitos(v).length <= 11
        ? MASCARAS.cpf.formatar(v) : MASCARAS.cnpj.formatar(v)),
      erro: (v) => (digitos(v).length <= 11 ? MASCARAS.cpf.erro(v) : MASCARAS.cnpj.erro(v)),
    },
    telefone: {
      formatar: (v) => {
        if (v.trim().startsWith("+")) return v;
        const numeros = digitos(v).slice(0, 11);
        return encaixar(numeros, numeros.length > 10 ? "(00) 00000-0000" : "(00) 0000-0000");
      },
      erro: (v) => {
        const tamanho = digitos(v).length;
        return v.trim().startsWith("+") || tamanho === 10 || tamanho === 11
          ? "" : "Telefone incompleto: DDD + numero.";
      },
    },
    uf: { formatar: (v) => letras(v, 2), erro: (v) => (UFS.has(v) ? "" : "UF invalida.") },
    pais: { formatar: (v) => letras(v, 2), erro: (v) => (v.length === 2 ? "" : "Use 2 letras: BR.") },
    moeda: { formatar: (v) => letras(v, 3), erro: (v) => (v.length === 3 ? "" : "Use 3 letras: BRL.") },
    digitos: { formatar: (v) => digitos(v).slice(0, 14), erro: () => "" },
  };

  function avisar(campo, mensagem) {
    let aviso = campo.parentElement.querySelector(":scope > .sh-mascara-erro");
    if (mensagem) campo.setAttribute("aria-invalid", "true");
    else campo.removeAttribute("aria-invalid");
    if (!mensagem) {
      if (aviso) aviso.remove();
      return;
    }
    if (!aviso) {
      aviso = document.createElement("small");
      aviso.className = "sh-mascara-erro";
      campo.after(aviso);
    }
    aviso.textContent = mensagem;
  }

  function mascarar(campo, tipo) {
    const mascara = MASCARAS[tipo || campo.dataset.mascara];
    if (!mascara || campo.dataset.mascaraPronta) return;
    campo.dataset.mascaraPronta = "1";
    const aplicar = () => {
      const formatado = mascara.formatar(campo.value);
      if (formatado !== campo.value) campo.value = formatado;
    };
    campo.addEventListener("input", () => {
      aplicar();
      avisar(campo, "");
    });
    campo.addEventListener("blur", () => avisar(campo, campo.value ? mascara.erro(campo.value) : ""));
    aplicar();  // valor que veio do banco ("12345678909") ja aparece formatado
  }

  window.StarHub = Object.assign(window.StarHub || {}, { mascarar });

  window.StarHub.aoCarregar((raiz) => {
    raiz.querySelectorAll("input[data-mascara]").forEach((campo) => mascarar(campo));
  });
})();
