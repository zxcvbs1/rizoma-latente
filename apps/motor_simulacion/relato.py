"""
El artefacto de historia portátil (06_motor_simulacion extensión, jul 2026):
el dueño de una corrida se lleva SU relato como un archivo HTML autocontenido
para guardar y pasar de mano en mano. El nodo lo RENDERIZA, no lo hostea ni
lo persiste (INV-07 intacto: es la copia del dueño, no un store que la
retiene). Se arma ANTES de cerrar la corrida: el transcript muere con ella,
igual que corrida_transcript. Sin CSS ni JS externos, sin identidades: solo
roles, ronda y el acto que dejó cada uno (patrón apps/espejo/pagina.py).
"""
from apps.motor_simulacion import motor as motor_sim


def _esc(valor) -> str:
    texto = str(valor if valor is not None else "")
    return (texto.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace('"', "&quot;"))


def render_relato_html(corrida_id: str, db) -> str:
    """Arma el HTML legible del transcript vivo de UNA corrida: título con el
    marco, cada ronda como sección, cada acto con su rol y su descripción.
    Exige corrida ABIERTA (misma restricción que corrida_transcript): el
    relato muere al cerrar."""
    datos = motor_sim.transcript_de(db, corrida_id)
    corrida = motor_sim._corrida_abierta(db, corrida_id)
    marco = corrida.marco

    por_ronda: dict = {}
    for acto in datos["actos"]:
        por_ronda.setdefault(acto["ronda"], []).append(acto)

    secciones = []
    for ronda in sorted(por_ronda):
        actos_html = "".join(
            f'<div class="acto"><span class="rol">{_esc(a["rol"])}</span>'
            f'<p>{_esc(a["descripcion"])}</p></div>'
            for a in por_ronda[ronda])
        secciones.append(f'<section class="ronda"><h2>ronda {ronda}</h2>{actos_html}</section>')

    if not datos["actos"]:
        cuerpo = (
            '<div class="aviso-vacio"><strong>Esta corrida no registró ningún '
            'acto en el nodo:</strong> la engine no fue servida (nadie '
            'respondió sus pedidos) o se cerró antes de correr. Si un GM te '
            'contó una historia de esta corrida, esa historia no pasó por '
            'acá.</div>')
    else:
        cuerpo = "".join(secciones)

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>relato: {_esc(marco)}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ background: #101012; color: #d8d4cc; font: 17px/1.65 Georgia, serif;
         max-width: 760px; margin: 0 auto; padding: 2.5rem 1.2rem 6rem; }}
  h1 {{ font-size: 1.5rem; font-weight: normal; letter-spacing: .08em; margin-bottom: .3rem; }}
  .nota {{ color: #6f6a60; font-size: .82rem; margin-bottom: 2.5rem; }}
  section.ronda {{ margin-bottom: 2rem; border-top: 1px solid #26262a; padding-top: 1rem; }}
  section.ronda h2 {{ font-size: .9rem; font-weight: normal; color: #8b7f5f;
                      letter-spacing: .12em; text-transform: uppercase; margin-bottom: .9rem; }}
  .acto {{ margin-bottom: 1.1rem; }}
  .acto .rol {{ color: #7d96a8; font-size: .85rem; letter-spacing: .03em;
               display: block; margin-bottom: .25rem; }}
  .acto p {{ color: #e8e2d6; }}
  .vacio {{ color: #6f6a60; font-style: italic; }}
  .aviso-vacio {{ background: #241a1a; border: 1px solid #6b3a3a; border-left: 4px solid #b85c5c;
                  color: #e8d6d6; padding: 1.1rem 1.3rem; margin-top: 1.5rem; font-size: 1rem; }}
  .aviso-vacio strong {{ color: #e8b9b9; }}
</style>
</head>
<body>
<h1>una corrida bajo el marco: {_esc(marco)}</h1>
<p class="nota">tu copia; el nodo no la retiene (INV-07). guardala local o pasala de mano en mano.</p>
{cuerpo}
</body>
</html>"""
