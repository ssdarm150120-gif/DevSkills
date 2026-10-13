"""Ver el aviso por reuso de un codigo del segundo factor (HU de aviso por reuso; D.3.10).

Se llama al abrir la pantalla de inicio, es decir, DESPUES del ingreso completo (contrasena y, si el
rol lo exige, segundo factor): jamas en las etapas intermedias. Solo mira los intentos del propio
actor. Si hay intentos de reuso que el usuario aun no ha visto, devuelve el aviso con el mas
reciente y deja la marca de "visto" en el ID de ESE intento: los anteriores quedan vistos con el, y
uno nuevo que llegue entre la lectura y la marca tiene un id mayor y sigue pendiente. La marca
no usa el reloj, por eso este caso de uso no recibe uno, y nunca retrocede.

Debe correr en una transaccion (la abre quien lo llama). Casi todas las aperturas del inicio NO
tienen aviso pendiente, asi que primero se lee SIN bloqueo; solo si hay un pendiente se bloquea la
fila del usuario y se COMPRUEBA DE NUEVO: dos pestañas que abren el inicio a la vez no muestran el
aviso dos veces, y el resto de las lecturas no se turna con nadie.
"""

from dataclasses import dataclass

from identidad.aplicacion.puertos import AvisosDeReuso, ZonaHoraria
from identidad.dominio.aviso_reuso import AvisoDeReuso
from nucleo.actor import Actor


@dataclass(frozen=True, slots=True)
class AvisosPendientes:
    avisos: AvisosDeReuso
    zona: ZonaHoraria

    def __call__(self, actor: Actor) -> AvisoDeReuso | None:
        # 1. Sin bloqueo: lo normal es que no haya nada que mostrar.
        visto = self.avisos.marca(actor.id)
        if self.avisos.ultimo_intento_de_reuso(actor.id, despues_de=visto) is None:
            return None
        # 2. Hay un pendiente: se toma el bloqueo y se vuelve a mirar (otra pestaña pudo ganar).
        visto = self.avisos.bloquear_marca(actor.id)
        ultimo = self.avisos.ultimo_intento_de_reuso(actor.id, despues_de=visto)
        if ultimo is None:
            return None
        self.avisos.marcar_visto(actor.id, hasta_id=ultimo.id)
        return AvisoDeReuso(ultimo.ocurrido_en, self.zona.zona())
