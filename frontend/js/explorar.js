// Exploração de ocorrências por distrito (UC08). Os registros aparecem como
// contagem e como taxa por 100 mil moradores; a cor do mapa é uma escala
// sequencial neutra, sem ranquear territórios (RNF18).

import { $, el, num, int, getJSON } from './util.js';
import { instalarBarraDeAcessibilidade, instalarAtalhos } from './acessibilidade.js';

// Cinco quintis de um só matiz: "menos" a "mais", sem associação com perigo.
const CORES = ['#eef4f4', '#cfe2e2', '#a8cbcc', '#7baeb0', '#4f8f92'];
const SEM_DADOS = '#e4e9eb';
const TRACO = '#425e68';
const TRACO_SELECIONADO = '#005fcc';

const mapa = L.map('map', { keyboard: true, scrollWheelZoom: true, minZoom: 10, maxZoom: 18 });
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap',
}).addTo(mapa);

let camadaDistritos = null;
let geometria = null;
let stats = [];
let selecionado = null;
let medida = 'taxa';

const ROTULOS = { taxa: 'Registros por 100 mil moradores', registros: 'Registros georreferenciados' };

function setStatus(mensagem, tipo = '') {
  $('status').textContent = mensagem;
  $('signal').className = `signal${tipo ? ` ${tipo}` : ''}`;
}

function valorDa(area) {
  if (medida !== 'taxa') return Number(area.registros) || 0;
  return area.taxa_100k == null ? null : Number(area.taxa_100k);
}

function currentParams() {
  const p = new URLSearchParams({ start: $('start').value, end: $('end').value });
  const postal = $('cep').value.replace(/\D/g, '');
  if (postal) p.set('cep', postal);
  if ($('category').value) p.set('category', $('category').value);
  return p;
}

function areaDe(feature) {
  const codigo = String(feature.properties.cd_distrito_municipal);
  return stats.find((a) => String(a.codigo) === codigo)
    || { codigo, distrito: feature.properties.nm_distrito_municipal, regiao: feature.properties.nm_regiao_05,
         registros: 0, populacao: null, taxa_100k: null };
}

/** Quintis da medida escolhida, entre os distritos que têm valor. */
function quebras() {
  const valores = stats.map(valorDa).filter((v) => v != null && v > 0).sort((a, b) => a - b);
  if (!valores.length) return [];
  return [0.2, 0.4, 0.6, 0.8].map((p) => valores[Math.max(0, Math.ceil(valores.length * p) - 1)]);
}

function corDe(area, breaks) {
  const valor = valorDa(area);
  if (valor == null) return SEM_DADOS;
  if (valor <= 0) return SEM_DADOS;
  if (!breaks.length) return CORES[0];
  const indice = breaks.findIndex((limite) => valor <= limite);
  return CORES[indice < 0 ? CORES.length - 1 : indice];
}

function estiloDe(feature) {
  const area = areaDe(feature);
  const selecionadoAqui = selecionado === String(area.codigo);
  return {
    color: selecionadoAqui ? TRACO_SELECIONADO : TRACO,
    weight: selecionadoAqui ? 3 : 1.15,
    opacity: .94,
    fillColor: corDe(area, quebras()),
    fillOpacity: (valorDa(area) || 0) > 0 ? .79 : .5,
  };
}

function popupDe(area) {
  const caixa = el('div', {}, el('div', { class: 'popup-title', text: area.distrito }));
  caixa.append(el('div', { class: 'popup-meta', text: `Região ${area.regiao || '—'}` }));
  caixa.append(el('div', { class: 'popup-count', text: `${int.format(area.registros)} registros` }));
  caixa.append(el('div', { class: 'popup-meta', text: area.taxa_100k == null
    ? 'sem população do distrito para calcular a taxa'
    : `${num.format(area.taxa_100k)} por 100 mil moradores` }));
  return caixa;
}

function rotuloDeZona(area) {
  const taxa = area.taxa_100k == null ? 'sem taxa' : `${num.format(area.taxa_100k)} por 100 mil moradores`;
  return `${area.distrito}: ${int.format(area.registros)} registros georreferenciados, ${taxa}`;
}

function atualizarEstilos() {
  if (!camadaDistritos) return;
  const breaks = quebras();
  camadaDistritos.eachLayer((layer) => {
    layer.setStyle(estiloDe(layer.feature));
    const area = areaDe(layer.feature);
    const elemento = layer.getElement();
    if (elemento) {
      elemento.setAttribute('aria-label', rotuloDeZona(area));
      const titulo = layer.getPopup();
      if (titulo) titulo.setContent(popupDe(area));
    }
  });
  desenharLegenda(breaks);
}

function desenharLegenda(breaks) {
  const rampa = $('legend-ramp');
  rampa.replaceChildren();
  $('legend-title').textContent = ROTULOS[medida];
  const nomeDaFaixa = (i) => (breaks[i] == null ? `Faixa ${i + 1}` : `Faixa ${i + 1}: até ${num.format(breaks[i])}`);
  const etiquetas = [['Sem registros ou sem população', SEM_DADOS], ...CORES.map((cor, i) => [nomeDaFaixa(i), cor])];
  for (const [rotulo, cor] of etiquetas) {
    // A legenda inteira é uma imagem descritiva; os chips só dão o tooltip visual.
    const chip = el('span', { class: 'legend-chip', title: rotulo, 'aria-hidden': 'true' });
    chip.style.backgroundColor = cor;
    rampa.append(chip);
  }
  document.querySelector('.map-legend').setAttribute('aria-label',
    `Legenda: ${ROTULOS[medida]}. Cinza: sem registros ou sem população. Do tom mais claro ao mais escuro, `
    + 'os quintis da cidade no período escolhido.');
}

function ligarDistrito(feature, layer) {
  layer.options.keyboard = true;
  layer.bindPopup(() => popupDe(areaDe(feature)), { autoPan: true });
  layer.on('click', () => {
    const area = areaDe(feature);
    selecionado = String(area.codigo);
    $('district-search').value = selecionado;
    atualizarEstilos();
    setStatus(`${rotuloDeZona(area)}.`, 'ok');
  });
  layer.on('add', () => {
    const elemento = layer.getElement();
    if (!elemento) return;
    elemento.setAttribute('tabindex', '0');
    elemento.setAttribute('role', 'button');
    elemento.setAttribute('aria-label', rotuloDeZona(areaDe(feature)));
    elemento.addEventListener('keydown', (evento) => {
      if (evento.key === 'Enter' || evento.key === ' ') {
        evento.preventDefault();
        layer.openPopup();
      }
    });
  });
}

function renderBarras(id, itens, rotulo, valor) {
  const raiz = $(id);
  // região rolável precisa ser alcançável pelo teclado (WCAG 2.1.1)
  raiz.setAttribute('tabindex', '0');
  raiz.setAttribute('role', 'region');
  raiz.replaceChildren();
  if (!itens.length) {
    raiz.append(el('p', { class: 'empty', text: 'Sem registros para os filtros escolhidos.' }));
    return;
  }
  const maximo = Math.max(1, ...itens.map((item) => Number(item[valor]) || 0));
  for (const item of itens) {
    const total = Number(item[valor]) || 0;
    const trilha = el('div', {
      class: 'bar-track', role: 'meter',
      'aria-label': `${item[rotulo]}: ${int.format(total)}`,
      'aria-valuemin': '0', 'aria-valuemax': String(maximo), 'aria-valuenow': String(total),
    });
    const enchimento = el('div', { class: 'bar-fill' });
    enchimento.style.width = `${Math.max(2, (100 * total) / maximo)}%`;
    trilha.append(enchimento);
    raiz.append(el('div', { class: 'bar-row' },
      el('span', { class: 'bar-name', text: item[rotulo] }),
      trilha,
      el('span', { class: 'bar-value', text: int.format(total) })));
  }
}

function renderResumo(dados) {
  $('total').textContent = int.format(dados.total);
  $('with-coords').textContent = int.format(dados.com_coordenada);
  $('with-cep').textContent = int.format(dados.com_cep);
  renderBarras('monthly', dados.mensal, 'mes', 'registros');
  renderBarras('categories', dados.categorias, 'label', 'registros');
}

// Tabela em ordem alfabética: a lista não é um ranking de "pior" a "melhor".
function renderTabela() {
  const corpo = $('area-table');
  corpo.replaceChildren();
  if (!stats.length) {
    corpo.append(el('tr', {}, Object.assign(el('td', { text: 'Nenhum distrito disponível.' }), { colSpan: 4 })));
    return;
  }
  const ordem = [...stats].sort((a, b) => a.distrito.localeCompare(b.distrito, 'pt-BR'));
  for (const area of ordem) {
    const acao = el('button', {
      type: 'button', text: area.distrito,
      'aria-label': `Localizar distrito ${area.distrito} no mapa`,
    });
    acao.addEventListener('click', () => focarDistrito(area.codigo));
    corpo.append(el('tr', {},
      el('th', { scope: 'row' }, acao),
      el('td', { class: 'num', text: int.format(area.registros) }),
      el('td', { class: 'num', text: area.populacao == null ? '—' : int.format(area.populacao) }),
      el('td', { class: 'num', text: area.taxa_100k == null ? '—' : num.format(area.taxa_100k) })));
  }
}

function renderDistritos() {
  if (!geometria) return;
  const seletor = $('district-search');
  const anterior = seletor.value;
  seletor.replaceChildren(new Option('Escolha um distrito no mapa', ''));
  for (const area of [...stats].sort((a, b) => a.distrito.localeCompare(b.distrito, 'pt-BR'))) {
    seletor.add(new Option(area.distrito, String(area.codigo)));
  }
  seletor.value = anterior;
  atualizarEstilos();
  renderTabela();
}

function focarDistrito(codigo) {
  if (!geometria || !camadaDistritos) return;
  const camada = camadaDistritos.getLayers()
    .find((l) => String(l.feature.properties.cd_distrito_municipal) === String(codigo));
  if (!camada) return;
  selecionado = String(codigo);
  mapa.fitBounds(camada.getBounds().pad(.12), { maxZoom: 14 });
  atualizarEstilos();
  camada.openPopup();
  setStatus(`${areaDe(camada.feature).distrito} selecionado.`, 'ok');
}

async function carregarGeometria() {
  geometria = await getJSON('/api/areas/geometry');
  camadaDistritos = L.geoJSON(geometria, { style: estiloDe, onEachFeature: ligarDistrito, keyboard: true }).addTo(mapa);
  const limites = camadaDistritos.getBounds();
  mapa.fitBounds(limites, { padding: [14, 14] });
  mapa.setMaxBounds(limites.pad(.05));
  $('district-count').textContent = `${geometria.features.length} distritos`;
}

async function atualizar() {
  const botao = $('apply');
  selecionado = null;
  $('district-search').value = '';
  botao.disabled = true;
  botao.textContent = 'Atualizando…';
  setStatus('Atualizando os dados para os filtros selecionados…');
  try {
    const parametros = currentParams();
    const [resumo, areas] = await Promise.all([
      getJSON(`/api/summary?${parametros}`),
      getJSON(`/api/areas?${parametros}`),
    ]);
    stats = areas.areas || [];
    renderResumo(resumo);
    renderDistritos();
    const semTaxa = stats.filter((a) => a.taxa_100k == null).length;
    setStatus(`${int.format(resumo.total)} registros encontrados.`
      + (areas.cep_distrito ? ` CEP associado a ${areas.cep_distrito.distrito} pela concentração histórica das coordenadas.` : '')
      + (semTaxa && medida === 'taxa' ? ` ${semTaxa} distrito(s) sem população calculada ficam em cinza.` : ''), 'ok');
  } catch (erro) {
    setStatus(erro.message, 'bad');
    $('total').textContent = '—';
    $('with-coords').textContent = '—';
    $('with-cep').textContent = '—';
  } finally {
    botao.disabled = false;
    botao.textContent = 'Aplicar filtros';
  }
}

async function iniciar() {
  try {
    const categorias = await getJSON('/api/categories');
    for (const categoria of categorias) $('category').add(new Option(categoria.label, categoria.value));
    await carregarGeometria();
  } catch (erro) {
    setStatus(`Não foi possível carregar os limites dos distritos: ${erro.message}`, 'bad');
    return;
  }
  try {
    const estado = await getJSON('/api/status');
    setStatus(estado.tem_registros ? 'Banco conectado · limites e registros prontos.' : 'Banco conectado, aguardando registros.', 'ok');
    await atualizar();
  } catch (erro) {
    setStatus(`Mapa dos distritos carregado. ${erro.message}`, 'bad');
  }
}

instalarBarraDeAcessibilidade({ anunciar: setStatus });
instalarAtalhos({ 1: '#conteudo', 2: '.top-nav', 3: '#consulta' });

$('apply').addEventListener('click', atualizar);
$('clear').addEventListener('click', () => {
  $('cep').value = '';
  $('start').value = '2025-01-01';
  $('end').value = '2026-12-31';
  $('category').value = '';
  $('district-search').value = '';
  selecionado = null;
  atualizar();
});
$('cep').addEventListener('input', (evento) => {
  const digitos = evento.target.value.replace(/\D/g, '').slice(0, 8);
  evento.target.value = digitos.length > 5 ? `${digitos.slice(0, 5)}-${digitos.slice(5)}` : digitos;
});
$('cep').addEventListener('keydown', (evento) => {
  if (evento.key === 'Enter') atualizar();
});
$('district-search').addEventListener('change', (evento) => {
  if (evento.target.value) focarDistrito(evento.target.value);
});
for (const radio of document.querySelectorAll('input[name=medida]')) {
  radio.addEventListener('change', () => {
    medida = radio.value;
    $('map-subtitle').textContent = medida === 'taxa'
      ? 'Cor pela taxa de registros por 100 mil moradores: compara distritos de tamanhos diferentes.'
      : 'Cor pela contagem de registros no período: números absolutos, sem pesar a população.';
    atualizarEstilos();
  });
}
$('fullscreen').addEventListener('click', async () => {
  const cartao = $('map').closest('.map-card');
  if (!document.fullscreenElement) {
    await cartao.requestFullscreen();
    $('fullscreen').textContent = 'Sair da tela cheia';
  } else {
    await document.exitFullscreen();
    $('fullscreen').textContent = 'Tela cheia';
  }
  setTimeout(() => mapa.invalidateSize(), 150);
});
window.addEventListener('resize', () => mapa.invalidateSize());
iniciar();
