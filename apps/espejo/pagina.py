"""
La página pública del espejo (WP-09). Autocontenida, sin cuenta, sin búsqueda
por texto libre (v0, INV-09): se entra por formas, épocas o lengua y se
deambula por enlaces laterales. No hay nada que escribir: solo mirar.
"""

PAGINA_ESPEJO = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>el espejo</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body { background: #101012; color: #d8d4cc; font: 15px/1.55 Georgia, serif;
         max-width: 880px; margin: 0 auto; padding: 2rem 1.2rem 6rem; }
  h1 { font-size: 1.4rem; font-weight: normal; letter-spacing: .12em; margin-bottom: .3rem; }
  .nota { color: #6f6a60; font-size: .8rem; margin-bottom: 2rem; }
  nav { display: flex; gap: 1.4rem; margin-bottom: 2rem; border-bottom: 1px solid #26262a;
        padding-bottom: .7rem; }
  nav a { color: #9a938a; text-decoration: none; font-size: .85rem; letter-spacing: .08em;
          cursor: pointer; }
  nav a.activa { color: #e8e2d6; border-bottom: 1px solid #8b7f5f; padding-bottom: .68rem; }
  .carta { border: 1px solid #26262a; border-radius: 10px; padding: 1rem 1.2rem;
           margin-bottom: 1rem; }
  .carta h3 { font-size: 1rem; font-weight: normal; color: #e8e2d6; }
  .meta { color: #6f6a60; font-size: .75rem; margin-top: .5rem; }
  .meta span { margin-right: 1rem; }
  .tipo { color: #8b7f5f; font-size: .7rem; letter-spacing: .14em; text-transform: uppercase; }
  .lateral { color: #7d96a8; font-size: .78rem; cursor: pointer; }
  .barra { background: #1c1c20; border-radius: 4px; height: 6px; overflow: hidden; margin-top: .35rem; }
  .barra div { background: #8b7f5f; height: 100%; }
  .vacio { color: #6f6a60; font-style: italic; padding: 2rem 0; }
  table { width: 100%; border-collapse: collapse; }
  td, th { text-align: left; padding: .45rem .2rem; border-bottom: 1px solid #1e1e22;
           font-size: .85rem; }
  th { color: #6f6a60; font-weight: normal; font-size: .72rem; letter-spacing: .1em; }
</style>
</head>
<body>
<h1>el espejo</h1>
<p class="nota">se mira la maquinaria, nunca a alguien. sin cuenta, sin b&uacute;squeda por persona:
lo que este espejo no muestra es porque no existe en su capa.</p>
<nav>
  <a data-v="formas" class="activa">formas</a>
  <a data-v="epocas">&eacute;pocas</a>
  <a data-v="lengua">lengua</a>
  <a data-v="salud">salud</a>
</nav>
<main id="zona"><p class="vacio">cargando el com&uacute;n...</p></main>
<script>
const zona = document.getElementById('zona');
const tabs = document.querySelectorAll('nav a');
tabs.forEach(t => t.onclick = () => { tabs.forEach(x => x.classList.remove('activa'));
  t.classList.add('activa'); cargar(t.dataset.v); });

async function cargar(vista) {
  zona.innerHTML = '<p class="vacio">cargando...</p>';
  try {
    const r = await fetch('/espejo/' + vista);
    if (!r.ok) { zona.innerHTML = '<p class="vacio">el espejo se niega: ' + r.status +
      ' (si hay material con identidad en el store, no se sirve)</p>'; return; }
    render[vista](await r.json());
  } catch (e) { zona.innerHTML = '<p class="vacio">sin conexi&oacute;n con el nodo</p>'; }
}

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

const render = {
  formas(d) {
    if (!d.formas.length) { zona.innerHTML = '<p class="vacio">el acervo todav&iacute;a est&aacute; vac&iacute;o: las formas llegan cuando una comunidad decide publicarlas.</p>'; return; }
    const hijas = {}; d.linaje.forEach(l => (hijas[l.de] = hijas[l.de] || []).push(l.a));
    zona.innerHTML = d.formas.map(f => `
      <div class="carta" id="f-${esc(f.id)}">
        <div class="tipo">${esc(f.tipo.replace('_',' '))} &middot; ${esc(f.marco)}</div>
        <h3>${esc(f.nombre)}</h3>
        <p>${esc(f.descripcion)}</p>
        <div class="barra" title="masa"><div style="width:${Math.min(100, f.masa * 12)}%"></div></div>
        <div class="meta">
          <span>${esc(f.procedencia)}</span>
          <span>consentida por ${esc(f.regla_consentimiento)}</span>
          <span>licencia ${esc(f.licencia)}</span>
          ${f.linaje ? `<span class="lateral" onclick="ir('${esc(f.linaje)}')">&uarr; viene de otra forma</span>` : ''}
          ${(hijas[f.id]||[]).map(h => `<span class="lateral" onclick="ir('${esc(h)}')">&darr; alguien la torci&oacute;</span>`).join('')}
        </div>
      </div>`).join('');
  },
  epocas(d) {
    if (!d.epocas.length) { zona.innerHTML = '<p class="vacio">todav&iacute;a no hay &eacute;pocas.</p>'; return; }
    zona.innerHTML = '<table><tr><th>&eacute;poca</th><th>intenciones emitidas</th><th>formas publicadas</th></tr>' +
      d.epocas.map(e => `<tr><td>${esc(e.epoca)}</td><td>${e.intenciones}</td><td>${e.formas}</td></tr>`).join('') + '</table>';
  },
  lengua(d) {
    if (!d.lengua.length) { zona.innerHTML = '<p class="vacio">la lengua nace con el primer uso.</p>'; return; }
    zona.innerHTML = '<table><tr><th>comando</th><th>usos</th><th>masa</th></tr>' +
      d.lengua.map(l => `<tr><td>!${esc(l.comando)}</td><td>${l.usos}</td><td>${l.masa}</td></tr>`).join('') +
      '</table><p class="nota" style="margin-top:1rem">la lengua evoluciona por adopci&oacute;n y decay, no por decreto (INV-15).</p>';
  },
  async salud(d) {
    const t = d.prevision.tasa_acierto;
    let html = `<div class="carta"><div class="tipo">previsión global</div>
      <h3>${d.prevision.aciertos} aciertos sobre ${d.prevision.predicciones} predicciones${t !== null ? ' (tasa ' + t + ')' : ''}</h3>
      <p class="meta">${esc(d.prevision.lectura)}. agregado an&oacute;nimo: alarma, jam&aacute;s KPI.</p></div>`;
    try {
      const a = await (await fetch('/espejo/alarmas')).json();
      const carta = (titulo, s) => `<div class="carta" style="${s.alarma ? 'border-color:#a85c4a' : ''}">
        <div class="tipo">${titulo}${s.alarma ? ' &middot; ALARMA' : ''}</div>
        <p class="meta">${esc(s.lectura)}</p>
        ${s.serie.map(f => `<div class="meta"><span>${esc(f.mes)}</span>` +
          Object.entries(f).filter(([k]) => k !== 'mes').map(([k, v]) => `<span>${esc(k)}: ${v}</span>`).join('') +
          '</div>').join('')}
      </div>`;
      html += carta('surco / riel', a.surco_riel) + carta('absorci&oacute;n', a.absorcion);
      html += `<p class="nota">${esc(a.nota)}</p>`;
    } catch (e) {}
    zona.innerHTML = html;
  }
};

function ir(id) { const el = document.getElementById('f-' + id);
  if (el) { el.scrollIntoView({behavior:'smooth'}); el.style.borderColor = '#8b7f5f'; } }

cargar('formas');
</script>
</body>
</html>"""
