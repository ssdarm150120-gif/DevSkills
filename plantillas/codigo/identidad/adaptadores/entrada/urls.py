from django.urls import path

from identidad.adaptadores.entrada import vistas, vistas_usuarios

urlpatterns = [
    path("", vistas.inicio, name="inicio"),
    path("ingresar", vistas.ingresar, name="ingresar"),
    path("ingresar/contrasena", vistas.contrasena_obligatoria, name="contrasena_obligatoria"),
    path("ingresar/enrolar", vistas.enrolar_segundo_factor, name="enrolar_segundo_factor"),
    path("ingresar/codigo", vistas.pedir_codigo, name="pedir_codigo"),
    path("salir", vistas.salir, name="salir"),
    path("cuenta/contrasena", vistas.cambiar_contrasena, name="cambiar_contrasena"),
    path("estilos/identidad.css", vistas.estilos, name="estilos_identidad"),
    # Gestion de usuarios: solo el Administrador; las acciones son POST con CSRF.
    path("admin/usuarios", vistas_usuarios.lista_usuarios, name="lista_usuarios"),
    path("admin/usuarios/nuevo", vistas_usuarios.nuevo_usuario, name="nuevo_usuario"),
    path(
        "admin/usuarios/<uuid:usuario_id>", vistas_usuarios.detalle_usuario, name="detalle_usuario"
    ),
    path(
        "admin/usuarios/<uuid:usuario_id>/editar",
        vistas_usuarios.editar_usuario,
        name="editar_usuario",
    ),
    path(
        "admin/usuarios/<uuid:usuario_id>/desactivar",
        vistas_usuarios.desactivar_usuario,
        name="desactivar_usuario",
    ),
    path(
        "admin/usuarios/<uuid:usuario_id>/reactivar",
        vistas_usuarios.reactivar_usuario,
        name="reactivar_usuario",
    ),
    path(
        "admin/usuarios/<uuid:usuario_id>/restablecer",
        vistas_usuarios.restablecer_contrasena,
        name="restablecer_contrasena",
    ),
    path(
        "admin/usuarios/<uuid:usuario_id>/segundo-factor/reiniciar",
        vistas_usuarios.reiniciar_segundo_factor,
        name="reiniciar_segundo_factor",
    ),
    path(
        "admin/usuarios/<uuid:usuario_id>/desbloquear",
        vistas_usuarios.desbloquear_cuenta,
        name="desbloquear_cuenta",
    ),
]
