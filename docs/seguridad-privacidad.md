# Guía de Seguridad y Protección de Datos Personales — EXPO LANDA

Este documento establece las políticas operativas, medidas técnicas y procedimientos para el tratamiento de datos personales conforme a la **Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP)** de México y las mejores prácticas de ciberseguridad.

---

## 1. Principios de Minimización de Datos

La aplicación recopila únicamente los datos estrictamente necesarios para la gestión del evento inmobiliario:

- **Nombre completo:** Para identificar al asistente responsable.
- **Teléfono móvil (10 dígitos):** Para confirmar asistencia o avisar de imprevistos.
- **Correo electrónico:** Para canalizar información del evento.
- **Cantidad de asistentes:** Para estimar la concurrencia global del evento.
- **Horario aproximado (opcional):** Para balancear el flujo de visitantes a lo largo del día.

### Lo que NO se recopila bajo ninguna circunstancia:
- Identificaciones oficiales (INE/Pasaporte).
- CURP o RFC.
- Datos bancarios, tarjetas o información financiera.
- Comprobantes de ingresos o documentación de crédito hipotecario.
- Datos personales de acompañantes o menores de edad.
- Huellas digitales, contraseñas de visitantes o datos sensibles.

---

## 2. Consentimiento y Separación de Finalidades

El sistema implementa dos mecanismos independientes de consentimiento:

1. **Finalidades Primarias (Casilla Obligatoria):**
   - Gestión del registro, asignación de folio y coordinación logística de asistencia.
   - Desmarcada por defecto; el usuario debe marcarla activamente tras consultar el resumen o el Aviso integral.
   - El backend registra la versión exacta del aviso (`privacy_version`) y la marca de tiempo UTC (`privacy_accepted_at`).

2. **Finalidades Secundarias / Publicidad (Casilla Opcional):**
   - Comunicaciones sobre promociones, disponibilidad de vivienda y futuros eventos por WhatsApp, llamada o correo.
   - Desmarcada por defecto. El usuario puede registrarse perfectamente dejando esta casilla sin marcar.
   - Se registra versión del texto comercial (`marketing_text_version`) y timestamp (`marketing_consent_at`).

### Revocación de Publicidad
El titular puede revocar su consentimiento comercial en cualquier momento desde `derechos.html#revocacion` o por solicitud directa a la organizadora.
- El panel administrativo permite marcar la revocación inmediatamente (`POST /api/admin/registrations/{folio}/revoke-marketing`).
- La exportación a Excel y las consultas filtradas excluyen automáticamente a quienes hayan revocado su consentimiento publicitario.

---

## 3. Procedimiento para Solicitudes ARCO

Cualquier persona puede ejercer sus derechos de **Acceso, Rectificación, Cancelación u Oposición (ARCO)**:

### Procedimiento de Recepción y Respuesta:
1. **Recepción:** El titular envía un correo al buzón legal configurado (`PRIVACY_CONTACT_EMAIL`) indicando su nombre, folio (opcional) y derecho que desea ejercer.
2. **Acreditación:** El responsable valida la identidad confirmando los datos de contacto registrados.
3. **Plazos:** Conforme a la LFPDPPP, se cuenta con un plazo máximo de **20 días hábiles** para emitir respuesta sobre la procedencia, y **15 días hábiles** adicionales para hacerla efectiva.
4. **Ejecución en el Sistema:**
   - **Rectificación:** Si hay un error en teléfono o correo, el administrador puede modificar el estatus o actualizar la información.
   - **Cancelación / Supresión:** Se ofrecen dos vías en el panel (`/admin.html`):
     - **Anonimización:** Elimina irreversiblemente nombre, teléfono, correo y llave de idempotencia, conservando únicamente la fecha y número de asistentes para fines estadísticos históricos.
     - **Eliminación Definitiva:** Borra el registro completo de la base de datos tras confirmar el folio exacto.
5. **Auditoría:** Ambas acciones generan un registro inmutable en `audit_log` con el usuario que ejecutó la acción, la fecha y el motivo legal (sin almacenar datos personales de la solicitud).

---

## 4. Política de Conservación y Purga Periódica

Los datos personales recabados para la EXPO LANDA no deben mantenerse indefinidamente.

1. **Plazo sugerido:** Mantener registros activos durante el periodo de seguimiento comercial autorizado (por ejemplo, 12 meses) y purgar registros sin consentimiento publicitario tras la conclusión del evento.
2. **Ejecución de Purga mediante CLI:**
   El backend incluye un comando específico para anonimizar registros antiguos de forma segura:

   ```bash
   # Simulación previa para verificar registros afectados
   python cli.py anonymize-expired --months 12 --dry-run

   # Ejecución real de anonimización
   python cli.py anonymize-expired --months 12
   ```

---

## 5. Manejo Seguro de Archivos Excel Exportados

Los reportes generados con el botón **EXPORTAR REGISTROS A EXCEL** contienen datos personales y deben tratarse con extrema confidencialidad:

### Reglas de Seguridad Operativa:
1. **Protección contra Inyección de Fórmulas:**
   El servicio de exportación (`services/export.py`) neutraliza automáticamente cualquier valor que comience con caracteres especiales (`=`, `+`, `-`, `@`, tabuladores o saltos de línea), anteponiendo un apóstrofo `'` y fijando el tipo de celda a texto explícito (`data_type="s"`). Esto previene ataques de *CSV/Formula Injection* si un usuario malintencionado hubiera ingresado fórmulas en su nombre.
2. **Almacenamiento Local:** No almacenes los archivos `.xlsx` en escritorios compartidos, carpetas públicas de Google Drive o discos sin cifrar.
3. **Transmisión Segura:** Si el reporte debe compartirse con el equipo de ventas, envíalo cifrado con contraseña o a través de un canal corporativo con autenticación en dos pasos.
4. **Destrucción Segura:** Una vez concluida la jornada del evento o la gestión de llamadas, elimina permanentemente las copias locales del archivo (`Shift + Supr` o borrado seguro).

---

## 6. Arquitectura Técnica de Seguridad

| Control | Implementación |
| :--- | :--- |
| **Cifrado en Tránsito** | Forzado HTTPS con HSTS (`Strict-Transport-Security: max-age=31536000`) |
| **Contraseñas Administrativas** | Hashing con **Argon2id** (`PasswordHasher`) con defensa contra enumeración por temporización |
| **Fuerza Bruta** | Bloqueo temporal tras 5 intentos fallidos consecutivos por 15 minutos + Rate limit por IP |
| **Gestión de Sesiones** | Cookies seguras `__Host-` con `HttpOnly`, `SameSite=Strict`, `Secure`. Tokens almacenados únicamente en hash SHA-256 |
| **Expiración de Sesión** | Timeout por inactividad a los 30 minutos y límite absoluto a las 8 horas |
| **Protección CSRF** | Token aleatorio por sesión exigido en encabezado `X-CSRF-Token` para todas las operaciones mutables |
| **Validación de Origen** | Comprobación estricta del encabezado `Origin` contra `ALLOWED_ORIGINS` |
| **Defensa contra XSS** | CSP restrictivo (`script-src 'self'`), uso exclusivo de `textContent` en frontend, prohibición de `innerHTML` |
| **Protección contra Inyección SQL** | Consultas parametrizadas mediante SQLAlchemy ORM (sin concatenación de strings) |
| **Anti-Spam / Anti-Bots** | Honeypot invisible, token de formulario firmado con HMAC y validación de tiempo mínimo de llenado (mínimo 2 segundos) |
| **Ocultamiento de Errores** | Sin filtración de trazas internas (tracebacks) ni PII en respuestas HTTP |
