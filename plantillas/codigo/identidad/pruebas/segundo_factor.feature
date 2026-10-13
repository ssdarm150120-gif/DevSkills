# language: es
# HU de ejemplo del esqueleto: usar el segundo factor para los roles sensibles. Si tu SRS la ajusta,
# los escenarios se cambian aqui TAL CUAL y luego las pruebas.
Característica: Segundo factor

  Escenario: Segundo factor para roles sensibles
    Dado que tengo un rol que exige segundo factor (Administrador o Auditor)
    Cuando ingreso mi contraseña correcta
    Entonces el sistema me pide un código de un segundo factor (aplicación autenticadora)
    Y sin ese código no se abre la sesión

  Escenario: Enrolamiento en el primer ingreso
    Dado que tengo un rol que exige segundo factor y todavía no lo he registrado
    Cuando ingreso mi contraseña correcta
    Entonces el sistema me muestra un código QR y una clave para registrar mi aplicación de códigos
    Y el enrolamiento termina cuando capturo un código válido
    Y queda registrado

  Escenario: Código correcto
    Dado que ya registré mi aplicación de códigos
    Cuando ingreso mi contraseña y el código vigente
    Entonces entro a la aplicación con los permisos de mis roles

  Escenario: Límite de intentos del código
    Cuando capturo 5 códigos incorrectos seguidos
    Entonces la cuenta se bloquea 15 minutos y los intentos quedan registrados

  Escenario: Un código no se acepta dos veces
    Dado que ya ingresé con el código "123456"
    Cuando alguien intenta ingresar con ese mismo código dentro de su vigencia
    Entonces el sistema lo rechaza

  Escenario: Rol sensible asignado después
    Dado que el administrador me asignó el rol "Auditor"
    Cuando vuelvo a ingresar
    Entonces tengo que enrolar mi segundo factor antes de entrar

  Escenario: Reinicio por el administrador
    Dado que el administrador reinició mi segundo factor porque perdí mi dispositivo
    Cuando ingreso mi contraseña correcta
    Entonces mi registro anterior ya no sirve y tengo que enrolarme de nuevo
