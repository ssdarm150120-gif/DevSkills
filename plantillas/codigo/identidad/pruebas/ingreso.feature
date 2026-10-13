# language: es
# HU de ejemplo del esqueleto: iniciar sesión de forma segura. Si tu SRS la ajusta, los escenarios
# se cambian aqui TAL CUAL y luego las pruebas.
Característica: Autenticación con contraseña

  Escenario: Ingreso correcto
    Dado que tengo un rol que no exige segundo factor
    Cuando ingreso mi correo corporativo y mi contraseña correctos
    Entonces entro a la aplicación con los permisos de mis roles
    Y el ingreso queda registrado

  Escenario: No se revela si el correo existe
    Cuando intento ingresar con un correo que no existe
    Entonces veo "Correo o contraseña incorrectos"
    Y es el mismo mensaje que al ingresar un correo existente con una contraseña incorrecta
    Y el intento queda registrado

  Escenario: Bloqueo por intentos fallidos
    Cuando fallo la contraseña 5 veces seguidas
    Entonces la cuenta se bloquea 15 minutos y el intento queda registrado
    Y el bloqueo aplica a la cuenta, sin importar desde dónde se intente

  Escenario: Falla cerrado para los roles que exigen segundo factor
    Dado que tengo un rol que exige segundo factor (Administrador o Auditor)
    Y el segundo factor todavía no está disponible o no lo he completado
    Cuando ingreso mi correo y mi contraseña correctos
    Entonces no entro a la aplicación
    Y veo "Tu rol requiere un segundo factor para ingresar"
    Y el intento queda registrado

  Escenario: Sesión inactiva
    Cuando paso 3 horas sin actividad
    Entonces la sesión se cierra y tengo que volver a ingresar
    Y mientras tenga actividad y no se cumpla la duración máxima, la sesión no se cierra por inactividad

  Escenario: Duración máxima de la sesión
    Dado que ingresé hace 12 horas y seguí trabajando sin interrupciones
    Cuando hago una petición
    Entonces la sesión se cierra y vuelvo a la pantalla de ingreso

  Escenario: Contraseña robusta
    Cuando defino mi contraseña
    Entonces debe tener al menos 12 caracteres y no puede estar en la lista de contraseñas filtradas incluida en el sistema
    Y la validación no envía la contraseña a ningún servicio externo

  Escenario: Contraseña temporal en el primer ingreso
    Dado que el administrador me dio una contraseña temporal
    Cuando ingreso con ella
    Entonces lo único que puedo hacer es definir una contraseña nueva
    Y la contraseña temporal deja de servir

  Escenario: Cambiar mi propia contraseña
    Dado que inicié sesión
    Cuando proporciono mi contraseña actual y una nueva que cumple las reglas
    Entonces mi contraseña cambia, mis demás sesiones se cierran y el cambio queda registrado
