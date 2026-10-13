# language: es
# HU de ejemplo del esqueleto: enterarme si alguien intentó reusar mi código. Si tu SRS la ajusta,
# los escenarios se cambian aqui TAL CUAL y luego las pruebas.
Característica: Aviso por reuso del segundo factor

  Escenario: Aviso en el siguiente ingreso
    Dado que alguien intentó entrar a mi cuenta con un código del segundo factor que ya se había usado
    Cuando ingreso y completo mi segundo factor
    Entonces veo un aviso con la fecha y hora del intento
    Y el aviso me indica que cambie mi contraseña y avise al administrador si no fui yo

  Escenario: El aviso se muestra una sola vez
    Dado que ya vi el aviso de un intento de reuso
    Cuando vuelvo a ingresar
    Entonces no veo el aviso otra vez

  Escenario: Sin intentos de reuso no hay aviso
    Dado que nadie intentó reusar un código mío
    Cuando ingreso
    Entonces no veo ningún aviso

  Escenario: El intento queda en la bitácora
    Cuando alguien intenta entrar con un código del segundo factor ya usado
    Entonces el sistema lo rechaza
    Y el intento queda en la bitácora de auditoría, visible para el administrador
