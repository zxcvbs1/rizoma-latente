"""
Compilación CLIENTE-LADO de un patrón de coordinación (WP-32).

La distinción que este ejemplo encarna (01_red §7.2, INV-18/19):

- Lo que circula por el común es el PATRÓN: prosa declarativa, publicada en el
  acervo, legible por cualquiera. Jamás código.
- Lo que cada cliente hace con esa prosa es SUYO: puede leerla tal cual, puede
  dársela a su modelo como rúbrica, o puede compilarla localmente a andamiaje
  ejecutable como este (Pydantic para parametrizar el flujo). Este archivo es
  lo que cualquier modelo puede regenerar leyendo el patrón; vive del lado del
  cliente y nunca viaja al acervo ni al nodo.
- El andamiaje PREPARA propuestas de emisión; no emite. Cada emisión con
  consecuencia pasa por el camino de siempre: la persona la confirma y su
  llave la firma (INV-01). Un campo del modelo lo hace imposible de olvidar:
  `requiere_confirmacion` solo acepta True.

Correr la demo (sin servicios):
    .venv/bin/python examples/andamiaje_cliente_patron.py
"""
from typing import Literal

from pydantic import BaseModel, Field

# El patrón fuente, tal como se sirve del acervo (GET /formas/{id}/rubrica,
# envuelto como dato). Se cita acá para que el ejemplo sea autocontenido.
PATRON_PRESTAMO = (
    "Patrón de préstamo. Pasos: quien tiene algo para prestar lo dice "
    "con sus palabras (!presto y el objeto); quien lo necesita lo pide "
    "(!busco). Cuando la resonancia los junta y ambos se dirigen la "
    "palabra, quien presta declara la expectativa: qué presta y para "
    "cuándo espera la devolución, dicho en la conversación. El "
    "recordatorio del plazo lo lleva el cliente de cada quien, como "
    "nota propia. La devolución se anuncia como una intención más "
    "(!devuelvo y el objeto) y cierra el ciclo. La expectativa que no "
    "se cumple decae en silencio: nadie anota deudas de nadie.")


class PropuestaEmision(BaseModel):
    """Un paso del patrón, compilado: un TEXTO CANDIDATO a emisión. No es una
    emisión: es lo que el cliente le muestra a la persona para que ella
    confirme (o reescriba con sus palabras) antes de que la llave firme."""
    texto: str = Field(min_length=1)
    momento: Literal["ahora", "al_coordinar", "al_plazo"]
    requiere_confirmacion: Literal[True] = True  # sin excepción posible


class NotaLocal(BaseModel):
    """Lo que el patrón asigna al CLIENTE, no a la red: el recordatorio del
    plazo es una nota propia. Nunca se emite, nunca sale de esta máquina."""
    texto: str
    dias_desde_coordinacion: int = Field(gt=0)


class ParametrosPrestamo(BaseModel):
    """La parametrización del flujo: lo único que la persona completa."""
    objeto: str = Field(min_length=1, description="qué se presta, en sus palabras")
    plazo_dias: int = Field(default=7, gt=0, le=365,
                            description="para cuándo se espera la devolución")


def compilar_prestamo(params: ParametrosPrestamo) -> dict:
    """Del patrón (prosa) + parámetros (Pydantic) a la secuencia del flujo:
    propuestas de emisión (cada una espera la confirmación de la persona) y
    la nota local del recordatorio (que jamás se emite)."""
    return {
        "emisiones_propuestas": [
            PropuestaEmision(
                texto=f"!presto {params.objeto}",
                momento="ahora"),
            PropuestaEmision(
                texto=(f"declaro la expectativa: espero la devolución de "
                       f"{params.objeto} en {params.plazo_dias} días"),
                momento="al_coordinar"),
            PropuestaEmision(
                texto=f"!devuelvo {params.objeto}",
                momento="al_plazo"),
        ],
        "notas_locales": [
            NotaLocal(
                texto=f"recordar la devolución de {params.objeto}",
                dias_desde_coordinacion=params.plazo_dias),
        ],
        "patron_fuente": PATRON_PRESTAMO,
    }


if __name__ == "__main__":
    plan = compilar_prestamo(ParametrosPrestamo(objeto="taladro", plazo_dias=10))
    print("Flujo compilado del patrón 'préstamo con devolución declarada':\n")
    for propuesta in plan["emisiones_propuestas"]:
        print(f"  [{propuesta.momento:13}] {propuesta.texto}")
        assert propuesta.requiere_confirmacion is True
    for nota in plan["notas_locales"]:
        print(f"  [nota local   ] {nota.texto} "
              f"(a los {nota.dias_desde_coordinacion} días; no se emite)")
    print("\nNada de esto se emitió: son propuestas. La persona confirma "
          "cada una con su palabra y recién ahí la llave firma.")
