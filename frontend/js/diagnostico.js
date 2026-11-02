// Tela de diagnóstico do endereço (UC01 a UC04). JavaScript da página, servido
// como estático; o Leaflet continua global (variável L).

import { $, el, num, int, distancia, minutos, getJSON, corCss } from './util.js';

const CATEGORIAS = {
  lazer_convivencia: ['Lazer e convivência', '--c-lazer'],
  cultura_esporte: ['Cultura e esporte', '--c-cultura'],
  mobilidade: ['Mobilidade', '--c-mobilidade'],
  comercio_rua: ['Comércio de rua', '--c-comercio'],
  servicos_essenciais: ['Serviços essenciais', '--c-servicos'],
  conectividade: ['Conectividade', '--c-conectividade'],
};

const TIPOS = {
  praca: 'Praça',
  parque_area_verde: 'Parque ou área verde',
  biblioteca_centro_cultural: 'Biblioteca ou centro cultural',
  ceu_equipamento_esportivo: 'CEU ou equipamento esportivo',
  ponto_onibus: 'Ponto de ônibus',
  estacao_metro_trem: 'Estação de metrô ou trem',
  ciclovia: 'Ciclovia',
  feira_mercado_municipal: 'Feira livre ou mercado',
  unidade_basica_saude: 'Unidade básica de saúde',
  escola_publica: 'Escola pública',
  iluminacao_publica: 'Iluminação pública',
  wifi_publico: 'Wi-Fi público',
};

const TENDENCIA = {
  alta: 'Em alta no período',
  queda: 'Em queda no período',
  estável: 'Estável no período',
};

const state = { lat: null, lon: null, endereco: null, distrito: null, origem: null, dados: null, pedido: 0 };

const cor = (categoria) => corCss(CATEGORIAS[categoria][1]);

// ---------- utilidades ----------
function anunciar(mensagem, erro = false) {
  const status = $('status');
  status.textContent = mensagem;
  status.classList.toggle('erro', erro);
}

function pesos() {
  const p = {};
  for (const categoria of Object.keys(CATEGORIAS)) p[`peso_${categoria}`] = $(`peso-${categoria}`).value;
  return p;
}

function barra(rotulo, valor, { mediana = null, corDaBarra = null, sufixo = '' } = {}) {
  const pct = valor == null ? 0 : Math.max(0, Math.min(100, valor));
  const fill = el('div', { class: 'fill' });
  fill.style.width = `${pct}%`;
  if (corDaBarra) fill.style.background = corDaBarra;
  const track = el('div', {
    class: 'track',
    role: 'img',
    'aria-label': `${rotulo}: ${valor == null ? 'sem dados' : `${num.format(valor)} de 100`}`,
  }, fill);
  if (mediana != null) {
    const marca = el('div', { class: 'median' });
    marca.style.left = `${mediana}%`;
    track.append(marca);
  }
  return el('li', { class: 'bar' },
    el('span', { text: rotulo }),
    track,
    el('span', { class: 'value', text: valor == null ? '—' : num.format(valor) + sufixo }));
}

// ---------- pesos (RF09) ----------
for (const [categoria, [rotulo]] of Object.entries(CATEGORIAS)) {
  const sel = el('select', { id: `peso-${categoria}` });
  for (let i = 0; i <= 5; i++) {
    sel.add(new Option(i === 0 ? '0 · não importa' : i === 5 ? '5 · muito importante' : String(i), String(i), i === 1, i === 1));
  }
  sel.addEventListener('change', recalcular);
  $('pesos').append(el('label', { htmlFor: `peso-${categoria}` }, rotulo, sel));
}

let espera = null;
function recalcular() {
  clearTimeout(espera);
  if (state.lat == null) return;
  espera = setTimeout(() => diagnosticar({ lat: state.lat, lon: state.lon }, true), 250);
}

// ---------- abas (padrão WAI-ARIA) ----------
const abas = [...document.querySelectorAll('[role=tab]')];

function abrirAba(aba, foco = true) {
  for (const a of abas) {
    const selecionada = a === aba;
    a.setAttribute('aria-selected', String(selecionada));
    a.tabIndex = selecionada ? 0 : -1;
    $(a.getAttribute('aria-controls')).hidden = !selecionada;
  }
  if (foco) aba.focus();
  if (aba.id === 'aba-proximidade') setTimeout(() => mapa.invalidateSize(), 50);
}

abas.forEach((aba, i) => {
  aba.addEventListener('click', () => abrirAba(aba));
  aba.addEventListener('keydown', (evento) => {
    const destino = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: abas.length - 1 }[evento.key];
    if (destino != null) {
      evento.preventDefault();
      abrirAba(abas[(destino + abas.length) % abas.length]);
    }
  });
});

// ---------- mapa (RF13) ----------
const mapa = L.map('map', { keyboard: true, minZoom: 10, maxZoom: 18 }).setView([-23.55, -46.63], 11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap',
}).addTo(mapa);

const camadas = { base: L.layerGroup().addTo(mapa), categorias: {} };
for (const [categoria, [rotulo]] of Object.entries(CATEGORIAS)) {
  camadas.categorias[categoria] = L.layerGroup().addTo(mapa);
  const cb = el('input', { type: 'checkbox', checked: true, id: `f-${categoria}` });
  cb.addEventListener('change', () => (cb.checked ? camadas.categorias[categoria].addTo(mapa) : camadas.categorias[categoria].remove()));
  const swatch = el('span', { class: 'swatch', 'aria-hidden': 'true' });
  swatch.style.background = cor(categoria);
  $('filtros').append(el('label', { htmlFor: `f-${categoria}` }, cb, swatch, rotulo));
}

mapa.on('click', (evento) => {
  if (state.lat == null) return;
  state.endereco = null;
  diagnosticar({ lat: evento.latlng.lat, lon: evento.latlng.lng });
});

const limites = {};

async function desenharMapa(d) {
  mapa.invalidateSize();
  camadas.base.clearLayers();
  for (const grupo of Object.values(camadas.categorias)) grupo.clearLayers();
  const ponto = [state.lat, state.lon];
  L.marker(ponto, { title: 'Ponto consultado', alt: 'Ponto consultado', keyboard: true })
    .bindPopup(state.endereco ? (state.endereco.logradouro || `CEP ${state.endereco.cep}`) : 'Ponto escolhido no mapa')
    .addTo(camadas.base);
  for (const raio of [500, 1000]) {
    L.circle(ponto, { radius: raio, color: '#21424f', weight: 1.5, dashArray: '6 6', fill: false, interactive: false })
      .addTo(camadas.base);
  }
  for (const [categoria, itens] of Object.entries(d.proximidade.entorno)) {
    for (const item of itens) {
      if (item.latitude == null) continue;
      const marcador = L.circleMarker([item.latitude, item.longitude], {
        radius: 6, color: '#fff', weight: 1.5, fillColor: cor(categoria), fillOpacity: .95,
      });
      marcador.bindPopup(el('div', {},
        el('div', { class: 'popup-title', text: item.nome }),
        el('div', { text: `${TIPOS[item.tipo]} · ${distancia(item.distancia_m)} em linha reta` })));
      marcador.addTo(camadas.categorias[categoria]);
    }
  }
  const codigo = state.distrito.codigo;
  try {
    limites[codigo] = limites[codigo] || await getJSON(`/api/distritos/${encodeURIComponent(codigo)}/limite`);
    L.geoJSON(limites[codigo], { style: { color: '#21424f', weight: 2, fill: false }, interactive: false }).addTo(camadas.base);
  } catch {
    /* sem limite do distrito: o mapa segue com o ponto e os equipamentos */
  }
  mapa.invalidateSize();
  mapa.fitBounds(L.latLng(ponto).toBounds(2300));
}

// ---------- renderização ----------
function linhaVazia(tbody, colunas, texto) {
  tbody.replaceChildren(el('tr', {}, el('td', { colSpan: colunas, text: texto })));
}

function renderProximidade(p) {
  $('ipl').textContent = p.ipl == null ? '—' : num.format(p.ipl);
  const ul = $('ipl-categorias');
  ul.replaceChildren();
  for (const [categoria, info] of Object.entries(p.categorias)) {
    const item = barra(CATEGORIAS[categoria][0], info.nota, { corDaBarra: cor(categoria) });
    if (info.nota == null) item.querySelector('.value').title = 'sem dados na fonte';
    ul.append(item);
  }
  const tabela = $('tipos');
  tabela.replaceChildren();
  for (const [tipo, info] of Object.entries(p.tipos)) {
    const nome = info.disponivel
      ? (info.pontos_no_raio != null
        ? `${int.format(info.pontos_no_raio)} pontos · ${int.format(info.densidade_km2)}/km²`
        : (info.nome || '—'))
      : el('span', { class: 'muted', text: 'sem dados na fonte' });
    tabela.append(el('tr', {},
      el('th', { scope: 'row', text: TIPOS[tipo] }),
      el('td', {}, nome, info.aviso && info.disponivel ? el('div', { class: 'muted', text: info.aviso }) : null),
      el('td', { class: 'num', text: info.pontos_no_raio != null ? '—' : distancia(info.distancia_m) }),
      el('td', { class: 'num', text: info.tempo_caminhada_min == null ? '—' : `${info.tempo_caminhada_min} min` }),
      el('td', { class: 'num', text: info.nota == null ? '—' : num.format(info.nota) }),
      el('td', { class: 'num', text: info.ate_500m ?? '—' }),
      el('td', { class: 'num', text: info.ate_1km ?? '—' })));
  }
  const lista = [];
  for (const [categoria, itens] of Object.entries(p.entorno)) {
    for (const item of itens) lista.push([categoria, item]);
  }
  lista.sort((a, b) => a[1].distancia_m - b[1].distancia_m);
  const tabelaEntorno = $('entorno');
  tabelaEntorno.replaceChildren();
  if (!lista.length) linhaVazia(tabelaEntorno, 5, 'Nenhum equipamento a até 1 km.');
  for (const [categoria, item] of lista) {
    tabelaEntorno.append(el('tr', {},
      el('td', { text: CATEGORIAS[categoria][0] }),
      el('td', { text: TIPOS[item.tipo] }),
      el('th', { scope: 'row', text: item.nome }),
      el('td', { class: 'num', text: distancia(item.distancia_m) }),
      el('td', { class: 'num', text: minutos(item.distancia_m) })));
  }
}

function renderVitalidade(v) {
  $('ivep').textContent = num.format(v.ivep);
  $('ivep-mediana').textContent = v.mediana_municipal == null ? ''
    : `Mediana dos 96 distritos com os mesmos pesos: ${num.format(v.mediana_municipal)}.`;
  const ul = $('ivep-categorias');
  ul.replaceChildren();
  const tabela = $('vitalidade');
  tabela.replaceChildren();
  for (const [categoria, info] of Object.entries(v.categorias)) {
    ul.append(barra(CATEGORIAS[categoria][0], info.percentil, { corDaBarra: cor(categoria), mediana: 50 }));
    tabela.append(el('tr', {},
      el('th', { scope: 'row', text: CATEGORIAS[categoria][0] }),
      el('td', { class: 'num', text: info.equipamentos == null ? '—' : int.format(info.equipamentos) }),
      el('td', { class: 'num', text: info.densidade_km2 == null ? '—' : num.format(info.densidade_km2) }),
      el('td', { class: 'num', text: info.densidade_10k_hab == null ? '—' : num.format(info.densidade_10k_hab) }),
      el('td', { class: 'num', text: info.percentil == null ? '—' : num.format(info.percentil) })));
  }
}

function renderOcorrencias(o) {
  $('occ-janela').textContent = `Taxa por 100 mil moradores por ano, de ${o.janela[0]} a ${o.janela[1]}`
    + ` · população do distrito: ${int.format(o.populacao)} (Censo 2022).`;
  $('occ-subnotificacao').textContent = o.aviso_subnotificacao;
  $('occ-observacao').textContent = o.observacao;
  const grid = $('ocorrencias');
  grid.replaceChildren();
  for (const natureza of Object.values(o.naturezas)) {
    const card = el('article', { class: 'card occ' },
      el('h3', {}, el('span', { text: natureza.rotulo }),
        el('span', { class: 'tag', text: `${int.format(natureza.ocorrencias)} registros` })));
    if (natureza.taxa_100k_ano == null) {
      card.append(el('p', { class: 'muted', text: `${natureza.mensagem[0].toUpperCase()}${natureza.mensagem.slice(1)}.` }));
      grid.append(card);
      continue;
    }
    const maximo = Math.max(natureza.taxa_100k_ano, natureza.taxa_municipal_100k_ano || 0) || 1;
    const linha = (rotulo, valor, classe) => {
      const fill = el('div', { class: `fill ${classe}` });
      fill.style.width = `${(100 * valor) / maximo}%`;
      return el('div', { class: 'bar' },
        el('span', { text: rotulo }),
        el('div', { class: 'track', role: 'img', 'aria-label': `${rotulo}: ${num.format(valor)} por 100 mil por ano` }, fill),
        el('span', { class: 'value', text: num.format(valor) }));
    };
    card.append(el('div', { class: 'pair' },
      linha('Este distrito', natureza.taxa_100k_ano, 'district'),
      linha('Cidade', natureza.taxa_municipal_100k_ano, 'city')));
    const porAno = Object.entries(natureza.taxa_por_ano).map(([ano, taxa]) => `${ano}: ${num.format(taxa)}`).join(' · ');
    card.append(el('p', { class: 'trend' },
      el('strong', { text: TENDENCIA[natureza.tendencia] || '' }),
      el('span', { class: 'muted', text: ` (${porAno})` })));
    grid.append(card);
  }
}

function renderFontes(fontes) {
  const ul = $('lista-fontes');
  ul.replaceChildren();
  for (const fonte of fontes || []) {
    const data = fonte.data_referencia
      ? new Date(`${fonte.data_referencia}T12:00:00`).toLocaleDateString('pt-BR') : 'sem data';
    const item = el('li', {},
      el('a', { href: fonte.url, target: '_blank', rel: 'noreferrer', text: fonte.fonte }),
      ` — ${fonte.descricao}: ${data}${fonte.observacao ? ` (${fonte.observacao})` : ''}`
      + `${fonte.licenca ? `. Licença ${fonte.licenca}` : ''}.`);
    if (fonte.aviso) item.append(el('strong', { text: ` Aviso: ${fonte.aviso}.` }));
    ul.append(item);
  }
}

async function render(resposta, soPesos) {
  const d = resposta.diagnostico;
  state.dados = resposta;
  state.distrito = resposta.local.distrito;
  $('resultado').hidden = false;
  $('fora').hidden = true;
  const titulo = state.endereco
    ? [state.endereco.logradouro, state.endereco.bairro].filter(Boolean).join(', ') || `CEP ${state.endereco.cep}`
    : 'Ponto escolhido no mapa';
  $('local-titulo').textContent = titulo;
  $('local-distrito').textContent = `Distrito: ${state.distrito.nome}`;
  $('local-aviso').textContent = state.endereco
    ? 'A localização obtida pelo CEP é aproximada: ela identifica o distrito, mas não a posição exata do imóvel.'
    : 'Diagnóstico do ponto clicado no mapa.';
  renderProximidade(d.proximidade);
  renderVitalidade(d.vitalidade);
  renderOcorrencias(d.ocorrencias);
  renderFontes(resposta.fontes);
  if (!soPesos) await desenharMapa(d);
}

// ---------- consulta (RF15: resultado e erros na região viva) ----------
async function diagnosticar(alvo, soPesos = false) {
  const pedido = ++state.pedido;
  const query = new URLSearchParams(pesos());
  if (alvo.cep) query.set('cep', alvo.cep);
  else {
    query.set('lat', alvo.lat.toFixed(6));
    query.set('lon', alvo.lon.toFixed(6));
  }
  $('consultar').disabled = true;
  anunciar(soPesos ? 'Recalculando os índices com as novas prioridades…' : 'Consultando o diagnóstico…');
  try {
    const resposta = await getJSON(`/api/diagnostico?${query}`);
    if (pedido !== state.pedido) return;
    if (alvo.cep) state.endereco = resposta.local.endereco || null;
    if (!resposta.diagnostico && !alvo.cep && state.dados) {
      anunciar(`${resposta.aviso} Escolha um ponto dentro da cidade.`, true);
      return;
    }
    if (!resposta.diagnostico) {
      $('resultado').hidden = true;
      $('fora').hidden = false;
      const endereco = [resposta.local.endereco?.logradouro, resposta.local.endereco?.municipio].filter(Boolean).join(', ');
      $('fora-texto').textContent = `${resposta.aviso}${endereco ? ` (${endereco})` : ''}`
        + ' O diagnóstico cobre apenas os 96 distritos da capital.';
      anunciar(resposta.aviso, true);
      return;
    }
    state.lat = resposta.local.latitude;
    state.lon = resposta.local.longitude;
    state.origem = resposta.local.origem_coordenada;
    await render(resposta, soPesos);
    const d = resposta.diagnostico;
    anunciar(`${soPesos ? 'Índices recalculados' : 'Diagnóstico concluído'} para o distrito ${state.distrito.nome}: `
      + `proximidade ${d.proximidade.ipl == null ? 'sem dados' : num.format(d.proximidade.ipl)}, `
      + `vitalidade ${num.format(d.vitalidade.ivep)}, de 100.`);
    if (!soPesos) {
      $('local-titulo').focus();
      if (alvo.cep) history.replaceState(null, '', `?cep=${alvo.cep}`);
    }
  } catch (erro) {
    if (pedido === state.pedido) anunciar(erro.message, true);
  } finally {
    if (pedido === state.pedido) $('consultar').disabled = false;
  }
}

$('cep').addEventListener('input', (evento) => {
  const digitos = evento.target.value.replace(/\D/g, '').slice(0, 8);
  evento.target.value = digitos.length > 5 ? `${digitos.slice(0, 5)}-${digitos.slice(5)}` : digitos;
});

$('form').addEventListener('submit', (evento) => {
  evento.preventDefault();
  const cep = $('cep').value.replace(/\D/g, '');
  if (cep.length !== 8) {
    anunciar('O CEP deve ter 8 números.', true);
    $('cep').focus();
    return;
  }
  diagnosticar({ cep });
});

const inicial = new URLSearchParams(location.search).get('cep');
if (inicial) {
  $('cep').value = inicial;
  $('cep').dispatchEvent(new Event('input'));
  diagnosticar({ cep: inicial.replace(/\D/g, '') });
}
