# Prompts para Figma Make: {{NOMBRE_PROYECTO}} (por sprint)

<!--
Lo escribe el analista con la skill devskills:prompts-figma, a partir del SRS (roles de 2.3, historias
del Anexo B, metas de 1.1.1) y del PLAN (entregas y sprints). Es SOLO la parte visual: prototipo
navegable con datos ficticios, sin backend. Se regenera el Word con md_a_word.py.
Orden de las secciones: encabezado, "Cómo usarlos", ruta rápida, prompts de actualización y de
correcciones (los más recientes primero), Prompt 0 (base) y los prompts por grupo de sprints.
-->

| Campo | Valor |
|-------|-------|
| Versión | 0.1 |
| Fecha | {{FECHA}} |
| Fuentes | `documentacion/SRS.md` <!-- X.Y -->, `documentacion/DISENO.md` <!-- X.Y -->, `documentacion/PLAN.md` <!-- X.Y --> |
| Alcance | **Solo la parte visual** (prototipo navegable con datos ficticios). No hay backend |

## Cómo usarlos
1. Abre **un solo archivo** de Figma Make y pega el **Prompt 0** (sistema de diseño, navegación y **datos ficticios**). Todo lo demás se construye encima.
2. Pega los prompts siguientes **en orden**. Cada uno corresponde a un **grupo de sprints** del plan e indica las historias (HU) que cubre, para que el prototipo crezca igual que el producto.
3. Si Figma Make se desvía, repite: *"Usa exclusivamente los DATOS FICTICIOS definidos en el Prompt 0 y el mismo sistema de diseño."*
4. Todos los datos son **ficticios**. No reemplazarlos por clientes, personas ni montos reales: los prototipos se comparten y se suben a la nube.

| Prompt | Sprints | Entrega | Pantallas |
|--------|---------|---------|-----------|
| 0 | — | — | Sistema de diseño, navegación por rol, datos ficticios |
| M | — | Maqueta de venta (opcional) | Todas las pestañas funcionales, modo claro y oscuro, recorrido de demo |
| 1 | <!-- S1 a Sn --> | 0. Cimientos | <!-- pantallas --> |
| <!-- n --> | <!-- sprints --> | <!-- entrega --> | <!-- pantallas --> |

### Ruta rápida para la maqueta de venta
Si el objetivo es **vender el proyecto** (y no prototipar sprint por sprint): pega el **Prompt 0**, después el **Prompt M** y al final los prompts de actualización (**R**) y de correcciones (**R2**) que existan, en ese orden.

---

<!--
Prompt de ACTUALIZACIÓN (R, R3...): cuando cambia el alcance (por ejemplo, una retrospectiva que sube
la versión del SRS), se escribe un prompt que se pega SOBRE la maqueta existente. Formato:

## Prompt R. Actualización de <motivo> (SRS X.Y)

> Pégalo **sobre la maqueta que ya tienes**, después del Prompt 0 y del Prompt M. El prompt hace N cosas: ...
>
> Cubre HU-nn a HU-nn.

```
Actualiza la maqueta actual de "{{NOMBRE_PROYECTO}}". Conserva el mismo sistema de diseño, los modos claro y oscuro, la navegación, y usa SOLO los DATOS FICTICIOS del Prompt 0 más los datos nuevos que vienen abajo. Toda la interfaz va en español de México. Es SOLO visual: no hay backend.

CAMBIO DE ENFOQUE: ...
1) DATOS NUEVOS (agrégalos a los del Prompt 0 y úsalos en todas las pantallas): ...
2) PANTALLAS NUEVAS: ...
3) QUITA: ...
```

Prompt de CORRECCIONES (R2...): cuando la maqueta contradice los requisitos. No agrega pantallas.

## Prompt R2. Correcciones a la maqueta después del Prompt R

> Pégalo **sobre la maqueta actual**. Corrige N puntos que contradicen los requisitos (SRS X.Y). No agrega pantallas nuevas.

```
Corrige la maqueta actual de "{{NOMBRE_PROYECTO}}". Conserva el sistema de diseño, los modos claro y oscuro, la navegación, el recorrido de demo y SOLO los DATOS FICTICIOS del Prompt 0 y del Prompt R. No agregues pantallas nuevas. Todo en español de México con tuteo.

1) <PANTALLA>: qué está mal según el SRS (cita el RF o la HU) y cómo debe quedar.
...
Al final revisa: <lista de verificación de lo corregido>.
```
-->

## Prompt M. Maqueta de venta: todas las pestañas funcionales, modo claro/oscuro y recorrido de demo

```
Sobre el prototipo actual (mismo sistema de diseño y SOLO los DATOS FICTICIOS del Prompt 0), convierte la maqueta en una DEMO DE VENTA completamente navegable. Todo es visual y en memoria (sin backend): cada acción cambia el estado en pantalla y muestra un aviso breve.

A) MODO CLARO Y OSCURO
- Interruptor sol/luna en la barra superior; por defecto sigue la preferencia del sistema y recuerda la elección.
- Define todo con variables (tokens): fondo, superficie, superficie elevada, borde, texto principal/secundario/atenuado, primario <!-- #RRGGBB --> (en oscuro, una variante más clara con contraste AA), y los semánticos en versión clara y oscura.
- Aplícalo a TODO: tablas, tarjetas, gráficos, insignias, modales. Ningún texto puede perder contraste en modo oscuro.

B) ROLES
- El selector de rol cambia la pantalla de Inicio y las pestañas visibles: <!-- rol: pestañas -->.
- Para la demo, arrancar como Administrador con todas las pestañas activas.

C) PESTAÑAS (todas funcionales)
1. INICIO: 4 indicadores por rol + lista de pendientes con enlaces.
<!-- 2. PESTAÑA: qué se puede hacer y qué cambia en pantalla -->

D) RECORRIDO DE DEMO
<!-- pasos del recorrido que cuenta la historia del problema de negocio (SRS 1.1.1) -->
```

---

## Prompt 0. Base: sistema de diseño, navegación y datos ficticios

```
Diseña el prototipo navegable de una aplicación web responsiva (escritorio primero, usable en tablet y celular) llamada "{{NOMBRE_PROYECTO}}". <!-- Qué es y para quién, en dos frases. -->

OBJETIVO DEL PRODUCTO: <!-- el problema de negocio del SRS 1.1.1 en una frase y la regla de negocio central -->

ROLES (con un selector de rol en la barra superior para la demo): <!-- roles del SRS 2.3 -->.

SISTEMA DE DISEÑO:
- Estilo de herramienta de trabajo, limpio y denso en información. Nada decorativo.
- Tipografía <!-- Inter -->; 14 px en tablas y listas.
- Colores: estructura en grises (slate); primario <!-- #RRGGBB --> para acciones. Semánticos: verde = listo, ámbar = en curso/por vencer, rojo = error/vencido, azul = información.
- Contraste AA. Cada pantalla con estado vacío, de carga y de error.
- Componentes: barra lateral colapsable; barra superior con buscador global, campana de notificaciones, selector de rol y avatar; tablas con filtros; insignias de estado; paneles laterales; modales de confirmación.

NAVEGACIÓN LATERAL (según el rol): <!-- pestañas -->.

DATOS FICTICIOS (usar SIEMPRE estos, en todas las pantallas):
<!-- Usuarios internos (nombre ficticio y rol), entidades principales del negocio con IDs con prefijo,
estados variados (uno en cada estado de las máquinas del DISEÑO D.3), montos y fechas coherentes.
Nunca datos reales. Los mismos datos los usan las pruebas de aceptación (qa-bdd). -->

Crea primero la estructura (barra lateral, barra superior) y una pantalla de INICIO por rol con 4 tarjetas de indicadores y la lista de pendientes de ese rol, usando estos datos.
```

---

## Prompt 1. Sprints <!-- S1 a Sn --> · Entrega 0: Cimientos
*Historias: <!-- HU-nn, HU-nn -->.*

```
Con el mismo sistema de diseño y los DATOS FICTICIOS del Prompt 0, diseña:

1) INICIO DE SESIÓN: correo y contraseña; segundo paso con código de 6 dígitos de una app autenticadora para los roles que lo exigen, con una pantalla de registro de la app (código QR y clave) en el primer ingreso; pantalla de cambio obligatorio de la contraseña temporal.

2) ADMINISTRACIÓN > USUARIOS: tabla de usuarios con roles (una persona puede tener varios), estado activo/inactivo y "Desactivar" (nunca borrar).

<!-- 3) PANTALLA: contenido, acciones, estados y reglas del SRS que debe mostrar (cita RF/HU) -->
```

---

<!-- ## Prompt n. Sprints Sx a Sy · Entrega k: <nombre>
*Historias: HU-nn a HU-nn.*
```
Con el mismo sistema de diseño y los DATOS FICTICIOS del Prompt 0, diseña:
1) ...
```
-->
