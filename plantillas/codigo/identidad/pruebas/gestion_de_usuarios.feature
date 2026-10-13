# language: es
# HU de gestion de usuarios y roles (cimiento del esqueleto). Los escenarios siguen la HU de ejemplo
# del SRS; si tu SRS los ajusta, se cambian aqui TAL CUAL y luego las pruebas.
Característica: Usuarios y roles

  Escenario: Usuario con varios roles
    Cuando creo a "Ana" con los roles "Auditor" y "Usuario"
    Entonces Ana ve las colas y las acciones de los dos roles

  Escenario: Desactivar, no borrar
    Cuando desactivo a un usuario que dejó la empresa
    Entonces ya no puede entrar
    Y sus acciones pasadas siguen en la bitácora con su nombre
    Y lo asignado a su nombre en otros modulos se libera por el bus de eventos

  Escenario: Alta con correo corporativo y contraseña temporal
    Cuando doy de alta a "Ana" con su correo corporativo
    Entonces el sistema genera una contraseña temporal para entregársela
    Y Ana tiene que cambiarla en su primer ingreso
    Y el alta queda en la bitácora, sin guardar la contraseña

  Escenario: Correo repetido
    Cuando intento dar de alta a un usuario con un correo que ya tiene otro usuario
    Entonces el sistema no lo permite

  Escenario: Restablecer la contraseña
    Dado que "Ana" olvidó su contraseña
    Cuando restablezco su contraseña
    Entonces su contraseña anterior deja de servir y recibe otra temporal que debe cambiar al ingresar
    Y el restablecimiento queda en la bitácora con quién lo hizo, sobre qué usuario y cuándo

  Escenario: Reiniciar el segundo factor
    Dado que "Luis", auditor, perdió su dispositivo
    Cuando reinicio su segundo factor
    Entonces su registro anterior deja de servir y Luis se vuelve a enrolar en su siguiente ingreso
    Y el reinicio queda en la bitácora

  Escenario: Desbloquear una cuenta
    Dado que la cuenta de "Ana" está bloqueada por 5 intentos fallidos
    Cuando la desbloqueo
    Entonces Ana puede ingresar sin esperar los 15 minutos
    Y el desbloqueo queda en la bitácora

  Escenario: Sin autoservicio de recuperación
    Cuando un usuario olvida su contraseña
    Entonces la pantalla de ingreso no ofrece recuperarla por correo
    Y le indica que la solicite al administrador

  Escenario: Un administrador no recupera su propia cuenta
    Dado que tengo el rol "Administrador"
    Cuando intento restablecer mi propia contraseña o reiniciar mi propio segundo factor desde la gestión de usuarios
    Entonces el sistema no lo permite y me indica que debe hacerlo otro administrador

  Escenario: Un administrador cambia sus propios roles
    Dado que tengo el rol "Administrador"
    Cuando me agrego o me quito otros roles
    Entonces el cambio se aplica y queda en la bitácora
    Y no puedo quitarme el rol "Administrador" ni desactivarme

  Escenario: Siempre queda un administrador activo
    Dado que desactivar a un administrador o quitarle el rol dejaría al sistema sin administradores activos
    Cuando intento hacerlo
    Entonces el sistema no lo permite y me indica que debe quedar al menos un administrador activo

  Escenario: Aviso de un solo administrador
    Dado que solo queda un administrador activo
    Cuando abro la gestión de usuarios
    Entonces veo un aviso que recomienda tener al menos dos administradores

  Escenario: Correo con caracteres no permitidos
    Cuando intento dar de alta a un usuario con un correo que tiene acentos, "ñ" u otros caracteres no permitidos
    Entonces el sistema no lo permite y me indica qué caracteres se aceptan
