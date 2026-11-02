// Tela de diagnóstico do endereço (UC01 a UC04). JavaScript da página, servido
// como estático; o Leaflet continua global (variável L).

import {$, el, num, int, distancia, minutos, getJSON, corCss} from './util.js';

'use strict';
const $=id=>document.getElementById(id);
const num=new Intl.NumberFormat('pt-BR',{maximumFractionDigits:1});
const int=new Intl.NumberFormat('pt-BR');
const CATEGORIAS={lazer_convivencia:['Lazer e convivência','var(--c-lazer)','#2e7d32'],cultura_esporte:['Cultura e esporte','var(--c-cultura)','#6a3d9a'],mobilidade:['Mobilidade','var(--c-mobilidade)','#1f5fa8'],comercio_rua:['Comércio de rua','var(--c-comercio)','#8a5a00'],servicos_essenciais:['Serviços essenciais','var(--c-servicos)','#00796b'],conectividade:['Conectividade','var(--c-conectividade)','#455a64']};
const TIPOS={praca:'Praça',parque_area_verde:'Parque ou área verde',biblioteca_centro_cultural:'Biblioteca ou centro cultural',ceu_equipamento_esportivo:'CEU ou equipamento esportivo',ponto_onibus:'Ponto de ônibus',estacao_metro_trem:'Estação de metrô ou trem',ciclovia:'Ciclovia',feira_mercado_municipal:'Feira livre ou mercado',unidade_basica_saude:'Unidade básica de saúde',escola_publica:'Escola pública',wifi_publico:'Wi-Fi público'};
const TENDENCIA={alta:'Em alta no período',queda:'Em queda no período','estável':'Estável no período'};
const state={lat:null,lon:null,endereco:null,distrito:null,origem:null,dados:null,pedido:0};

// ---------- utilidades ----------
const el=(tag,props={},...kids)=>{const e=document.createElement(tag);for(const [k,v] of Object.entries(props)){if(k==='class')e.className=v;else if(k==='text')e.textContent=v;else if(k.startsWith('aria-')||k==='role'||k==='scope')e.setAttribute(k,v);else e[k]=v}e.append(...kids.filter(k=>k!=null));return e};
const distancia=m=>m==null?'—':m<1000?`${int.format(Math.round(m))} m`:`${num.format(m/1000)} km`;
const minutos=m=>m==null?'—':`${int.format(Math.ceil(m/80))} min`;
function anunciar(msg,erro=false){const s=$('status');s.textContent=msg;s.classList.toggle('erro',erro)}
async function getJSON(url){const r=await fetch(url);let d={};try{d=await r.json()}catch{}if(!r.ok){const det=Array.isArray(d.detail)?'Parâmetro inválido.':d.detail;throw Error(det||'Não foi possível consultar o serviço.')}return d}
function pesos(){const p={};for(const c of Object.keys(CATEGORIAS))p['peso_'+c]=$('peso-'+c).value;return p}
function barra(rotulo,valor,{mediana=null,cor=null,sufixo=''}={}){const pct=valor==null?0:Math.max(0,Math.min(100,valor));const fill=el('div',{class:'fill'});fill.style.width=pct+'%';if(cor)fill.style.background=cor;const track=el('div',{class:'track','role':'img','aria-label':`${rotulo}: ${valor==null?'sem dados':num.format(valor)+' de 100'}`},fill);if(mediana!=null){const m=el('div',{class:'median'});m.style.left=mediana+'%';track.append(m)}return el('li',{class:'bar'},el('span',{text:rotulo}),track,el('span',{class:'value',text:valor==null?'—':num.format(valor)+sufixo}))}

// ---------- pesos (RF09) ----------
for(const [c,[rotulo]] of Object.entries(CATEGORIAS)){const sel=el('select',{id:'peso-'+c});for(let i=0;i<=5;i++)sel.add(new Option(i===0?'0 · não importa':i===5?'5 · muito importante':String(i),String(i),i===1,i===1));sel.addEventListener('change',recalcular);$('pesos').append(el('label',{htmlFor:'peso-'+c},rotulo,sel))}
let espera=null;function recalcular(){clearTimeout(espera);if(state.lat==null)return;espera=setTimeout(()=>diagnosticar({lat:state.lat,lon:state.lon},true),250)}

// ---------- abas (padrão WAI-ARIA) ----------
const abas=[...document.querySelectorAll('[role=tab]')];
function abrirAba(aba,foco=true){for(const a of abas){const sel=a===aba;a.setAttribute('aria-selected',String(sel));a.tabIndex=sel?0:-1;$(a.getAttribute('aria-controls')).hidden=!sel}if(foco)aba.focus();if(aba.id==='aba-proximidade')setTimeout(()=>mapa.invalidateSize(),50)}
abas.forEach((a,i)=>{a.addEventListener('click',()=>abrirAba(a));a.addEventListener('keydown',e=>{const k={ArrowRight:i+1,ArrowLeft:i-1,Home:0,End:abas.length-1}[e.key];if(k!=null){e.preventDefault();abrirAba(abas[(k+abas.length)%abas.length])}})});

// ---------- mapa (RF13) ----------
const mapa=L.map('map',{keyboard:true,minZoom:10,maxZoom:18}).setView([-23.55,-46.63],11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(mapa);
const camadas={base:L.layerGroup().addTo(mapa),categorias:{}};
for(const [c,[rotulo,,cor]] of Object.entries(CATEGORIAS)){camadas.categorias[c]=L.layerGroup().addTo(mapa);const cb=el('input',{type:'checkbox',checked:true,id:'f-'+c});cb.addEventListener('change',()=>cb.checked?camadas.categorias[c].addTo(mapa):camadas.categorias[c].remove());const sw=el('span',{class:'swatch','aria-hidden':'true'});sw.style.background=cor;$('filtros').append(el('label',{htmlFor:'f-'+c},cb,sw,rotulo))}
mapa.on('click',e=>{if(state.lat==null)return;state.endereco=null;diagnosticar({lat:e.latlng.lat,lon:e.latlng.lng})});
const limites={};
async function desenharMapa(d){mapa.invalidateSize();camadas.base.clearLayers();Object.values(camadas.categorias).forEach(g=>g.clearLayers());
 const ponto=[state.lat,state.lon];
 L.marker(ponto,{title:'Ponto consultado',alt:'Ponto consultado',keyboard:true}).bindPopup(state.endereco?`${state.endereco.logradouro||'CEP '+state.endereco.cep}`:'Ponto escolhido no mapa').addTo(camadas.base);
 for(const r of [500,1000])L.circle(ponto,{radius:r,color:'#21424f',weight:1.5,dashArray:'6 6',fill:false,interactive:false}).addTo(camadas.base);
 for(const [categoria,itens] of Object.entries(d.proximidade.entorno)){const cor=CATEGORIAS[categoria][2];for(const it of itens){if(it.latitude==null)continue;const m=L.circleMarker([it.latitude,it.longitude],{radius:6,color:'#fff',weight:1.5,fillColor:cor,fillOpacity:.95});const box=el('div',{},el('div',{class:'popup-title',text:it.nome}),el('div',{text:`${TIPOS[it.tipo]} · ${distancia(it.distancia_m)} em linha reta`}));m.bindPopup(box);m.addTo(camadas.categorias[categoria])}}
 const cod=state.distrito.codigo;try{limites[cod]=limites[cod]||await getJSON(`/api/distritos/${encodeURIComponent(cod)}/limite`);L.geoJSON(limites[cod],{style:{color:'#21424f',weight:2,fill:false},interactive:false}).addTo(camadas.base)}catch{}
 mapa.invalidateSize();mapa.fitBounds(L.latLng(ponto).toBounds(2300))}

// ---------- renderização ----------
function linhaVazia(tbody,colunas,texto){tbody.replaceChildren(el('tr',{},el('td',{colSpan:colunas,text:texto})))}
function renderProximidade(p){
 $('ipl').textContent=p.ipl==null?'—':num.format(p.ipl);
 const ul=$('ipl-categorias');ul.replaceChildren();
 for(const [c,info] of Object.entries(p.categorias)){const li=barra(CATEGORIAS[c][0],info.nota,{cor:CATEGORIAS[c][1]});if(info.nota==null)li.querySelector('.value').title='sem dados na fonte';ul.append(li)}
 const tb=$('tipos');tb.replaceChildren();
 for(const [t,info] of Object.entries(p.tipos)){
  const nome=info.disponivel?(info.nome||'—'):el('span',{class:'muted',text:'sem dados na fonte'});
  const tr=el('tr',{},el('th',{scope:'row',text:TIPOS[t]}),el('td',{},nome,info.aviso&&info.disponivel?el('div',{class:'muted',text:info.aviso}):null),
   el('td',{class:'num',text:distancia(info.distancia_m)}),el('td',{class:'num',text:info.tempo_caminhada_min==null?'—':`${info.tempo_caminhada_min} min`}),
   el('td',{class:'num',text:info.nota==null?'—':num.format(info.nota)}),el('td',{class:'num',text:info.ate_500m??'—'}),el('td',{class:'num',text:info.ate_1km??'—'}));
  tb.append(tr)}
 const lista=[];for(const [c,itens] of Object.entries(p.entorno))for(const it of itens)lista.push([c,it]);lista.sort((a,b)=>a[1].distancia_m-b[1].distancia_m);
 const te=$('entorno');te.replaceChildren();if(!lista.length)linhaVazia(te,5,'Nenhum equipamento a até 1 km.');
 for(const [c,it] of lista)te.append(el('tr',{},el('td',{text:CATEGORIAS[c][0]}),el('td',{text:TIPOS[it.tipo]}),el('th',{scope:'row',text:it.nome}),el('td',{class:'num',text:distancia(it.distancia_m)}),el('td',{class:'num',text:minutos(it.distancia_m)})))}
function renderVitalidade(v){
 $('ivep').textContent=num.format(v.ivep);
 $('ivep-mediana').textContent=v.mediana_municipal==null?'':`Mediana dos 96 distritos com os mesmos pesos: ${num.format(v.mediana_municipal)}.`;
 const ul=$('ivep-categorias');ul.replaceChildren();const tb=$('vitalidade');tb.replaceChildren();
 for(const [c,info] of Object.entries(v.categorias)){ul.append(barra(CATEGORIAS[c][0],info.percentil,{cor:CATEGORIAS[c][1],mediana:50}));
  tb.append(el('tr',{},el('th',{scope:'row',text:CATEGORIAS[c][0]}),el('td',{class:'num',text:info.equipamentos==null?'—':int.format(info.equipamentos)}),el('td',{class:'num',text:info.densidade_km2==null?'—':num.format(info.densidade_km2)}),el('td',{class:'num',text:info.densidade_10k_hab==null?'—':num.format(info.densidade_10k_hab)}),el('td',{class:'num',text:info.percentil==null?'—':num.format(info.percentil)})))}}
function renderOcorrencias(o){
 $('occ-janela').textContent=`Taxa por 100 mil moradores por ano, de ${o.janela[0]} a ${o.janela[1]} · população do distrito: ${int.format(o.populacao)} (Censo 2022).`;
 $('occ-subnotificacao').textContent=o.aviso_subnotificacao;$('occ-observacao').textContent=o.observacao;
 const grid=$('ocorrencias');grid.replaceChildren();
 for(const n of Object.values(o.naturezas)){
  const card=el('article',{class:'card occ'},el('h3',{},el('span',{text:n.rotulo}),el('span',{class:'tag',text:`${int.format(n.ocorrencias)} registros`})));
  if(n.taxa_100k_ano==null){card.append(el('p',{class:'muted',text:`${n.mensagem[0].toUpperCase()}${n.mensagem.slice(1)}.`}))}
  else{const max=Math.max(n.taxa_100k_ano,n.taxa_municipal_100k_ano||0)||1;
   const linha=(rotulo,valor,cls)=>{const f=el('div',{class:'fill '+cls});f.style.width=(100*valor/max)+'%';return el('div',{class:'bar'},el('span',{text:rotulo}),el('div',{class:'track','role':'img','aria-label':`${rotulo}: ${num.format(valor)} por 100 mil por ano`},f),el('span',{class:'value',text:num.format(valor)}))};
   card.append(el('div',{class:'pair'},linha('Este distrito',n.taxa_100k_ano,'district'),linha('Cidade',n.taxa_municipal_100k_ano,'city')));
   const anos=Object.entries(n.taxa_por_ano).map(([a,t])=>`${a}: ${num.format(t)}`).join(' · ');
   card.append(el('p',{class:'trend'},el('strong',{text:TENDENCIA[n.tendencia]||''}),el('span',{class:'muted',text:` (${anos})`})))}
  grid.append(card)}}
function renderFontes(fontes){const ul=$('lista-fontes');ul.replaceChildren();for(const f of fontes||[]){const data=f.data_referencia?new Date(f.data_referencia+'T12:00:00').toLocaleDateString('pt-BR'):'sem data';const li=el('li',{},el('a',{href:f.url,target:'_blank',rel:'noreferrer',text:f.fonte}),` — ${f.descricao}: ${data}${f.observacao?' ('+f.observacao+')':''}${f.licenca?'. Licença '+f.licenca:''}.`);if(f.aviso)li.append(el('strong',{text:` Aviso: ${f.aviso}.`}));ul.append(li)}}
async function render(r,soPesos){const d=r.diagnostico;state.dados=r;state.distrito=r.local.distrito;
 $('resultado').hidden=false;$('fora').hidden=true;
 const titulo=state.endereco?[state.endereco.logradouro,state.endereco.bairro].filter(Boolean).join(', ')||`CEP ${state.endereco.cep}`:'Ponto escolhido no mapa';
 $('local-titulo').textContent=titulo;$('local-distrito').textContent=`Distrito: ${state.distrito.nome}`;
 $('local-aviso').textContent=state.endereco?'A localização obtida pelo CEP é aproximada: ela identifica o distrito, mas não a posição exata do imóvel.':'Diagnóstico do ponto clicado no mapa.';
 renderProximidade(d.proximidade);renderVitalidade(d.vitalidade);renderOcorrencias(d.ocorrencias);renderFontes(r.fontes);
 if(!soPesos)await desenharMapa(d)}

// ---------- consulta (RF15: resultado e erros na região viva) ----------
async function diagnosticar(alvo,soPesos=false){
 const pedido=++state.pedido;const q=new URLSearchParams(pesos());
 if(alvo.cep)q.set('cep',alvo.cep);else{q.set('lat',alvo.lat.toFixed(6));q.set('lon',alvo.lon.toFixed(6))}
 $('consultar').disabled=true;anunciar(soPesos?'Recalculando os índices com as novas prioridades…':'Consultando o diagnóstico…');
 try{const r=await getJSON('/api/diagnostico?'+q);if(pedido!==state.pedido)return;
  if(alvo.cep){state.endereco=r.local.endereco||null}
  if(!r.diagnostico&&!alvo.cep&&state.dados){anunciar(`${r.aviso} Escolha um ponto dentro da cidade.`,true);return}
  if(!r.diagnostico){$('resultado').hidden=true;$('fora').hidden=false;$('fora-texto').textContent=`${r.aviso}${r.local.endereco?' ('+[r.local.endereco.logradouro,r.local.endereco.municipio].filter(Boolean).join(', ')+')':''} O diagnóstico cobre apenas os 96 distritos da capital.`;anunciar(r.aviso,true);return}
  state.lat=r.local.latitude;state.lon=r.local.longitude;
  await render(r,soPesos);
  const d=r.diagnostico;anunciar(`${soPesos?'Índices recalculados':'Diagnóstico concluído'} para o distrito ${state.distrito.nome}: proximidade ${d.proximidade.ipl==null?'sem dados':num.format(d.proximidade.ipl)}, vitalidade ${num.format(d.vitalidade.ivep)}, de 100.`);
  if(!soPesos){$('local-titulo').focus();if(alvo.cep)history.replaceState(null,'',`?cep=${alvo.cep}`)}
 }catch(e){if(pedido===state.pedido)anunciar(e.message,true)}
 finally{if(pedido===state.pedido)$('consultar').disabled=false}}

$('cep').addEventListener('input',e=>{const d=e.target.value.replace(/\D/g,'').slice(0,8);e.target.value=d.length>5?`${d.slice(0,5)}-${d.slice(5)}`:d});
$('form').addEventListener('submit',e=>{e.preventDefault();const cep=$('cep').value.replace(/\D/g,'');if(cep.length!==8){anunciar('O CEP deve ter 8 números.',true);$('cep').focus();return}diagnosticar({cep})});
const inicial=new URLSearchParams(location.search).get('cep');if(inicial){$('cep').value=inicial;$('cep').dispatchEvent(new Event('input'));diagnosticar({cep:inicial.replace(/\D/g,'')})}
