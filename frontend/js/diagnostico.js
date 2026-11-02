// Tela de diagnóstico do endereço (UC01 a UC04). JavaScript da página, servido
// como estático; o Leaflet continua global (variável L).

import { $, el, num, int, distancia, minutos, getJSON, corCss, atualizarUrl, csv, baixarArquivo } from './util.js';
import { instalarBarraDeAcessibilidade, instalarAtalhos } from './acessibilidade.js';

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
  espera = setTimeout(async () => {
    await diagnosticar({ lat: state.lat, lon: state.lon }, true);
    await recalcularComparacao();
  }, 250);
}

async function recalcularComparacao() {
  if (!comparacoes.length) return;
  const alvos = comparacoes.map((item) => item.alvo);
  try {
    const respostas = await Promise.all(alvos.map((alvo) => consultar(alvo)));
    comparacoes = respostas.map((r, i) => ({ ...resumoDe(r), alvo: alvos[i] }));
    renderComparacao();
  } catch {
    /* mantém a comparação anterior se alguma consulta falhar */
  }
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
function estadoVazio(titulo) {
  $('local-titulo').textContent = titulo;
  $('local-distrito').textContent = '';
  $('local-aviso').textContent = 'Os índices aparecem depois de uma consulta válida; as abas já podem ser percorridas pelo teclado.';
  $('ipl').textContent = '—';
  $('ivep').textContent = '—';
  $('ivep-mediana').textContent = '';
  $('occ-janela').textContent = '';
  $('occ-subnotificacao').textContent = '';
  $('occ-observacao').textContent = '';
  for (const id of ['ipl-categorias', 'ivep-categorias', 'ocorrencias', 'lista-fontes']) $(id).replaceChildren();
  linhaVazia($('tipos'), 7, 'Sem dados: consulte um endereço.');
  linhaVazia($('vitalidade'), 5, 'Sem dados: consulte um endereço.');
  linhaVazia($('entorno'), 5, 'Sem dados: consulte um endereço.');
}

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
  $('fora').hidden = true;
  const titulo = state.endereco
    ? [state.endereco.logradouro, state.endereco.numero && `nº ${state.endereco.numero}`,
       state.endereco.bairro].filter(Boolean).join(', ') || `CEP ${state.endereco.cep}`
    : 'Ponto escolhido no mapa';
  $('local-titulo').textContent = titulo;
  $('local-distrito').textContent = `Distrito: ${state.distrito.nome}`;
  $('local-aviso').textContent = resposta.local.aviso_localizacao
    || 'Diagnóstico do ponto clicado no mapa.';
  renderProximidade(d.proximidade);
  renderVitalidade(d.vitalidade);
  renderOcorrencias(d.ocorrencias);
  renderFontes(resposta.fontes);
  if (!soPesos) await desenharMapa(d);
}

// ---------- exportação (RF18, versão CSV) ----------
function linhasCsv(resposta) {
  const d = resposta.diagnostico;
  const local = resposta.local;
  const linhas = [['bloco', 'indicador', 'categoria/tipo/natureza', 'valor', 'unidade', 'detalhe']];
  const endereco = [local.endereco?.logradouro, local.endereco?.numero && `nº ${local.endereco.numero}`,
    local.endereco?.bairro, local.endereco?.cep].filter(Boolean).join(', ');
  linhas.push(['local', 'endereço', endereco, '', '', '']);
  linhas.push(['local', 'distrito', local.distrito.nome, local.distrito.codigo, '',
    local.distrito.regiao || '']);
  linhas.push(['local', 'coordenada', `${local.latitude.toFixed(6)},${local.longitude.toFixed(6)}`,
    'graus', '', local.origem_coordenada]);
  linhas.push(['local', 'aviso da coordenada', local.aviso_localizacao || '', '', '', '']);
  linhas.push(['proximidade', 'IPL', d.proximidade.ipl ?? '', 'de 100',
    d.proximidade.medida, 'pesos: ' + Object.entries(d.proximidade.categorias)
      .map(([c, i]) => `${c}=${i.peso}`).join(',')]);
  for (const [categoria, info] of Object.entries(d.proximidade.categorias)) {
    linhas.push(['proximidade', 'nota da categoria', categoria, info.nota ?? '', 'de 100', `peso ${info.peso}`]);
  }
  for (const [tipo, info] of Object.entries(d.proximidade.tipos)) {
    const detalhe = info.pontos_no_raio != null
      ? `${info.pontos_no_raio} pontos no raio de ${info.raio_medida_m} m`
      : (info.nome || '');
    linhas.push(['proximidade', 'tipo', tipo, info.nota ?? '', 'de 100',
      `${detalhe}${info.distancia_m != null ? ` · ${info.distancia_m} m em linha reta` : ''}`
      + `${info.tempo_caminhada_min != null ? ` · ${info.tempo_caminhada_min} min a pé` : ''}`
      + `${info.ate_500m != null ? ` · ${info.ate_500m} até 500 m · ${info.ate_1km} até 1 km` : ''}`
      + `${info.aviso ? ` · ${info.aviso}` : ''}`]);
  }
  for (const [categoria, itens] of Object.entries(d.proximidade.entorno)) {
    for (const item of itens) {
      linhas.push(['proximidade', 'equipamento no entorno', `${categoria} · ${item.tipo}`, item.distancia_m, 'm',
        `${item.nome} · ${minutos(item.distancia_m)} a pé`]);
    }
  }
  linhas.push(['vitalidade', 'IVEP', d.vitalidade.ivep, 'de 100', 'distrito', '']);
  for (const [categoria, info] of Object.entries(d.vitalidade.categorias)) {
    linhas.push(['vitalidade', 'categoria', categoria, info.percentil ?? '', 'percentil',
      `${info.equipamentos ?? 0} equipamentos · ${info.densidade_km2 ?? ''}/km²`
      + ` · ${info.densidade_10k_hab ?? ''}/10 mil hab · peso ${info.peso}`]);
  }
  const oc = d.ocorrencias;
  linhas.push(['ocorrencias', 'janela', oc.janela.join('-'), '', 'anos completos',
    `população ${oc.populacao}`]);
  for (const [grupo, item] of Object.entries(oc.naturezas)) {
    linhas.push(['ocorrencias', 'natureza', grupo, item.taxa_100k_ano ?? '', 'por 100 mil por ano',
      `${item.ocorrencias} registros${item.taxa_municipal_100k_ano != null
        ? ` · cidade ${item.taxa_municipal_100k_ano}` : ''}`
      + `${item.tendencia ? ` · tendência ${item.tendencia}` : ''}`
      + `${item.mensagem ? ` · ${item.mensagem}` : ''}`]);
  }
  linhas.push(['ocorrencias', 'aviso', oc.aviso_subnotificacao, '', '', '']);
  for (const fonte of resposta.fontes || []) {
    linhas.push(['fontes', fonte.fonte, fonte.descricao, fonte.data_referencia || '', '',
      `${fonte.observacao || ''}${fonte.aviso ? ` · ${fonte.aviso}` : ''}${fonte.licenca ? ` · ${fonte.licenca}` : ''}`]);
  }
  return linhas;
}

const baixar = el('button', { type: 'button', class: 'btn-light', text: 'Baixar diagnóstico em CSV' });
baixar.addEventListener('click', () => {
  if (!state.dados?.diagnostico) {
    anunciar('Consulte um endereço antes de baixar o CSV.', true);
    return;
  }
  const ponto = `${state.lat.toFixed(4)}_${state.lon.toFixed(4)}`.replace(/\./g, ',');
  baixarArquivo(`geohabita-${state.distrito.codigo}-${ponto}.csv`, csv(linhasCsv(state.dados)));
  anunciar('Arquivo CSV gerado no seu navegador: nada foi enviado nem guardado no servidor.');
});

// ---------- comparação de até três endereços (RF16, UC05) ----------
const MAXIMO_COMPARACAO = 3;
let comparacoes = [];

async function resolverEndereco(texto) {
  /** "01001-000" vira CEP; qualquer outra coisa passa pela busca de endereço. */
  const digitos = (texto || '').replace(/\D/g, '');
  if (/^[0-9-]+$/.test(texto.trim()) && digitos.length === 8) {
    return { cep: digitos, numero: state.endereco?.numero || '' };
  }
  const resposta = await getJSON(`/api/enderecos?${new URLSearchParams({ logradouro: texto })}`);
  if (!resposta.candidatos.length) throw new Error(resposta.mensagem || 'Endereço não encontrado.');
  if (resposta.sugerido != null) {
    const escolha = resposta.candidatos[resposta.sugerido];
    return escolha.cep ? { cep: escolha.cep, numero: escolha.numero }
      : { lat: escolha.latitude, lon: escolha.longitude, rotulo: escolha.rotulo || escolha.logradouro };
  }
  throw new Error('Mais de um endereço corresponde: refine com o número do imóvel.');
}

async function consultar(alvo) {
  const query = new URLSearchParams(pesos());
  if (alvo.cep) {
    query.set('cep', alvo.cep);
    if (alvo.numero) query.set('numero', alvo.numero);
  } else {
    query.set('lat', alvo.lat.toFixed(6));
    query.set('lon', alvo.lon.toFixed(6));
  }
  return getJSON(`/api/diagnostico?${query}`);
}

function resumoDe(resposta, alvo = state.alvo) {
  const d = resposta.diagnostico;
  const naturezas = Object.values(d.ocorrencias.naturezas);
  const comTaxa = naturezas.filter((n) => n.taxa_100k_ano != null);
  return {
    titulo: resposta.local.endereco
      ? [resposta.local.endereco.logradouro, resposta.local.endereco.numero && `nº ${resposta.local.endereco.numero}`,
         resposta.local.endereco.bairro].filter(Boolean).join(', ') || `CEP ${resposta.local.endereco.cep}`
      : (resposta.local.rotulo || 'Ponto no mapa'),
    distrito: resposta.local.distrito,
    ipl: d.proximidade.ipl,
    ivep: d.vitalidade.ivep,
    categorias: d.proximidade.categorias,
    iluminacao: d.proximidade.tipos.iluminacao_publica,
    ocorrencias: comTaxa.map((n) => ({ rotulo: n.rotulo, taxa: n.taxa_100k_ano })),
    semTaxa: naturezas.filter((n) => n.taxa_100k_ano == null).map((n) => n.rotulo),
    aviso: resposta.local.aviso_localizacao,
    alvo,
  };
}

function cartaoComparacao(item, indice) {
  const remover = el('button', { type: 'button', class: 'btn-light comp-remover', text: 'Remover' });
  remover.addEventListener('click', () => {
    comparacoes.splice(indice, 1);
    renderComparacao();
  });
  const categorias = el('ul', { class: 'bars' });
  for (const [categoria, info] of Object.entries(item.categorias)) {
    if (info.nota == null) continue;
    categorias.append(el('li', { class: 'comp-item' },
      el('span', { text: CATEGORIAS[categoria][0] }),
      el('span', { class: 'value', text: num.format(info.nota) })));
  }
  const ocorrencias = el('ul', { class: 'bars' });
  for (const n of item.ocorrencias) {
    ocorrencias.append(el('li', { class: 'comp-item' },
      el('span', { text: n.rotulo }), el('span', { class: 'value', text: `${num.format(n.taxa)} / 100 mil` })));
  }
  if (item.semTaxa.length) {
    ocorrencias.append(el('li', { class: 'comp-nota', text: `Sem taxa comparável: ${item.semTaxa.join(', ')}.` }));
  }
  return el('article', { class: 'card comp-card' },
    el('h4', {}, el('span', { text: item.titulo }), el('span', { class: 'tag', text: `distrito ${item.distrito.nome}` })),
    remover,
    el('p', { class: 'comp-indices' },
      el('strong', { text: `IPL ${item.ipl == null ? '—' : num.format(item.ipl)}` }),
      el('span', { text: ` · IVEP ${num.format(item.ivep)} · iluminação ${item.iluminacao.nota == null ? 'sem dados' : `${num.format(item.iluminacao.nota)} (${int.format(item.iluminacao.densidade_km2 ?? 0)} pontos/km²)`}` }),
      ' de 100'),
    categorias, ocorrencias,
    item.aviso ? el('p', { class: 'hint', text: item.aviso }) : null);
}

function renderComparacao() {
  const lista = $('comparar');
  lista.replaceChildren();
  if (!comparacoes.length) {
    lista.append(el('p', { class: 'empty', text: 'Nenhum endereço fixado. Use "Fixar esta consulta" ou adicione acima.' }));
    return;
  }
  for (const [indice, item] of comparacoes.entries()) lista.append(cartaoComparacao(item, indice));
}

function fixarConsultaAtual() {
  if (!state.dados?.diagnostico) {
    anunciar('Consulte um endereço antes de fixá-lo na comparação.', true);
    return;
  }
  const resumo = resumoDe(state.dados);
  const repetido = comparacoes.findIndex((c) => c.titulo === resumo.titulo);
  if (repetido >= 0) comparacoes.splice(repetido, 1);
  if (comparacoes.length >= MAXIMO_COMPARACAO) comparacoes.shift();
  comparacoes.push(resumo);
  renderComparacao();
  anunciar(`${resumo.titulo} fixado na comparação (${comparacoes.length} de ${MAXIMO_COMPARACAO}).`);
}

$('form-comparar').addEventListener('submit', async (evento) => {
  evento.preventDefault();
  const entrada = $('comp-entrada').value.trim();
  if (!entrada) {
    anunciar('Informe um CEP ou uma rua com número para comparar.', true);
    return;
  }
  if (comparacoes.length >= MAXIMO_COMPARACAO) {
    anunciar('A comparação aceita três endereços: remova um antes de adicionar outro.', true);
    return;
  }
  anunciar('Consultando o endereço para comparação…');
  try {
    const alvo = await resolverEndereco(entrada);
    const resposta = await consultar(alvo);
    if (!resposta.diagnostico) throw new Error(resposta.aviso || 'Endereço fora do município.');
    comparacoes.push(resumoDe(resposta));
    $('comp-entrada').value = '';
    renderComparacao();
    anunciar(`${resposta.local.distrito.nome} adicionado à comparação (${comparacoes.length} de ${MAXIMO_COMPARACAO}).`);
  } catch (erro) {
    anunciar(erro.message, true);
  }
});

const acoes = el('div', { class: 'acoes-consulta' });
const fixar = el('button', { type: 'button', class: 'btn-light', text: 'Fixar esta consulta para comparar' });
fixar.addEventListener('click', fixarConsultaAtual);
acoes.append(fixar, baixar);
$('consulta').append(acoes);

// ---------- consulta (RF15: resultado e erros na região viva) ----------
async function diagnosticar(alvo, soPesos = false) {
  const pedido = ++state.pedido;
  const query = new URLSearchParams(pesos());
  if (alvo.cep) {
    query.set('cep', alvo.cep);
    if (alvo.numero) query.set('numero', alvo.numero);
  } else {
    query.set('lat', alvo.lat.toFixed(6));
    query.set('lon', alvo.lon.toFixed(6));
  }
  $('consultar').disabled = true;
  anunciar(soPesos ? 'Recalculando os índices com as novas prioridades…' : 'Consultando o diagnóstico…');
  try {
    const resposta = await getJSON(`/api/diagnostico?${query}`);
    if (pedido !== state.pedido) return;
    state.alvo = alvo;
    if (alvo.cep) state.endereco = resposta.local.endereco || null;
    state.origem = resposta.local.origem_coordenada;
    if (!resposta.diagnostico && !alvo.cep && state.dados) {
      anunciar(`${resposta.aviso} Escolha um ponto dentro da cidade.`, true);
      return;
    }
    if (!resposta.diagnostico) {
      estadoVazio('Nenhum endereço consultado');
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
      if (alvo.cep) atualizarUrl({ cep: alvo.cep, numero: alvo.numero || '' });
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
  const numero = $('numero').value.trim();
  const logradouro = $('logradouro').value.trim();
  if (cep.length === 8) {
    fecharCandidatos();
    diagnosticar({ cep, numero });
    return;
  }
  if (logradouro.length >= 3) {
    buscarEndereco(logradouro, numero);
    return;
  }
  anunciar('Digite os 8 números do CEP ou, se não souber, o nome da rua com o número do imóvel.', true);
  $('cep').focus();
});

// Busca por endereço: o ViaCEP devolve os CEPs do logradouro e o número escolhe
// o trecho; quando há mais de um candidato, a lista aparece abaixo do campo.
async function buscarEndereco(logradouro, numero) {
  const query = new URLSearchParams({ logradouro });
  if (numero) query.set('numero', numero);
  anunciar('Buscando o endereço…');
  try {
    const resposta = await getJSON(`/api/enderecos?${query}`);
    mostrarCandidatos(resposta, numero);
  } catch (erro) {
    anunciar(erro.message, true);
  }
}

function mostrarCandidatos(resposta, numero) {
  const caixa = $('candidatos');
  caixa.replaceChildren();
  if (!resposta.candidatos.length) {
    caixa.hidden = true;
    anunciar(resposta.mensagem || 'Nenhum endereço encontrado.', true);
    return;
  }
  if (resposta.sugerido != null) {
    const escolhido = resposta.candidatos[resposta.sugerido];
    caixa.hidden = true;
    if (escolhido.latitude != null && !escolhido.cep) {
      diagnosticar({ lat: escolhido.latitude, lon: escolhido.longitude });
    } else {
      diagnosticar({ cep: escolhido.cep, numero: numero || escolhido.numero });
    }
    return;
  }
  caixa.hidden = false;
  caixa.append(el('p', { class: 'hint', text: resposta.mensagem || 'Escolha um endereço da lista:' }));
  const lista = el('ul', { class: 'candidatos-lista' });
  for (const candidato of resposta.candidatos) {
    const rotulo = [candidato.logradouro, candidato.numero && `nº ${candidato.numero}`, candidato.complemento,
      candidato.predio, candidato.bairro, candidato.cep && `CEP ${candidato.cep}`].filter(Boolean).join(' · ');
    const botao = el('button', { type: 'button', class: 'candidato', text: rotulo });
    botao.addEventListener('click', () => {
      fecharCandidatos();
      if (candidato.cep) diagnosticar({ cep: candidato.cep, numero: candidato.numero });
      else diagnosticar({ lat: candidato.latitude, lon: candidato.longitude });
    });
    lista.append(el('li', {}, botao));
  }
  caixa.append(lista);
  anunciar(`${resposta.candidatos.length} endereços encontrados. Escolha um na lista abaixo do campo.`);
}

function fecharCandidatos() {
  const caixa = $('candidatos');
  caixa.replaceChildren();
  caixa.hidden = true;
}

// ---------- inicialização ----------
estadoVazio('Nenhum endereço consultado');
instalarBarraDeAcessibilidade({ anunciar });
instalarAtalhos();

const inicial = new URLSearchParams(location.search);
const cepInicial = inicial.get('cep');
if (cepInicial) {
  $('cep').value = cepInicial;
  $('cep').dispatchEvent(new Event('input'));
  $('numero').value = inicial.get('numero') || '';
  diagnosticar({ cep: cepInicial.replace(/\D/g, ''), numero: $('numero').value });
}

// Ao trocar o contraste, as cores vêm de novas variáveis CSS: repinta o mapa.
new MutationObserver(() => {
  for (const categoria of Object.keys(CATEGORIAS)) {
    const swatch = $(`f-${categoria}`)?.parentElement.querySelector('.swatch');
    if (swatch) swatch.style.background = cor(categoria);
    for (const camada of camadas.categorias[categoria].getLayers()) camada.setStyle?.({ fillColor: cor(categoria) });
  }
  if (state.dados) {
    renderProximidade(state.dados.diagnostico.proximidade);
    renderVitalidade(state.dados.diagnostico.vitalidade);
  }
}).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
