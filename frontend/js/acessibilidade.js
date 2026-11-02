// Controles de acessibilidade fixos (e-MAG / WCAG 2.1): alto contraste, tamanho
// de fonte e atalhos de teclado. As preferências ficam no localStorage do próprio
// navegador — nada é enviado ao servidor (RNF15).

import { $ } from './util.js';

const CHAVES = { contraste: 'geohabita.altoContraste', fonte: 'geohabita.fonte' };
const FONTES = [87.5, 100, 112.5, 125, 150];
const PADRAO = 1; // índice da fonte padrão (100%)

const raiz = document.documentElement;

function salvar(chave, valor) {
  try {
    localStorage.setItem(chave, String(valor));
  } catch {
    /* navegador em modo privado: a preferência vale só para a visita */
  }
}

function ler(chave, padrao) {
  try {
    const valor = localStorage.getItem(chave);
    return valor == null ? padrao : valor;
  } catch {
    return padrao;
  }
}

function pressionado(botao, ligado) {
  if (botao) botao.setAttribute('aria-pressed', String(ligado));
}

export function aplicarContraste(ligado) {
  raiz.classList.toggle('alto-contraste', ligado);
  pressionado($('btn-contraste'), ligado);
  salvar(CHAVES.contraste, ligado ? '1' : '0');
  return ligado;
}

export function aplicarFonte(indice) {
  const i = Math.max(0, Math.min(FONTES.length - 1, indice));
  raiz.style.setProperty('--fonte-base', `${FONTES[i]}%`);
  pressionado($('btn-fonte-padro'), i === PADRAO);
  salvar(CHAVES.fonte, String(i));
  return i;
}

function botao(id, rotulo, acao, pressionadoInicial) {
  const elemento = document.createElement('button');
  elemento.type = 'button';
  elemento.id = id;
  elemento.textContent = rotulo;
  if (pressionadoInicial) elemento.setAttribute('aria-pressed', String(pressionadoInicial()));
  elemento.addEventListener('click', () => {
    acao();
    if (pressionadoInicial) elemento.setAttribute('aria-pressed', String(pressionadoInicial()));
  });
  return elemento;
}

function grupo(legenda, ...botoes) {
  const fieldset = document.createElement('fieldset');
  const titulo = document.createElement('legend');
  titulo.textContent = legenda;
  fieldset.append(titulo, ...botoes);
  return fieldset;
}

const indiceSalvo = () => Number(ler(CHAVES.fonte, String(PADRAO)));
const contrasteLigado = () => raiz.classList.contains('alto-contraste');

/** Monta a barra de controles de acessibilidade e aplica as preferências salvas. */
export function instalarBarraDeAcessibilidade({ anunciar = () => {} } = {}) {
  const alvo = $('acessibilidade');
  if (!alvo) return;

  alvo.append(
    grupo('Contraste', botao('btn-contraste', 'Alto contraste', () => {
      anunciar(aplicarContraste(!contrasteLigado()) ? 'Alto contraste ligado.' : 'Contraste normal.');
    }, contrasteLigado)),
    grupo('Tamanho da fonte',
      botao('btn-fonte-menor', 'A−', () => anunciar(`Fonte ${Math.round(FONTES[ajustarFonte(-1)])}%.`)),
      botao('btn-fonte-padro', 'A', () => {
        aplicarFonte(PADRAO);
        anunciar('Fonte no tamanho padrão.');
      }, () => indiceSalvo() === PADRAO),
      botao('btn-fonte-maior', 'A+', () => anunciar(`Fonte ${Math.round(FONTES[ajustarFonte(1)])}%.`))),
  );

  aplicarContraste(ler(CHAVES.contraste, '0') === '1');
  aplicarFonte(indiceSalvo());

  function ajustarFonte(passo) {
    return aplicarFonte(indiceSalvo() + passo);
  }
}

/** Alt+1 conteúdo, Alt+2 menu, Alt+3 consulta, Alt+4 mapa (padrão e-MAG). */
export function instalarAtalhos(atalhos = { 1: '#conteudo', 2: '.top-nav', 3: '#consulta', 4: '#mapa' }) {
  document.addEventListener('keydown', (evento) => {
    if (!evento.altKey || evento.ctrlKey || evento.metaKey || evento.shiftKey) return;
    const seletor = atalhos[evento.key];
    if (!seletor) return;
    const alvo = document.querySelector(seletor);
    if (!alvo) return;
    evento.preventDefault();
    alvo.scrollIntoView({ block: 'start' });
    (alvo.querySelector('input, button, [tabindex]') || alvo).focus({ preventScroll: true });
  });
}
