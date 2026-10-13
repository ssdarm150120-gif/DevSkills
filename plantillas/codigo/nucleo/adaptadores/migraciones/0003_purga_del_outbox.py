from django.db import migrations

# Retencion del outbox: el evento y sus entregas se borran a los 30 dias de despachados, y
# SOLO si todas sus entregas estan `entregada` (o no tiene entregas). La aplicacion no puede hacer
# DELETE sobre `evento_outbox` (ver `herramientas/roles_bd.py`): lo hace esta funcion, propiedad del
# rol de migraciones (SECURITY DEFINER), que se niega a borrar nada mas reciente que el plazo.
# Borra primero las entregas y luego el evento, en una sola sentencia (la FK se verifica al final).
SQL_CREAR = """
CREATE FUNCTION "nucleo".purgar_eventos_outbox(p_corte timestamptz, p_lote integer)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    borrados integer;
BEGIN
    IF p_corte IS NULL OR p_corte > clock_timestamp() - interval '30 days' THEN
        RAISE EXCEPTION 'purga_fuera_de_plazo: el corte debe ser de hace 30 dias o mas';
    END IF;
    IF p_lote IS NULL OR p_lote < 1 OR p_lote > 10000 THEN
        RAISE EXCEPTION 'purga_lote_invalido: el lote va de 1 a 10000';
    END IF;
    WITH candidatos AS (
        SELECT e.id
        FROM "nucleo"."evento_outbox" e
        WHERE e.registrado_en <= p_corte
          AND NOT EXISTS (
              SELECT 1 FROM "nucleo"."entrega_outbox" n
              WHERE n.evento_id = e.id
                AND (n.estado <> 'entregada' OR n.entregada_en IS NULL OR n.entregada_en > p_corte)
          )
        ORDER BY e.id
        LIMIT p_lote
        FOR UPDATE OF e SKIP LOCKED
    ), entregas_borradas AS (
        DELETE FROM "nucleo"."entrega_outbox" WHERE evento_id IN (SELECT id FROM candidatos)
    )
    DELETE FROM "nucleo"."evento_outbox" WHERE id IN (SELECT id FROM candidatos);
    GET DIAGNOSTICS borrados = ROW_COUNT;
    RETURN borrados;
END
$fn$;
REVOKE ALL ON FUNCTION "nucleo".purgar_eventos_outbox(timestamptz, integer) FROM PUBLIC;
"""
SQL_QUITAR = 'DROP FUNCTION "nucleo".purgar_eventos_outbox(timestamptz, integer)'


class Migration(migrations.Migration):
    dependencies = [("nucleo", "0002_outbox_de_eventos")]

    operations = [migrations.RunSQL(sql=SQL_CREAR, reverse_sql=SQL_QUITAR)]
