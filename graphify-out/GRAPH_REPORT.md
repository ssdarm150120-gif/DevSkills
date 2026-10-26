# Graph Report - DevSkills  (2026-10-26)

## Corpus Check
- 281 files · ~192,605 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 20 file(s) not represented in the graph (top: (none) 14, .feature 4, .template 1)

## Summary
- 3932 nodes · 9719 edges · 210 communities (141 shown, 69 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 1323 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2f604c86`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Actor
- test_escenarios_gestion_de_usuarios.py
- test_despliegue.py
- composicion.py
- AccionDeCuenta
- test_outbox.py
- test_puertos.py
- test_confirmar_codigo.py
- Usuario
- test_eventos_identidad.py
- usuarios.py
- composicion.py
- Despachador
- test_eventos.py
- test_escenarios_segundo_factor.py
- test_definir_contrasena.py
- test_aviso_reuso_adaptador.py
- test_endurecimiento.py
- test_escenarios_ingreso.py
- test_aviso_reuso_concurrencia.py
- hash_ficticio
- MonkeyPatch
- test_escenarios_aviso_por_reuso.py
- generar_presentacion.js
- Etapa
- test_roles_bd.py
- vistas_usuarios.py
- vistas.py
- test_outbox_ronda2.py
- CuentasEnMemoria
- test_settings.py
- test_contratos_importlinter.py
- test_segundo_factor_adaptador.py
- puertos/__init__.py
- Documento de Diseño de Software (SDD)
- md_a_word.py
- test_aviso_reuso.py
- Especificación de Requisitos de Software (SRS)
- AvisoDeReuso
- crear_proyecto.py
- configuracion/pruebas/test_adaptadores.py
- pathlib
- steps
- ResultadoCodigo
- CifradoDeSecretos
- RepositorioCuentas
- identidad/pruebas/test_adaptadores.py
- sys
- test_segundo_factor_concurrencia.py
- cli_spec.sh
- test_sonda_salud.py
- test_entorno.py
- test_dominio_puro.py
- django_core_exceptions
- lento
- subprocess
- Capacidad
- test_aislamiento_pgdata.py
- CIERRE-S{NN} · Cierre de calidad del sprint {NN}
- esquemas.py
- test_imports_dinamicos.py
- updates
- {{NOMBRE_PROYECTO}}: codigo
- test_dominio_roles.py
- despachador.py
- README.md
- test_si_una_escritura_del_reinicio_falla_no_queda_nada_a_medias
- test_filtro_eventos.py
- validar_contrasena
- middleware.py
- attributes
- salida/segundo_factor.py
- test_clientes_prohibidos.py
- P.1 Marco de trabajo
- spec_helper.sh
- body
- [Sin publicar]
- EncabezadoCSPMiddleware
- test_actor.py
- Critical Patterns
- Instalación
- Reglas que no se negocian
- with
- test_gestion_usuarios_base.py
- Manifiesto de evaluación: <!-- producto existente --> como base de {{NOMBRE_PROYECTO}}
- Critical Patterns
- judgment-day/SKILL.md
- Cómo contribuir a DevSkills
- ServicioContrasenasDjango
- entorno.py
- _cargar
- identidad/adaptadores/entrada/__init__.py
- Critical Patterns
- ci.yml
- exportar_sesion.py
- roles_bd.py
- Critical Patterns
- Critical Patterns
- Critical Patterns
- Critical Patterns
- hosts_permitidos_de_produccion
- contrasenas.py
- Critical Patterns
- Critical Patterns
- Critical Patterns
- pruebas
- Contexto del proyecto: {{NOMBRE_PROYECTO}}
- Critical Patterns
- proyecto-contexto/SKILL.md
- gitleaks_spec.sh
- install.sh script
- test_esqueleto_modulos.py
- .de
- Prompts para Figma Make: {{NOMBRE_PROYECTO}} (por sprint)
- Critical Patterns
- PULL_REQUEST_TEMPLATE.md
- jobs
- tasks.py
- _ZonaConHtml
- datetime
- evaluacion-alternativas/SKILL.md
- verificador
- Generadores de contenido
- Uso no interactivo
- Skills
- Stack
- _nombre_completo
- test_dependencias_reproducibles.py
- trazo_del_qr
- ctx
- _TextoFalso
- Equipo de agentes de {{NOMBRE_PROYECTO}}
- Critical Patterns
- plan_sprints_spec.sh
- qa.md
- verificador.md
- main
- Trabajar por Telegram
- contact_links
- esqueleto
- todo-en-verde
- test_roles_de_ejemplo.py
- Command
- test_el_conteo_del_bloqueo_no_pierde_intentos_concurrentes
- espia_de_argon2
- exportar_sesion_spec.sh
- analista-arquitecto.md
- angel-fixer.md
- dev-a.md
- dev-b.md
- ctx
- test_un_actor_sin_roles_no_tiene_ninguno
- 📦 Instalación
- install_ps1_spec.sh
- vetar_acciones_externas.sh
- falsos
- contexto_de_la_aplicacion
- ZonaFalsa
- guarda-todo/SKILL.md
- hook_spec.sh
- dev-integraciones.md
- dev-interfaz.md
- dev-servicios.md
- orquestador.md
- qa-bdd.md
- qa-no-funcional.md
- dev-dominio.md
- install_spec.sh
- limpiar_carpetas
- generar_certificado.sh
- admin
- avance/README.md
- CLAUDE.md
- {{SLUG}}

## God Nodes (most connected - your core abstractions)
1. `Usuario` - 260 edges
2. `Actor` - 132 edges
3. `AccionDeCuenta` - 78 edges
4. `Motivo` - 62 edges
5. `_cargar_prod()` - 60 edges
6. `Etapa` - 56 edges
7. `RepositorioCuentasDjango` - 53 edges
8. `Entorno` - 53 edges
9. `RegistroDeConsumidores` - 49 edges
10. `VerificadorTotp` - 47 edges

## Surprising Connections (you probably didn't know these)
- `1. Dónde vive cada dato (nada se escribe a mano en el backlog)` --references--> `inicio()`  [INFERRED]
  skills/planear-entregas/SKILL.md → plantillas/codigo/identidad/adaptadores/entrada/vistas.py
- `Agregado` --references--> `verificador()`  [INFERRED]
  CHANGELOG.md → plantillas/codigo/identidad/pruebas/test_segundo_factor_adaptador.py
- `Ciclo de calidad híbrido (decisión del Product Owner del método)` --references--> `verificador()`  [INFERRED]
  CHANGELOG.md → plantillas/codigo/identidad/pruebas/test_segundo_factor_adaptador.py
- `👥 Agentes` --references--> `verificador()`  [INFERRED]
  README.md → plantillas/codigo/identidad/pruebas/test_segundo_factor_adaptador.py
- `Paso 3. Reglas que siempre se revisan antes de entregar` --references--> `Actor`  [INFERRED]
  skills/implementar-historia/SKILL.md → plantillas/codigo/nucleo/actor.py

## Import Cycles
- None detected.

## Communities (210 total, 69 thin omitted)

### Community 0 - "Actor"
Cohesion: 0.06
Nodes (54): ReinicioAtomico, ConsultarUsuarios, EstadoSegundoFactor, CrearUsuario, EditarUsuario, ConflictoDeUsuario, CuentaNoDisponible, PermisoDenegado (+46 more)

### Community 1 - "test_escenarios_gestion_de_usuarios.py"
Cohesion: 0.06
Nodes (74): AccionCuenta, Meta, _abro_la_gestion(), _accion(), _actor_de(), _alta(), _alta_de_ana(), _alta_en_bitacora() (+66 more)

### Community 2 - "test_despliegue.py"
Cohesion: 0.04
Nodes (57): llave_segundo_factor_de_produccion(), _directivas_de_nginx(), _docker(), _flujo(), _generar_certificado(), imagen_openssl(), _pasos_de_despliegue(), _san_de() (+49 more)

### Community 3 - "composicion.py"
Cohesion: 0.08
Nodes (13): CasoCrearUsuario, CasoEditarUsuario, CatalogoDeRolesDjango, DetalleDeUsuario, CrearAdministrador, UsuarioCreado, ResultadoEdicion, exigir_que_quede_administrador() (+5 more)

### Community 4 - "AccionDeCuenta"
Cohesion: 0.06
Nodes (45): RegistroDeAccesosDjango, ConfirmarCodigo, intento(), DefinirContrasena, eventos_de_accion(), agregar(), eventos_de_intento(), identificador_de_evento() (+37 more)

### Community 5 - "test_outbox.py"
Cohesion: 0.07
Nodes (45): entregas_en_error(), estado_de_la_cola(), reintentar(), EntregaOutbox, Meta, EventoOutbox, Meta, _agotar() (+37 more)

### Community 6 - "test_puertos.py"
Cohesion: 0.04
Nodes (33): conectar(), conectar_bus_de_eventos(), conectar_segundo_factor(), ConfiguracionConfig, test_conectar_rechaza_un_adaptador_de_un_puerto_no_declarado(), test_el_segundo_factor_se_conecta_una_sola_vez(), sin_consumidores_fugados(), Aislamiento (+25 more)

### Community 7 - "test_confirmar_codigo.py"
Cohesion: 0.09
Nodes (44): ResultadoConfirmacion, EtapaInvalida, RequiereSegundoFactor, Entorno, _iniciar(), _reiniciar(), test_bloqueada_ni_el_codigo_correcto_pasa_y_ni_se_consulta_al_verificador(), test_cinco_codigos_incorrectos_seguidos_bloquean_la_cuenta_quince_minutos() (+36 more)

### Community 8 - "Usuario"
Cohesion: 0.09
Nodes (46): Usuario, Meta, _bueno(), con_codigo_pendiente(), con_enrolamiento_pendiente(), _ingresar(), _malo(), test_cada_etapa_rota_la_clave_de_sesion() (+38 more)

### Community 9 - "test_eventos_identidad.py"
Cohesion: 0.09
Nodes (34): _accion(), _intento_fallido(), _nombres(), _nombres_publicados(), obtener_publicador(), _publicados(), test_cada_accion_de_cuenta_produce_al_menos_un_evento_valido_y_sin_datos_prohibidos(), test_cambiar_los_datos_dice_que_campos_cambiaron() (+26 more)

### Community 10 - "usuarios.py"
Cohesion: 0.13
Nodes (19): correo_corporativo_valido(), DatosDeUsuario, UsuarioInvalido, validar_correo(), validar_datos(), validar_nombre(), validar_roles(), _datos() (+11 more)

### Community 11 - "composicion.py"
Cohesion: 0.09
Nodes (25): _atomico(), confirmar_codigo(), consultar_usuarios(), crear_administrador(), crear_usuario(), definir_contrasena(), desactivar_usuario(), desbloquear_cuenta() (+17 more)

### Community 12 - "Despachador"
Cohesion: 0.07
Nodes (32): Despachador, evento_de(), PublicadorDeEventosDjango, test_no_se_suscribe_dos_veces_el_mismo_consumidor_ni_a_un_evento_desconocido(), test_se_busca_la_suscripcion_por_nombre(), test_un_consumidor_recibe_solo_los_eventos_a_los_que_se_suscribio(), test_un_evento_sin_consumidores_no_tiene_suscripciones(), _en_hilo() (+24 more)

### Community 13 - "test_eventos.py"
Cohesion: 0.07
Nodes (29): _evento(), test_agotados_los_cinco_reintentos_pasa_a_error(), test_el_catalogo_deja_escrito_que_motivos_de_cierre_de_sesion_se_emiten_hoy(), test_el_limite_de_envios_manda_su_propia_espera(), test_el_momento_debe_traer_zona_y_ser_utc(), test_el_payload_del_evento_no_comparte_el_diccionario_de_quien_lo_creo(), test_el_payload_solo_admite_valores_de_json(), test_faltar_un_campo_requerido_se_rechaza() (+21 more)

### Community 14 - "test_escenarios_segundo_factor.py"
Cohesion: 0.14
Nodes (36): IntentoIngreso, Meta, _alguien_repite_el_codigo(), _bloqueada_y_registrada(), _cinco_codigos_incorrectos(), _clave_en(), _codigo(), _codigo_vigente() (+28 more)

### Community 15 - "test_definir_contrasena.py"
Cohesion: 0.09
Nodes (34): AltaInvalida, ContrasenaActualIncorrecta, ContrasenaInvalida, ResultadoDefinicion, _alta(), _con_temporal(), Entorno, entorno() (+26 more)

### Community 16 - "test_aviso_reuso_adaptador.py"
Cohesion: 0.05
Nodes (45): avisos_pendientes(), AvisosDeReusoDjango, _marca_de(), ZonaHorariaDeConfiguracion, entrar(), _con_aviso(), _forma(), _hay_for_update() (+37 more)

### Community 17 - "test_endurecimiento.py"
Cohesion: 0.09
Nodes (40): _alta(), _etapa(), _hash_con_parametros_viejos(), _ingresar(), _sensibles(), test_cambiar_el_sello_invalida_todas_las_sesiones_del_usuario(), test_changepassword_del_servidor_cierra_las_sesiones_abiertas(), test_con_adaptador_si_cambian_los_roles_con_la_etapa_abierta_a_uno_sensible_va_al_enrolamiento() (+32 more)

### Community 18 - "test_escenarios_ingreso.py"
Cohesion: 0.11
Nodes (41): _bloqueada(), _bloqueo_por_cuenta(), _cambiar(), _cambio(), _cambio_completo(), _cinco_fallos(), _con_temporal(), _correo_inexistente() (+33 more)

### Community 19 - "test_aviso_reuso_concurrencia.py"
Cohesion: 0.16
Nodes (9): _en_un_hilo(), _insertar_intento(), _limpiar(), _pedir_aviso(), test_dos_pestanas_a_la_vez_muestran_el_aviso_una_sola_vez(), _abrir_el_inicio(), test_un_intento_que_llega_entre_la_lectura_y_la_marca_no_se_pierde(), _usuario_con_un_reuso() (+1 more)

### Community 20 - "hash_ficticio"
Cohesion: 0.14
Nodes (4): AuditoriaConfig, hash_ficticio(), IdentidadConfig, NucleoConfig

### Community 21 - "MonkeyPatch"
Cohesion: 0.09
Nodes (46): _cargar_prod(), test_el_codigo_de_settings_no_menciona_localhost_5432(), test_el_middleware_csp_va_justo_despues_de_securitymiddleware(), test_el_middleware_de_identidad_va_despues_de_la_autenticacion(), test_prod_acepta_hosts_validos(), test_prod_acepta_un_hsts_corto_solo_en_la_propia_maquina_y_lo_advierte(), test_prod_acepta_una_secret_key_de_exactamente_50_caracteres_con_variedad(), test_prod_advierte_si_se_apaga_la_redireccion_en_la_propia_maquina() (+38 more)

### Community 22 - "test_escenarios_aviso_por_reuso.py"
Cohesion: 0.10
Nodes (26): reloj(), RelojAdelantable, _alguien_intenta_con_un_codigo_usado(), _alguien_intento_reusar(), ctx(), _el_sistema_lo_rechaza(), _ingresar_con_codigo(), _ingreso() (+18 more)

### Community 23 - "generar_presentacion.js"
Cohesion: 0.05
Nodes (40): D, DATOS_RUTA, Fi, fs, icono(), iconoEnCirculo(), MAESTRO, MESES (+32 more)

### Community 24 - "Etapa"
Cohesion: 0.11
Nodes (33): IniciarSesion, Etapa, cuenta(), VerificadorEnMemoria, test_el_cuenta_dataclass_sigue_siendo_inmutable(), Entorno, entorno(), test_bloqueada_ni_la_contrasena_correcta_entra_sin_importar_el_origen() (+25 more)

### Community 25 - "test_roles_bd.py"
Cohesion: 0.24
Nodes (16): _aprovisionar(), _ejecutar(), Entorno, entorno(), test_aprovisionar_es_idempotente_y_repara_lo_que_ya_existe(), test_aprovisionar_sin_la_tabla_del_catalogo_no_falla(), test_de_punta_a_punta_migra_con_el_rol_dueno_y_la_aplicacion_solo_hace_dml(), test_el_rol_de_migraciones_es_el_dueno_de_la_base() (+8 more)

### Community 26 - "vistas_usuarios.py"
Cohesion: 0.20
Nodes (15): _actor(), _administracion(), desactivar_usuario(), desbloquear_cuenta(), detalle_usuario(), editar_usuario(), accion(), _ejecutar() (+7 more)

### Community 27 - "vistas.py"
Cohesion: 0.10
Nodes (19): _abrir_sesion(), cambiar_contrasena(), _confirmar(), _continuar(), contrasena_obligatoria(), _definir(), _en_transaccion(), enrolar_segundo_factor() (+11 more)

### Community 28 - "test_outbox_ronda2.py"
Cohesion: 0.12
Nodes (28): FabricaDePublicadoresDjango, purgar(), _crear(), _evento(), _quedan(), Reloj, test_dry_run_cuenta_sin_borrar(), test_el_comando_de_purga_tiene_dry_run() (+20 more)

### Community 29 - "CuentasEnMemoria"
Cohesion: 0.05
Nodes (8): _a_cuenta(), _consulta(), FilaDeUsuario, Cuenta, AccesosEnMemoria, ContrasenasFalsas, CuentasEnMemoria, RelojFalso

### Community 30 - "test_settings.py"
Cohesion: 0.07
Nodes (27): _cargar_con_base(), _directivas(), _ejecutar_sin_settings(), test_celery_ejecuta_tareas_en_modo_eager(), test_check_deploy_con_las_variables_de_prueba_no_da_advertencias(), test_check_deploy_falla_con_una_secret_key_debil_sin_que_prod_la_rechace(), test_dev_con_redis_usa_el_broker_y_la_cache_reales(), test_dev_sin_redis_corre_celery_en_modo_local_y_cache_en_memoria() (+19 more)

### Community 31 - "test_contratos_importlinter.py"
Cohesion: 0.08
Nodes (22): test_las_migraciones_crean_un_esquema_por_modulo(), main(), generar(), _lista(), main(), orden_sin_ciclos(), _contratos_de_juguete(), _crear_proyecto() (+14 more)

### Community 32 - "test_segundo_factor_adaptador.py"
Cohesion: 0.15
Nodes (38): SegundoFactor, Meta, codigo_del_paso(), VerificadorTotp, paso_de(), enrolado(), _enrolar(), _secreto_de() (+30 more)

### Community 33 - "puertos/__init__.py"
Cohesion: 0.06
Nodes (20): elegir(), elegir_en_desarrollo(), EspecificacionEvento, ConsumidorRepetido, Suscripcion, _clave_prohibida(), emisor_autorizado(), EmisorNoAutorizado (+12 more)

### Community 34 - "Documento de Diseño de Software (SDD)"
Cohesion: 0.05
Nodes (42): D.0.1 Propósito, D.0.2 Alcance, D.0.3 Definiciones, acrónimos y glosario, D.0.4 Referencias, D.0.5 Partes interesadas y preocupaciones, D.0 Introducción, D.1.1 Principios, D.1.2 Módulos (+34 more)

### Community 35 - "md_a_word.py"
Cohesion: 0.07
Nodes (25): Corregido, actualizar_campos_al_abrir(), agregar_texto(), borde_parrafo(), campo(), codigo(), convertir(), documentos() (+17 more)

### Community 36 - "test_aviso_reuso.py"
Cohesion: 0.23
Nodes (16): AvisosEnMemoria, _actor(), _caso(), test_con_un_intento_pendiente_devuelve_el_aviso_con_su_momento(), test_con_varios_intentos_muestra_el_mas_reciente_y_da_por_vistos_los_anteriores(), test_el_aviso_sale_una_sola_vez(), test_el_orden_es_el_del_id_y_no_el_de_la_fecha(), test_la_marca_es_el_id_del_intento_mostrado() (+8 more)

### Community 37 - "Especificación de Requisitos de Software (SRS)"
Cohesion: 0.05
Nodes (41): 1.1.1 Problema de negocio (la necesidad real), 1.1.2 Contexto para la dirección (no son requisitos), 1.1 Propósito, 1.2 Alcance, 1.3 Definiciones, acrónimos y abreviaturas, 1.4 Referencias, 1. Introducción, 2.1 Perspectiva del producto (+33 more)

### Community 38 - "AvisoDeReuso"
Cohesion: 0.09
Nodes (9): AvisosPendientes, AvisosDeReuso, ZonaHoraria, AvisoDeReuso, test_al_terminar_el_horario_de_verano_dos_instantes_distintos_no_se_ven_iguales(), test_el_cambio_de_dia_por_la_zona_se_respeta(), test_el_mensaje_es_el_del_requisito(), test_el_momento_se_muestra_en_la_zona_configurada_con_dia_mes_anio() (+1 more)

### Community 40 - "crear_proyecto.py"
Cohesion: 0.10
Nodes (18): copiar(), crear(), describir_idioma(), ErrorDeCreacion, fijar_localizacion(), iniciar_git(), git(), leer_puertos() (+10 more)

### Community 41 - "configuracion/pruebas/test_adaptadores.py"
Cohesion: 0.09
Nodes (24): elegir_en_produccion(), PuertoElegible, _Cargador, _compose(), entorno_prod(), test_al_arrancar_se_conecta_el_verificador_del_segundo_factor(), test_desarrollo_acepta_un_adaptador_real_por_variable(), test_desarrollo_usa_los_falsos_por_defecto() (+16 more)

### Community 42 - "pathlib"
Cohesion: 0.09
Nodes (12): _asegurar_zonas_horarias(), django_db_modify_db_settings(), redis_falso(), url_base_de_datos(), nombre_unico(), _sesion_de_pytest(), test_dos_sesiones_de_pytest_a_la_vez_sobre_el_mismo_servidor_pasan(), test_dos_sesiones_obtienen_nombres_distintos() (+4 more)

### Community 43 - "steps"
Cohesion: 0.06
Nodes (33): concurrency, cancel-in-progress, group, env, environment, permissions, runs-on, steps (+25 more)

### Community 44 - "ResultadoCodigo"
Cohesion: 0.11
Nodes (17): decidir_codigo(), normalizar_codigo(), pasos_de_la_ventana(), ResultadoCodigo, test_el_mismo_codigo_no_se_acepta_dos_veces_aunque_siga_vigente(), test_el_paso_no_depende_de_la_zona_horaria(), test_el_primer_codigo_se_acepta_y_guarda_su_paso(), test_la_ventana_acepta_el_paso_anterior_el_vigente_y_el_siguiente() (+9 more)

### Community 45 - "CifradoDeSecretos"
Cohesion: 0.12
Nodes (16): CifradoDeSecretos, SecretoIlegible, _cifrado(), registrar_segundo_factor(), _registrar(), test_cada_cifrado_usa_un_nonce_distinto(), test_el_algoritmo_coincide_con_los_vectores_del_rfc_6238(), test_el_cifrado_ida_y_vuelta_y_no_deja_el_secreto_en_claro() (+8 more)

### Community 46 - "RepositorioCuentas"
Cohesion: 0.06
Nodes (7): CuentaBloqueada, revalidar_etapa(), IniciarEnrolamiento, Enrolamiento, RepositorioCuentas, VerificadorSegundoFactor, test_el_secreto_del_enrolamiento_no_sale_en_el_repr()

### Community 47 - "identidad/pruebas/test_adaptadores.py"
Cohesion: 0.04
Nodes (31): AdministradorDeUsuarios, _opciones(), Rol, Meta, UsuarioRol, Meta, huella_de_correo(), admin_cliente() (+23 more)

### Community 48 - "sys"
Cohesion: 0.09
Nodes (7): formatear_porcentaje(), expandir(), lista(), orden(), salir(), frontmatter(), main()

### Community 49 - "test_segundo_factor_concurrencia.py"
Cohesion: 0.12
Nodes (12): _borrar_usuario(), _crear_usuario_de_finanzas(), _en_hilo(), _correr(), _simultaneos(), _simultaneos_con_clientes(), test_dos_get_simultaneos_a_enrolar_ven_la_misma_clave_y_se_crea_un_solo_secreto(), test_el_mismo_codigo_en_hilos_simultaneos_sin_transaccion_externa_solo_lo_acepta_uno() (+4 more)

### Community 50 - "cli_spec.sh"
Cohesion: 0.09
Nodes (8): devskills(), g(), init_con_correo(), preparar_falso(), preparar_update(), publicar_segunda_version(), punto_de_control(), cli_spec.sh script

### Community 51 - "test_sonda_salud.py"
Cohesion: 0.11
Nodes (11): _Servidor, servidor_200(), test_el_host_de_la_sonda_es_el_primero_de_allowed_hosts(), test_la_sonda_consulta_salud_con_host_y_esquema_de_nginx(), test_la_sonda_devuelve_cero_si_nadie_escucha(), test_la_sonda_devuelve_el_estado_si_no_es_200(), test_main_sale_con_0_si_salud_responde_200_y_con_1_si_no(), test_sin_allowed_hosts_la_sonda_usa_localhost() (+3 more)

### Community 52 - "test_entorno.py"
Cohesion: 0.13
Nodes (21): booleana(), entero(), requerida(), texto(), zona_horaria(), test_booleana(), test_booleana_invalida_falla(), test_entero_lee_el_valor_del_entorno() (+13 more)

### Community 53 - "test_dominio_puro.py"
Cohesion: 0.14
Nodes (12): archivos_de_dominio(), imports_no_permitidos(), test_el_detector_acepta_stdlib_pura_nucleo_y_el_propio_modulo(), test_el_detector_rechaza_imports_con_io_o_de_otros_modulos(), test_hay_dominios_que_vigilar(), test_la_prueba_falla_ante_un_intruso_en_un_dominio_real(), test_ningun_dominio_importa_algo_fuera_de_la_lista_blanca(), _archivos_de_produccion() (+4 more)

### Community 54 - "django_core_exceptions"
Cohesion: 0.08
Nodes (3): Command, Command, Command

### Community 55 - "lento"
Cohesion: 0.16
Nodes (18): _compose(), desarrollo(), _sin_docker(), test_compose_certificado_solo_conserva_chown(), test_compose_el_outbox_tiene_su_cola_propia_y_un_solo_beat(), test_compose_endurece_los_contenedores_y_aisla_la_red_de_datos(), test_compose_incluye_los_contenedores_de_esta_etapa_y_ninguno_de_otros_elementos(), test_compose_la_aplicacion_arranca_despues_de_las_migraciones() (+10 more)

### Community 56 - "subprocess"
Cohesion: 0.14
Nodes (10): test_el_actor_se_importa_desde_nucleo_sin_cargar_ningun_modulo_ni_django(), test_el_proceso_de_base_local_no_toca_el_directorio_de_pruebas(), test_el_generador_imprime_exactamente_el_archivo_sin_traducir_el_fin_de_linea(), archivos_del_repo(), buscar_gitleaks(), comando_de(), docker_responde(), elegir_modo() (+2 more)

### Community 57 - "Capacidad"
Cohesion: 0.25
Nodes (11): Capacidad, capacidades_de(), puede(), _actor(), test_solo_el_administrador_gestiona_usuarios(), test_solo_el_rol_de_ejemplo_auditor_tiene_la_capacidad_de_ejemplo(), test_toda_capacidad_la_tiene_algun_rol(), test_toda_capacidad_tiene_su_descripcion_para_la_pantalla() (+3 more)

### Community 58 - "test_aislamiento_pgdata.py"
Cohesion: 0.15
Nodes (9): _acepta_conexiones(), _levantar_dev_en_otro_proceso(), _matar_huerfanos(), _procesos_postgres_de(), _sin_postgres_huerfanos(), test_con_el_mismo_directorio_el_servidor_de_pruebas_si_apagaba_el_de_dev(), test_detener_el_servidor_de_pruebas_no_apaga_al_de_desarrollo(), test_el_barrido_de_huerfanos_mata_un_postgres_que_nadie_apago() (+1 more)

### Community 59 - "CIERRE-S{NN} · Cierre de calidad del sprint {NN}"
Cohesion: 0.08
Nodes (21): 1. Elementos del sprint, 2. QA de cierre, 3. Lista congelada y rondas, 4. Verificación final, 5. Decisiones y trabajo derivado (sin deuda técnica), 6. Preguntas abiertas para el Product Owner, CIERRE-S{NN} · Cierre de calidad del sprint {NN}, 1. Qué se implementó (+13 more)

### Community 60 - "esquemas.py"
Cohesion: 0.14
Nodes (10): Migration, Migration, crear_esquema(), nombre_tabla(), validar_identificador(), Migration, test_crear_esquema_es_idempotente_y_reversible(), test_nombre_tabla_califica_con_el_esquema() (+2 more)

### Community 61 - "test_imports_dinamicos.py"
Cohesion: 0.17
Nodes (15): _archivos_de_negocio(), archivos_vigilados(), es_codigo_vigilado(), _ruff(), test_el_detector_ast_no_da_falsos_positivos(), test_el_detector_ast_reconoce_cada_forma_de_import_dinamico(), test_el_filtro_ast_solo_exime_pruebas_de_primer_nivel(), test_hay_codigo_de_negocio_que_vigilar() (+7 more)

### Community 62 - "updates"
Cohesion: 0.09
Nodes (22): patterns, update-types, patterns, actions, compose, imagenes, python-menores, dependency-name (+14 more)

### Community 63 - "{{NOMBRE_PROYECTO}}: codigo"
Cohesion: 0.09
Nodes (21): Base de datos: el rol de la aplicacion no es dueno del esquema (D.6.3), Certificado TLS (autofirmado, solo desarrollo y pruebas), Dependencias reproducibles, Desarrollar sin Docker (el camino por defecto), Endurecimiento de los contenedores, Entorno de pruebas (staging, en localhost mientras no exista el servidor), Escaneres de seguridad (los mismos del CI), Gotchas conocidos (aprendidos en el proyecto de referencia) (+13 more)

### Community 64 - "test_dominio_roles.py"
Cohesion: 0.11
Nodes (12): exige_segundo_factor(), test_el_usuario_no_exige_segundo_factor(), test_un_rol_sensible_basta_para_exigir_el_segundo_factor(), test_un_usuario_sin_roles_no_exige_segundo_factor(), Cargar el dominio en el esqueleto (roles, módulos y contratos), Commands, Critical Patterns, Fase 1. Descubrimiento con el Product Owner (antes de crear nada) (+4 more)

### Community 65 - "despachador.py"
Cohesion: 0.05
Nodes (13): Migration, Migration, EstadoDeLaCola, ResumenDeCorrida, Migration, Migration, _opciones(), _candidatos() (+5 more)

### Community 66 - "README.md"
Cohesion: 0.13
Nodes (13): 👥 Agentes, 📋 Comandos del CLI, 🤝 Contribuir, 🔁 Cómo funciona el ciclo, 📚 Documentación, Ejemplo, 🖨️ Generadores de contenido, 🚀 Inicio rápido (+5 more)

### Community 68 - "test_filtro_eventos.py"
Cohesion: 0.25
Nodes (11): _con_clave(), _evento(), _purga(), test_cada_evasion_de_la_clave_se_rechaza(), test_configuracion_cambiada_exige_quien_y_que_cambio(), test_exportacion_realizada_exige_quien_que_y_filtros_sin_datos_personales(), test_las_claves_legitimas_del_catalogo_no_se_prohiben_por_parecerse(), test_los_valores_legitimos_pasan() (+3 more)

### Community 69 - "validar_contrasena"
Cohesion: 0.17
Nodes (12): validar_contrasena(), test_con_11_caracteres_se_rechaza_por_corta(), test_con_129_caracteres_se_rechaza_por_larga(), test_corta_y_filtrada_reporta_los_dos_motivos(), test_exactamente_128_caracteres_es_valida(), test_exactamente_12_caracteres_es_valida(), test_la_comparacion_con_la_lista_no_distingue_mayusculas(), test_los_espacios_de_los_bordes_no_cuentan_para_la_longitud() (+4 more)

### Community 72 - "attributes"
Cohesion: 0.11
Nodes (17): description, label, options, placeholder, render, value, body, attributes (+9 more)

### Community 73 - "salida/segundo_factor.py"
Cohesion: 0.10
Nodes (6): _derivar(), _filas(), uri_de_enrolamiento(), test_el_emisor_por_defecto_no_es_el_nombre_de_ninguna_empresa(), test_el_momento_de_creacion_del_secreto_viene_del_reloj_inyectado(), test_el_uri_lleva_el_emisor_de_la_configuracion_y_el_correo()

### Community 74 - "test_clientes_prohibidos.py"
Cohesion: 0.20
Nodes (10): clientes_sin_cubrir(), _forbidden_modules_de_dominio_puro(), nombres_de_requirements(), test_clientes_bd_http_cubiertos(), test_el_detector_falla_ante_un_cliente_no_cubierto(), test_el_detector_ignora_lo_que_no_es_un_cliente_y_las_lineas_de_inclusion(), test_el_detector_pasa_si_el_cliente_esta_en_la_lista(), test_las_dependencias_transitivas_no_cuentan() (+2 more)

### Community 75 - "P.1 Marco de trabajo"
Cohesion: 0.12
Nodes (16): Historial de cambios, {{NOMBRE_PROYECTO}}, P.1.1 Por qué Scrum (y no Kanban puro), P.1.2 Roles, P.1.3 Ceremonias, P.1.4 Estimación y capacidad, P.1.5 Definiciones de Listo y de Terminado, P.1.6 Herramientas (+8 more)

### Community 77 - "body"
Cohesion: 0.12
Nodes (15): description, label, options, value, body, attributes, id, type (+7 more)

### Community 78 - "[Sin publicar]"
Cohesion: 0.13
Nodes (14): [1.0.0] - 2026-10-13, Agregado, Agregado, Cadena de suministro, Cambiado, Cambios, Ciclo de calidad híbrido (decisión del Product Owner del método), Docker es opcional (+6 more)

### Community 79 - "EncabezadoCSPMiddleware"
Cohesion: 0.19
Nodes (6): test_el_middleware_csp_falla_si_la_politica_esta_vacia(), vista(), test_el_middleware_csp_no_pisa_un_encabezado_explicito_de_la_vista(), test_el_middleware_csp_usa_la_politica_estricta_si_no_hay_setting(), test_una_csp_vacia_fijada_por_la_vista_se_trata_como_ausente(), EncabezadoCSPMiddleware

### Community 80 - "test_actor.py"
Cohesion: 0.15
Nodes (17): _carga_manipulada(), test_dos_actores_iguales_son_iguales_y_hashables(), test_el_estado_manipulado_por_setstate_tampoco_entra_sin_validar(), test_el_identificador_no_puede_ser_vacio(), test_los_roles_no_pueden_ser_un_texto_suelto(), test_los_roles_no_se_pueden_modificar_en_el_lugar(), test_los_roles_se_copian_y_no_comparten_el_conjunto_original(), test_no_admite_atributos_nuevos() (+9 more)

### Community 81 - "Critical Patterns"
Cohesion: 0.13
Nodes (14): Critical Patterns, Modos, Patrón 1: solo fixes quirúrgicos (remediación y evaluación; la revisión por historia no corrige), Patrón 2: fixes seguros por tipo de vulnerabilidad, Patrón 3: verificación de cada fix, Patrón 4: reporte de remediación, Patrón 5: revisión del código — qué revisar (revisión por historia y evaluación), Patrón 6: reporte de evaluación (+6 more)

### Community 82 - "Instalación"
Cohesion: 0.14
Nodes (14): Actualizar, Actualizar los scripts de un proyecto ya creado, Como plugin de Claude Code, Correo del autor en el primer commit, Desinstalar, Docker es opcional, GitHub CLI (`gh`) y el CI, Instalación (+6 more)

### Community 83 - "Reglas que no se negocian"
Cohesion: 0.14
Nodes (14): Al cerrar el sprint, Cero deuda, Cierre, en este orden (cada merge y cada cierre de sprint), Documentos de un proyecto, El ciclo de calidad híbrido, Flujo completo de un proyecto, Idioma, secretos y entorno, La excepción: ciclo completo por historia (+6 more)

### Community 84 - "with"
Cohesion: 0.24
Nodes (14): steps, secretos, steps, steps, name, runs-on, steps, name (+6 more)

### Community 85 - "test_gestion_usuarios_base.py"
Cohesion: 0.09
Nodes (26): actor_de(), _actor(), _administradores_activos(), _dos_administradores(), _en_hilo(), _en_paralelo(), _Falla, fallar_registro() (+18 more)

### Community 86 - "Manifiesto de evaluación: <!-- producto existente --> como base de {{NOMBRE_PROYECTO}}"
Cohesion: 0.14
Nodes (13): 10. Recomendación y decisión, 1. La pregunta, 2. Opciones evaluadas, 3. Qué es <!-- producto --> (hechos a verificar), 4. El problema central: ¿quién es dueño de los datos?, 5. Cobertura del SRS con <!-- opción B -->, 6. Impacto en el proyecto si se elige <!-- producto -->, 7. Cuándo <!-- producto --> sí sería la mejor opción (+5 more)

### Community 87 - "Critical Patterns"
Cohesion: 0.14
Nodes (13): 1. Preparar, 2. Ciclo normal por elemento (revisión por historia; máximo 3 rondas), 3. Ciclo de la excepción (ciclo completo por historia; máximo 3 rondas), 4. Merge del elemento, 5. Cierre del sprint (QA completo sobre todo el diff del sprint), Cierre de entrega (lo que solo cubre el CI se corre con Docker), Clasificación: ciclo normal o excepción, Commands (+5 more)

### Community 88 - "judgment-day/SKILL.md"
Cohesion: 0.14
Nodes (13): Autoverificación (antes de cualquier acción terminal), Critical Patterns, Formato de salida, Patrón 0: estándares del proyecto (ANTES de lanzar jueces), Patrón 1: revisión ciega en paralelo, Patrón 2: síntesis del veredicto (cuando AMBOS terminaron), Patrón 3: clasificación de las advertencias, Patrón 4: corregir y volver a juzgar (+5 more)

### Community 89 - "Cómo contribuir a DevSkills"
Cohesion: 0.15
Nodes (11): Antes de un commit, Estructura, Estándares del repositorio DevSkills, Reglas, Cómo contribuir a DevSkills, Estándares, Flujo: primero el issue, Licencia (+3 more)

### Community 90 - "ServicioContrasenasDjango"
Cohesion: 0.27
Nodes (4): ServicioContrasenasDjango, test_una_contrasena_apenas_mas_larga_que_el_limite_tampoco_llega(), test_una_contrasena_en_el_limite_se_hashea_y_se_verifica(), test_una_contrasena_enorme_no_llega_a_argon2()

### Community 91 - "entorno.py"
Cohesion: 0.08
Nodes (15): _clave_de_produccion(), debilidades_de_transporte(), _es_sufijo_publico(), exigir_tls_en_datos(), _host_invalido_en_produccion(), idioma(), _ip_sin_especificar(), llave_de_huella_de_produccion() (+7 more)

### Community 92 - "_cargar"
Cohesion: 0.15
Nodes (11): _cargar(), test_dev_exige_database_url_y_explica_como_arrancar(), test_dev_usa_la_database_url_del_entorno(), test_dev_y_prod_comparten_la_constante_de_la_clave_de_desarrollo(), test_dev_y_pruebas_no_agregan_la_csp(), test_migraciones_exige_su_url_y_una_secret_key_valida(), test_migraciones_no_cae_en_la_url_de_la_aplicacion(), test_migraciones_usa_el_rol_de_migraciones_y_no_el_de_la_aplicacion() (+3 more)

### Community 94 - "Critical Patterns"
Cohesion: 0.15
Nodes (12): Criterios de revisión (van en LOS DOS prompts), Critical Patterns, Formato de salida, Patrón 0: alcance (ANTES de lanzar auditores), Patrón 1: auditoría ciega en paralelo, Patrón 2: clasificación, Patrón 3: síntesis del veredicto (la hace el orquestador cuando AMBOS terminaron), Patrón 4: corregir y re-auditar (+4 more)

### Community 95 - "ci.yml"
Cohesion: 0.17
Nodes (11): concurrency, cancel-in-progress, group, name, permissions, contents, branches, branches (+3 more)

### Community 96 - "exportar_sesion.py"
Cohesion: 0.23
Nodes (5): enmascarar(), exportar(), limpiar(), sesion_mas_reciente(), texto_de()

### Community 97 - "roles_bd.py"
Cohesion: 0.15
Nodes (11): sin_marcador_de_ejemplo(), test_sin_marcador_de_ejemplo_acepta_un_secreto_real(), test_aprovisionar_exige_dos_roles_distintos(), test_aprovisionar_rechaza_claves_debiles_o_de_ejemplo(), test_aprovisionar_rechaza_una_clave_de_redis_debil_o_de_ejemplo(), test_aprovisionar_rechaza_una_url_de_administracion_de_ejemplo(), aprovisionar(), _crear_o_actualizar_rol() (+3 more)

### Community 98 - "Critical Patterns"
Cohesion: 0.17
Nodes (11): 1. Antes de escribir: análisis de impacto, 2. Orden de la pasada (no se salta ningún paso), 3. Versionado, 4. Quién decidió, 5. Commit de documentación, 6. Verificación de la pasada, Commands, Critical Patterns (+3 more)

### Community 99 - "Critical Patterns"
Cohesion: 0.17
Nodes (11): 1. Dónde vive cada dato (nada se escribe a mano en el backlog), 2. Cómo se cargan las entregas, 3. Entregas, 4. Estimación, 5. Velocidad y recalibración, 6. Cuándo se regenera, 7. Verificación después de regenerar, Commands (+3 more)

### Community 100 - "Critical Patterns"
Cohesion: 0.17
Nodes (11): 1. Regla del documento, 2. Orden (cada paso se valida antes del siguiente), 3. Lo que ya decide el esqueleto (no se rediseña), 4. Reglas que evitan retrabajo (lecciones del proyecto modelo), 5. ADR, 6. Habilitadores, 7. Cierre de cada paso, Commands (+3 more)

### Community 101 - "Critical Patterns"
Cohesion: 0.17
Nodes (11): 0. Modos, 1. Independencia, 2. Del Gherkin del SRS a pruebas ejecutables, 3. Requisitos no funcionales, 4. Batería y mutaciones, 5. Criterio de veredicto, 6. Defectos y observaciones, Commands (+3 more)

### Community 102 - "hosts_permitidos_de_produccion"
Cohesion: 0.25
Nodes (4): hosts_permitidos_de_produccion(), lista(), test_la_lista_de_sufijos_publicos_se_usa_sin_red(), test_lista_ignora_espacios_y_vacios()

### Community 104 - "Critical Patterns"
Cohesion: 0.18
Nodes (10): 1. Al empezar la sesión, 2. Delegar, no ejecutar, 3. Decidir lo técnico, preguntar lo de negocio, 4. Ningún trabajo sin respaldo en git, 5. Estado y avance, 6. Memoria (engram), 7. Telegram (si el canal está activo), 8. Reglas de trabajo del usuario (heredadas del proyecto modelo) (+2 more)

### Community 105 - "Critical Patterns"
Cohesion: 0.18
Nodes (10): 1. Qué es y qué no es, 2. Estructura del documento, 3. Datos ficticios (Prompt 0), 4. Cómo se escribe cada pantalla, 5. Correcciones: revisar la maqueta contra el SRS, 6. Versionado, Commands, Critical Patterns (+2 more)

### Community 106 - "Critical Patterns"
Cohesion: 0.18
Nodes (10): 1. Orden estricto (regla del Product Owner), 2. Problema de negocio y línea base medible (paso 1), 3. Convenciones de IDs (no se renumeran, no se reutilizan), 4. Preguntas y decisiones, 5. Historias (Anexo B), 6. Cierre de cada paso, Commands, Critical Patterns (+2 more)

### Community 107 - "pruebas"
Cohesion: 0.20
Nodes (10): run, pruebas, os, defaults, name, runs-on, strategy, shell (+2 more)

### Community 108 - "Contexto del proyecto: {{NOMBRE_PROYECTO}}"
Cohesion: 0.20
Nodes (9): Ciclo de calidad: plataforma y elementos críticos, Contexto del proyecto: {{NOMBRE_PROYECTO}}, Convenciones propias del proyecto, Decisiones vigentes del Product Owner que afectan el trabajo diario, Entorno local, Fuentes de verdad (en este orden), Integraciones externas, Módulos y desarrollador asignado (+1 more)

### Community 109 - "Critical Patterns"
Cohesion: 0.15
Nodes (10): Code Examples, Commands, Critical Patterns, Paso 0. Entender antes de tocar código, Paso 1. Ubicar el trabajo en la arquitectura, Paso 2. TDD (rojo → verde → refactor), Paso 3. Reglas que siempre se revisan antes de entregar, Paso 3b. Lecciones aprendidas (checklist de incidentes reales) (+2 more)

### Community 110 - "proyecto-contexto/SKILL.md"
Cohesion: 0.20
Nodes (9): Arquitectura fija (DISEÑO D.1), Commands, Convenciones de código, Critical Patterns, Definición de Listo y de Terminado, Entorno local, Fuentes de verdad (en este orden), Lo propio de cada proyecto: `documentacion/CONTEXTO.md` (+1 more)

### Community 112 - "install.sh script"
Cohesion: 0.42
Nodes (8): detectar_so(), es_propio(), escapar_sed(), limpiar_carpetas(), ruta_portable(), install.sh script, adaptar(), validar_ruta()

### Community 113 - "test_esqueleto_modulos.py"
Cohesion: 0.28
Nodes (3): test_modulo_esta_registrado_como_app_de_django(), test_modulo_no_tiene_submodulos_fuera_de_los_contratos_de_import_linter(), test_modulo_tiene_estructura_hexagonal()

### Community 114 - ".de"
Cohesion: 0.18
Nodes (7): _normalizar_roles(), _texto_no_vacio(), _validar(), test_de_acepta_cualquier_iterable_y_quita_repetidos(), test_de_acepta_un_generador_de_roles(), test_de_rechaza_un_texto_suelto_en_vez_de_partirlo_en_letras(), test_roles_con_elementos_que_no_son_texto_lanzan_value_error()

### Community 115 - "Prompts para Figma Make: {{NOMBRE_PROYECTO}} (por sprint)"
Cohesion: 0.22
Nodes (8): Cómo usarlos, Prompt 0. Base: sistema de diseño, navegación y datos ficticios, Prompt 1. Sprints <!-- S1 a Sn --> · Entrega 0: Cimientos, Prompt M. Maqueta de venta: todas las pestañas funcionales, modo claro/oscuro y recorrido de demo, Prompt R2. Correcciones a la maqueta después del Prompt R, Prompt R. Actualización de <motivo> (SRS X.Y), Prompts para Figma Make: {{NOMBRE_PROYECTO}} (por sprint), Ruta rápida para la maqueta de venta

### Community 116 - "Critical Patterns"
Cohesion: 0.22
Nodes (8): 1. Diagnóstico (sin tocar nada), 2. Respaldo, 3. Reanudar sin rehacer, 4. Limpieza, Commands, Critical Patterns, Si la corrida es no interactiva (`claude -p`), When to Use

### Community 117 - "PULL_REQUEST_TEMPLATE.md"
Cohesion: 0.25
Nodes (7): Cambios, Issue relacionado, Lista del contribuidor, Notas para quien revisa, Plan de pruebas, Resumen, Tipo de cambio

### Community 118 - "jobs"
Cohesion: 0.25
Nodes (8): jobs, lint, manifiestos, name, runs-on, name, runs-on, steps

### Community 119 - "tasks.py"
Cohesion: 0.31
Nodes (4): test_la_tarea_de_celery_lleva_limites_de_tiempo_y_no_usa_acks_late(), construir_despachador(), despachar_outbox(), purgar_outbox()

### Community 122 - "evaluacion-alternativas/SKILL.md"
Cohesion: 0.25
Nodes (7): 1. Principios, 2. Pasos, 3. Cierre, Commands, Critical Patterns, Resources, When to Use

### Community 123 - "verificador"
Cohesion: 0.33
Nodes (7): Agentes, Asignación de módulos, Nombres según la instalación, Qué generaliza cada uno, Reglas comunes a todos, Tabla de agentes, verificador()

### Community 124 - "Generadores de contenido"
Cohesion: 0.29
Nodes (7): Anexo C de trazabilidad, Documentos Word, Generadores de contenido, Instalar las dependencias sin tocar nada global, Plan y tablero de sprints, Presentación, Transcripción de la sesión

### Community 125 - "Uso no interactivo"
Cohesion: 0.29
Nodes (7): Corre en un entorno aislado, Costo observado y cómo abaratarlo, Las respuestas del Product Owner van en el prompt, Plugin engram en sesiones anidadas, Retomar tras un corte por límite de uso, Tiempos: la suspensión del equipo cuenta como duración, Uso no interactivo

### Community 126 - "Skills"
Cohesion: 0.29
Nodes (6): Arranque y documentación, Calidad adicional, Ciclo de cada historia, Equivalencias con el proyecto modelo, Sesión y coordinación, Skills

### Community 127 - "Stack"
Cohesion: 0.29
Nodes (7): Arquitectura, Cómo extenderlo para tu dominio, Lecciones del stack (CI y despliegue), Qué trae el esqueleto, Stack, Tecnologías, Verificación

### Community 128 - "_nombre_completo"
Cohesion: 0.33
Nodes (5): _aislar_modulos_de_settings(), entorno_prod(), _nombre_completo(), _restaurar_modulos_de_settings(), test_el_aislamiento_no_deja_prod_en_sys_modules()

### Community 129 - "test_dependencias_reproducibles.py"
Cohesion: 0.33
Nodes (3): _paquetes_del_lock(), test_el_lock_si_existe_fija_la_version_y_trae_hashes_de_cada_paquete(), test_pip_tools_esta_entre_las_herramientas_de_desarrollo()

### Community 131 - "ctx"
Cohesion: 0.29
Nodes (3): ctx(), rol_sensible(), sin_segundo_factor()

### Community 132 - "_TextoFalso"
Cohesion: 0.29
Nodes (3): test_una_subclase_de_str_con_eq_alterado_se_rechaza_como_rol(), test_una_subclase_de_str_con_eq_alterado_se_rechaza_en_el_id(), _TextoFalso

### Community 133 - "Equipo de agentes de {{NOMBRE_PROYECTO}}"
Cohesion: 0.29
Nodes (6): Ciclo de calidad (híbrido), Dónde queda el avance, Equipo de agentes de {{NOMBRE_PROYECTO}}, Estructura del repositorio, Jerarquía, Reglas del repositorio

### Community 134 - "Critical Patterns"
Cohesion: 0.29
Nodes (6): 1. Formato de la pregunta, 2. Por dónde preguntar, 3. Esperar, 4. Registrar quién decidió, Critical Patterns, When to Use

### Community 136 - "qa.md"
Cohesion: 0.33
Nodes (5): Cuidado del repositorio, Cómo trabajas, Límites, Modos, Reglas comunes de DevSkills

### Community 137 - "verificador.md"
Cohesion: 0.33
Nodes (5): Cuidado del repositorio, Cómo trabajas (modo final), Formato de salida, Modos, Reglas comunes de DevSkills

### Community 138 - "main"
Cohesion: 0.60
Nodes (4): test_main_aprovisiona_con_las_variables_de_entorno(), test_main_avisa_que_variables_faltan(), test_main_rechaza_una_clave_de_redis_debil(), main()

### Community 139 - "Trabajar por Telegram"
Cohesion: 0.33
Nodes (6): Abrir la sesión con el canal, Alias `claude-tg`, Cómo se comporta el orquestador con el canal activo, Problemas comunes, Requisitos, Trabajar por Telegram

### Community 140 - "contact_links"
Cohesion: 0.33
Nodes (5): blank_issues_enabled, contact_links, about, name, url

### Community 141 - "esqueleto"
Cohesion: 0.33
Nodes (6): SIN_DOCKER, env, name, runs-on, timeout-minutes, esqueleto

### Community 142 - "todo-en-verde"
Cohesion: 0.33
Nodes (6): todo-en-verde, if, name, needs, runs-on, steps

### Community 143 - "test_roles_de_ejemplo.py"
Cohesion: 0.33
Nodes (3): test_la_bitacora_es_un_ejemplo_marcado_y_el_administrador_no_la_anuncia(), test_los_archivos_que_nombra_la_seccion_existen(), test_los_roles_de_ejemplo_son_los_dos_que_documenta_el_readme()

### Community 148 - "analista-arquitecto.md"
Cohesion: 0.40
Nodes (4): Cuidado del repositorio, Cómo trabajas, Límites, Reglas comunes de DevSkills

### Community 149 - "angel-fixer.md"
Cohesion: 0.40
Nodes (4): Cuidado del repositorio, Modo evaluación (ciclo completo de la excepción), Modo revisión por historia (ciclo normal), Reglas comunes de DevSkills

### Community 150 - "dev-a.md"
Cohesion: 0.40
Nodes (4): Cuidado del repositorio, Cómo trabajas, Límites, Reglas comunes de DevSkills

### Community 151 - "dev-b.md"
Cohesion: 0.40
Nodes (4): Cuidado del repositorio, Cómo trabajas, Límites, Reglas comunes de DevSkills

### Community 154 - "📦 Instalación"
Cohesion: 0.40
Nodes (5): 📦 Instalación, Manual, Plugin de Claude Code (recomendado), Windows (Git Bash), Windows (PowerShell)

### Community 155 - "install_ps1_spec.sh"
Cohesion: 0.60
Nodes (3): ps1(), install_ps1_spec.sh script, win()

### Community 156 - "vetar_acciones_externas.sh"
Cohesion: 0.83
Nodes (3): vetar_acciones_externas.sh script, vetar(), vetar_instalacion()

### Community 161 - "guarda-todo/SKILL.md"
Cohesion: 0.50
Nodes (3): Commands, Critical Patterns, When to Use

### Community 162 - "hook_spec.sh"
Cohesion: 0.67
Nodes (3): evento(), hook(), hook_spec.sh script

## Knowledge Gaps
- **1 isolated node(s):** `{{SLUG}}`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1525 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **69 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Actor` connect `Actor` to `test_escenarios_gestion_de_usuarios.py`, `composicion.py`, `_TextoFalso`, `test_confirmar_codigo.py`, `test_eventos_identidad.py`, `composicion.py`, `test_escenarios_segundo_factor.py`, `test_aviso_reuso_adaptador.py`, `test_aviso_reuso_concurrencia.py`, `test_un_actor_sin_roles_no_tiene_ninguno`, `vistas_usuarios.py`, `vistas.py`, `test_segundo_factor_adaptador.py`, `Documento de Diseño de Software (SDD)`, `test_aviso_reuso.py`, `AvisoDeReuso`, `dev-dominio.md`, `admin`, `identidad/pruebas/test_adaptadores.py`, `Capacidad`, `test_si_una_escritura_del_reinicio_falla_no_queda_nada_a_medias`, `middleware.py`, `test_actor.py`, `test_gestion_usuarios_base.py`, `Critical Patterns`, `proyecto-contexto/SKILL.md`, `.de`, `Stack`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Are the 232 inferred relationships involving `Usuario` (e.g. with `actor_de()` and `_abrir_sesion()`) actually correct?**
  _`Usuario` has 232 INFERRED edges - model-reasoned connections that need verification._
- **What connects `{{SLUG}}` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Actor` be split into smaller, more focused modules?**
  _Cohesion score 0.0564831993403422 - nodes in this community are weakly interconnected._
- **Why does `verificador()` connect `verificador` to `test_segundo_factor_adaptador.py`, `README.md`, `[Sin publicar]`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Are the 75 inferred relationships involving `Actor` (e.g. with `dev-dominio.md` and `Qué trae el esqueleto`) actually correct?**
  _`Actor` has 75 INFERRED edges - model-reasoned connections that need verification._
- **Should `test_escenarios_gestion_de_usuarios.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06105006105006105 - nodes in this community are weakly interconnected._