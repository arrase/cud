---
name: create_task
description: Crea tareas periódicas programadas que se ejecutan automáticamente.
---

# Crear Tareas Periódicas

Puedes crear tareas programadas que se ejecutarán automáticamente según un horario cron.

## Ubicación

Crea un directorio en `workspace/tasks/<nombre>/` con un fichero `TASK.md` dentro.

## Formato del TASK.md

```yaml
---
name: nombre_unico
description: Descripción breve de la tarea.
schedule: "0 8 * * *"
channel_id: 123456789012345678   # Enviar respuesta a un canal de Discord.
user_id: 987654321098765432      # O enviar por DM a un usuario de Discord.
enabled: true                    # Opcional: true por defecto.
---

Aquí va el prompt que el agente ejecutará en cada ejecución programada.
```

## Destino de la respuesta

- `channel_id`: ID de un canal de Discord. El bot debe tener acceso al canal.
- `user_id`: ID de un usuario de Discord. La respuesta se enviará por mensaje directo.
- Se debe definir al menos uno de los dos. Si se definen ambos, `channel_id` tiene prioridad.

## Expresiones cron (min hora día mes día_semana)

- `0 8 * * *` — Cada día a las 8:00
- `0 */2 * * *` — Cada 2 horas
- `*/30 * * * *` — Cada 30 minutos
- `0 9 * * 1` — Cada lunes a las 9:00
- `0 0 1 * *` — Primer día de cada mes a medianoche
- `30 14 * * 1-5` — De lunes a viernes a las 14:30

## Importante

Después de crear o modificar una tarea, el usuario debe ejecutar `/reload` en Discord para que el scheduler la detecte.
