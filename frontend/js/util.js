// Utilidades compartilhadas das telas do GeoHabita (script web: JavaScript puro,
// sem framework de build). Nada aqui depende do Leaflet.

export const $ = (id) => document.getElementById(id);

export const num = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
export const int = new Intl.NumberFormat('pt-BR');

const PROPRIEDADES_DE_ATTR = new Set(['role', 'scope', 'tabindex']);

/** Cria um elemento: `{class, text, html, htmlFor, ...}` e atributos `aria-*`. */
export function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'htmlFor') node.htmlFor = value;
    else if (key.startsWith('aria-') || PROPRIEDADES_DE_ATTR.has(key)) node.setAttribute(key, value);
    else node[key] = value;
  }
  node.append(...kids.filter((kid) => kid != null));
  return node;
}

/** Cor de uma categoria, lida do CSS: fonte única, acompanha o alto contraste. */
export function corCss(variavel) {
  return getComputedStyle(document.documentElement).getPropertyValue(variavel).trim();
}

export const distancia = (metros) => metros == null ? '—'
  : metros < 1000 ? `${int.format(Math.round(metros))} m` : `${num.format(metros / 1000)} km`;

export const minutos = (metros, velocidadeMMin = 80) => metros == null ? '—'
  : `${int.format(Math.ceil(metros / velocidadeMMin))} min`;

/** JSON de uma rota da API; erros HTTP viram mensagem legível para a região viva. */
export async function getJSON(url) {
  const response = await fetch(url);
  let data = {};
  try {
    data = await response.json();
  } catch {
    /* resposta sem corpo JSON: usa o código HTTP */
  }
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? 'Parâmetro inválido.' : data.detail;
    throw new Error(detail || `Não foi possível consultar o serviço (HTTP ${response.status}).`);
  }
  return data;
}

/** Escreve no histórico do navegador sem recarregar a página (RF17). */
export function atualizarUrl(parametros) {
  const query = new URLSearchParams();
  for (const [chave, valor] of Object.entries(parametros)) if (valor) query.set(chave, valor);
  const novos = query.toString();
  history.replaceState(null, '', novos ? `?${novos}` : location.pathname);
}
