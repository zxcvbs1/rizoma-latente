"""
La gramática de las resonancias (WP-28): los comandos viven por uso.
Gramaticalización: cada emisión que porta un !comando le suma masa.
Desgramaticalización: el barrido nocturno apaga los que nadie usa (INV-03).
El vocabulario del nodo es sedimento del habla de su comunidad.
"""
import datetime

COMANDO_MAX_LARGO = 24


def _ahora():
    return datetime.datetime.now(datetime.timezone.utc)


def comando_valido(slug: str) -> bool:
    """Un comando NOMBRA un gesto en una palabra: corto, alfanumérico
    (guiones bajos ok), sin identidades. Un slug inválido no bloquea la
    emisión: entra como deseo puro (sin comando), la lengua no censura."""
    from packages.domain import frontera
    s = (slug or "").strip().lower()
    return bool(s) and len(s) <= COMANDO_MAX_LARGO and \
        s.replace("_", "").isalnum() and not frontera.contiene_identidades(s)


def gramaticalizar(db, slug: str):
    """El uso escribe la masa. Upsert: comando nuevo nace con masa 1;
    existente suma 1 y renueva last_touched."""
    from packages.domain.models import ComandoVivo
    if not comando_valido(slug):
        return None
    s = slug.strip().lower()
    fila = db.query(ComandoVivo).filter(ComandoVivo.slug == s).first()
    if fila is None:
        fila = ComandoVivo(slug=s, mass=1.0)
        db.add(fila)
    else:
        fila.mass = float(fila.mass or 0.0) + 1.0
    fila.last_touched = _ahora()
    db.flush()
    return fila
