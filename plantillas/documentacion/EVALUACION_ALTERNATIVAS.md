# Manifiesto de evaluación: <!-- producto existente --> como base de {{NOMBRE_PROYECTO}}
## ADR-<!-- nnn --> · Comprar (<!-- producto -->) o construir (stack del esqueleto)

<!--
Plantilla de la skill devskills:evaluacion-alternativas. Se usa cuando alguien pregunta "¿por qué no
usamos <producto existente> en lugar de construirlo?". Una copia por producto evaluado
(EVALUACION_<PRODUCTO>.md, o renombra esta). Este documento NO cambia requisitos: el SRS sirve igual
para cualquier opción, porque dice qué hace el sistema y no con qué se construye.
La decisión final la toma el Product Owner y se registra como ADR en DISENO.md (D.1.6), aceptado o
rechazado, con referencia a este documento.
-->

| Campo | Valor |
|-------|-------|
| Versión | 1.0 |
| Fecha | {{FECHA}} |
| Autor | {{AUTOR}} |
| Estado | **Abierto** <!-- | Cerrado: Aceptado (AAAA-MM-DD) | Cerrado: Rechazado (AAAA-MM-DD) --> |
| Decide | Product Owner, con el equipo de desarrollo |
| Fecha límite propuesta | <!-- p. ej. fin del sprint 1 --> |
| Documentos relacionados | `documentacion/SRS.md` <!-- X.Y --> · `documentacion/DISENO.md` <!-- X.Y --> · `documentacion/PLAN.md` <!-- X.Y --> |

> **Propósito.** Dejar por escrito la pregunta "¿podemos montar {{NOMBRE_PROYECTO}} sobre <!-- producto --> en lugar de construirlo?", con sus hechos, su análisis y la forma de decidirlo con evidencia. Este documento **no cambia requisitos**.

> **Advertencia sobre los hechos del producto.** Lo que se dice de <!-- producto --> (módulos, licencias, ediciones) se basa en el conocimiento general del producto y **debe verificarse con la versión vigente** antes de decidir.

---

## 1. La pregunta

1. <!-- ¿Se puede instalar el producto y montar sobre él los sprints del proyecto? -->
2. <!-- ¿Se puede usar solo una parte del producto? -->

## 2. Opciones evaluadas

| Opción | Descripción |
|--------|-------------|
| **A. <!-- producto completo -->** | <!-- descripción --> |
| **B. <!-- solo una parte del producto -->** | <!-- descripción --> |
| **C. Construir con el stack del esqueleto** (diseño actual) | Monolito modular en Django según `DISENO.md` |
| **D. Híbrido** | <!-- el producto solo para una función que el SRS no cubre --> |

## 3. Qué es <!-- producto --> (hechos a verificar)

- <!-- arquitectura, lenguaje, framework propio o no -->
- <!-- ediciones y licencias -->
- <!-- qué trae de fábrica y qué no -->
- <!-- política de actualizaciones y migración de lo construido encima -->

## 4. El problema central: ¿quién es dueño de los datos?

<!-- Compara con las restricciones del SRS (fuentes de verdad, sistemas en solo lectura). Para cada
opción: ¿hay dos sistemas que creen ser dueños de lo mismo? Distingue un riesgo estructural de un
riesgo de implementación. -->

- **Opción A:** <!-- -->
- **Opción B:** <!-- -->
- **Opción C:** <!-- -->

## 5. Cobertura del SRS con <!-- opción B -->

| Módulo del SRS | ¿Lo cubre de fábrica? |
|----------------|-----------------------|
| <!-- módulo --> | <!-- ✅ Sí / ⚠️ A medias: ... / ❌ No: a medida --> |

**Estimación preliminar:** de las <!-- N --> historias del Anexo B, el producto resolvería de fábrica o casi de fábrica <!-- n -->; <!-- m --> seguirían siendo desarrollo a medida, ahora dentro del producto.

**Por qué esto importa:** <!-- ¿el producto ahorra lo fácil (lo que el esqueleto ya trae: usuarios, roles, segundo factor, administración) o lo difícil (las historias de mayor valor)? -->

## 6. Impacto en el proyecto si se elige <!-- producto -->

| Área | Impacto |
|------|---------|
| Requisitos (SRS) | **Ninguno.** Los requisitos y las historias no cambian |
| Diseño técnico (DISENO) | <!-- qué se rehace --> |
| Equipo | <!-- curva de aprendizaje --> |
| Mantenimiento | <!-- migraciones por versión del producto --> |
| Licencias | <!-- costo por usuario o por año --> |
| Plan (PLAN) | Se regenera con la estimación nueva |

## 7. Cuándo <!-- producto --> sí sería la mejor opción

- <!-- condiciones del negocio en que conviene -->

## 8. Cómo se decide: spike de <!-- 2 semanas -->

**Objetivo:** reemplazar la opinión por evidencia del propio equipo.

**Pasos:**
1. Levantar <!-- la parte mínima del producto --> en Docker (con el prefijo y el rango de puertos del proyecto).
2. Implementar **una sola historia difícil** en las dos opciones: <!-- HU-nn -->.
3. Probar <!-- el punto crítico de la sección 4 -->.
4. Cotizar <!-- licencias -->.
5. Medir las horas reales de cada opción y completar la matriz de la sección 9.

**Entregable:** este documento con la sección 10 completa, y el ADR actualizado en `DISENO.md` como "Aceptado" o "Rechazado".

## 9. Criterios de decisión

| Criterio | Peso | Opción B | Opción C |
|----------|------|----------|----------|
| Encaje con las fuentes de verdad del SRS | <!-- 25 % --> | *Completar con el spike* | *Completar con el spike* |
| Tiempo hasta la primera entrega con valor | <!-- 20 % --> | | |
| Cobertura de fábrica de las historias | <!-- 15 % --> | | |
| Costo total a 3 años (licencias + desarrollo + migraciones) | <!-- 15 % --> | | |
| Conocimiento del equipo y curva de aprendizaje | <!-- 10 % --> | | |
| Riesgo de dependencia del proveedor y de las actualizaciones | <!-- 10 % --> | | |
| Seguridad y autohospedaje (DISENO D.6) | <!-- 5 % --> | | |
| **Total ponderado (escala 1 a 5)** | 100 % | | |

## 10. Recomendación y decisión

- **Recomendación actual:** <!-- opción y motivos -->
- **Decisión (<!-- AAAA-MM-DD -->):** <!-- ADR-nnn ACEPTADO / RECHAZADO. Decisión del Product Owner, con o sin spike, y por qué. Qué se reabre y cuándo. -->

## Historial de cambios
| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0 | {{FECHA}} | Manifiesto inicial: opciones, hechos a verificar, propiedad de los datos, cobertura del SRS, impacto, criterios y spike |
