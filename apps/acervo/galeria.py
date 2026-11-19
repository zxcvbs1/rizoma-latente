"""
La galería del acervo (03_comunidad §6, INV-08; WP-08 extensión, jul 2026):
el visualizador COLECTIVO. Lo persistente y enlazable de la obra no son las
historias (de cada quien, efímeras, se sueltan como un sueño): son las formas
despersonalizadas que la comunidad destiló y adoptó (tensión-tipo, injerto,
lente), cada una con su linaje y su masa de adopción. Cada forma ya tiene su
id, que ES su enlace compartible. Público por construcción: GET /formas ya
es público (WP-09), esta galería solo lo hace legible de un vistazo (patrón
apps/espejo/pagina.py). Self-contained, sin dependencias externas.
"""
from apps.acervo import acervo


def _esc(valor) -> str:
    texto = str(valor if valor is not None else "")
    return (texto.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace('"', "&quot;"))


def render_galeria_html(db) -> str:
    """Arma la galería HTML de las formas PUBLICADAS: nombre, tipo, marco,
    cuerpo, masa de adopción y linaje (bifurcaciones) como enlaces laterales."""
    formas = acervo.listar_formas(db)  # incluir_retiradas=False: solo publicadas

    hijas: dict = {}
    for f in formas:
        if f.get("linaje"):
            hijas.setdefault(f["linaje"], []).append(f["id"])

    if not formas:
        cuerpo = ('<p class="vacio">el acervo todavía está vacío: las formas llegan '
                  'cuando una comunidad decide publicarlas.</p>')
    else:
        tarjetas = []
        for f in formas:
            enlaces = []
            if f.get("linaje"):
                enlaces.append(
                    f'<span class="lateral">&uarr; viene de <code>{_esc(f["linaje"])}</code></span>')
            for hija_id in hijas.get(f["id"], []):
                enlaces.append(
                    f'<span class="lateral">&darr; bifurcada en <code>{_esc(hija_id)}</code></span>')
            barra = min(100.0, float(f.get("masa") or 0.0) * 12)
            cuerpo_forma = (f'<p class="cuerpo">{_esc(f["cuerpo"])}</p>' if f.get("cuerpo") else "")
            tarjetas.append(f'''
      <div class="carta" id="f-{_esc(f["id"])}">
        <div class="tipo">{_esc(f["tipo"].replace("_", " "))} &middot; {_esc(f["marco"])}</div>
        <h3>{_esc(f["nombre"])}</h3>
        <p>{_esc(f["descripcion"])}</p>
        {cuerpo_forma}
        <div class="barra" title="masa de adopci&oacute;n"><div style="width:{barra}%"></div></div>
        <div class="meta">
          <span>id: <code>{_esc(f["id"])}</code></span>
          <span>{_esc(f["procedencia"])}</span>
          <span>consentida por {_esc(f["regla_consentimiento"])}</span>
          {" ".join(enlaces)}
        </div>
      </div>''')
        cuerpo = "".join(tarjetas)

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>la galer&iacute;a del acervo</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ background: #101012; color: #d8d4cc; font: 15px/1.55 Georgia, serif;
         max-width: 880px; margin: 0 auto; padding: 2rem 1.2rem 6rem; }}
  h1 {{ font-size: 1.4rem; font-weight: normal; letter-spacing: .12em; margin-bottom: .3rem; }}
  .nota {{ color: #6f6a60; font-size: .8rem; margin-bottom: 2rem; }}
  .carta {{ border: 1px solid #26262a; border-radius: 10px; padding: 1rem 1.2rem;
           margin-bottom: 1rem; }}
  .carta h3 {{ font-size: 1rem; font-weight: normal; color: #e8e2d6; }}
  .cuerpo {{ color: #b5afa4; font-size: .88rem; margin-top: .4rem; white-space: pre-wrap; }}
  .meta {{ color: #6f6a60; font-size: .75rem; margin-top: .5rem; }}
  .meta span {{ margin-right: 1rem; }}
  .meta code {{ color: #9a938a; }}
  .tipo {{ color: #8b7f5f; font-size: .7rem; letter-spacing: .14em; text-transform: uppercase; }}
  .lateral {{ color: #7d96a8; }}
  .barra {{ background: #1c1c20; border-radius: 4px; height: 6px; overflow: hidden; margin-top: .35rem; }}
  .barra div {{ background: #8b7f5f; height: 100%; }}
  .vacio {{ color: #6f6a60; font-style: italic; padding: 2rem 0; }}
</style>
</head>
<body>
<h1>la galer&iacute;a del acervo</h1>
<p class="nota">lo colectivo que sobrevive al olvido: patrones destilados y adoptados por la
comunidad, no historias de nadie. cada forma tiene su id, que es su enlace.</p>
{cuerpo}
</body>
</html>"""
