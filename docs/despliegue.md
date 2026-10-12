# Guía de Despliegue en Producción — EXPO LANDA

Esta guía describe cómo desplegar la plataforma completa de EXPO LANDA en infraestructura de producción, manteniendo la separación entre frontend estático (desplegable en Vercel o servido directamente) y backend FastAPI con base de datos PostgreSQL administrada.

---

## 1. Arquitectura Recomendada

```
[ Visitante / Anuncio FB-IG ]
             │
             ▼
  [ Frontend: Vercel / CDN ]  o  [ FastAPI sirve / (monolito) ]
             │
             ▼ (HTTPS / REST)
      [ Backend: FastAPI ] (Render, Railway, Fly.io, etc.)
             │
             ▼ (TLS / sslmode=require)
  [ PostgreSQL Administrado ] (Neon, Supabase, Render Postgres)
```

---

## 2. Creación de la Base de Datos PostgreSQL

1. Contrata o aprovisiona una base de datos PostgreSQL administrada (versión 14 o superior) en un proveedor como **Neon**, **Supabase** o **Render**.
2. Obtén la URI de conexión asegurando que requiera cifrado TLS:
   ```text
   postgresql://USUARIO:CONTRASENA@HOST:5432/DATABASE?sslmode=require
   ```
3. Verifica que la base de datos cuente con respaldos automáticos diarios activados desde el panel del proveedor.

---

## 3. Configuración de Variables de Entorno en el Backend

Configura las siguientes variables en tu plataforma de hosting (Render, Railway, etc.):

| Variable | Ejemplo en Producción | Descripción |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `production` | Activa modo producción (desactiva docs públicos, fuerza HTTPS y cookies seguras) |
| `DATABASE_URL` | `postgresql://usr:pass@host/db?sslmode=require` | Conexión a PostgreSQL administrado |
| `AUTO_CREATE_TABLES` | `false` | Las tablas se crean exclusivamente con Alembic |
| `SERVE_FRONTEND` | `false` *(o `true` si es monolito)* | `false` si el frontend se aloja aparte en Vercel |
| `FORM_SIGNING_SECRET` | *(64 caracteres aleatorios)* | Clave para firmar tokens de formulario anti-spam |
| `ALLOWED_ORIGINS` | `https://expolanda.com` | Origen exacto del frontend permitido en CORS |
| `COOKIE_SECURE` | `true` | Exige cookie con bandera `Secure` y prefijo `__Host-` |
| `TRUSTED_PROXY_COUNT` | `1` o `2` | Número de proxies intermedios para resolver la IP del cliente real |
| `SESSION_IDLE_MINUTES` | `30` | Inactividad máxima antes de cerrar sesión admin |
| `SESSION_ABSOLUTE_HOURS`| `8` | Duración máxima absoluta de sesión |
| `MAX_ATTENDEES` | `10` | Límite por registro en el formulario (configurable) |
| `EVENT_DETAILS_CONFIRMED`| `true` *(tras confirmación)* | Cambiar a `true` cuando Mayte Ramírez valide fecha/horario |
| `PRIVACY_CONTROLLER_NAME`| `[Razón social o Nombre real]` | Responsable legal del tratamiento |
| `PRIVACY_CONTROLLER_ADDRESS`| `[Dirección fiscal real]` | Domicilio legal |
| `PRIVACY_CONTACT_EMAIL`| `privacidad@landa.com.mx` | Correo para solicitudes ARCO |
| `PRIVACY_CONTACT_PHONE`| `449 348 1867` | Teléfono de atención |
| `PRIVACY_RETENTION_TEXT`| `Consulte la política de 12 meses...`| Criterio formal de conservación |
| `PRIVACY_PROVIDERS_TEXT`| `Hospedaje en Render, base Neon...` | Proveedores de infraestructura |
| `TURNSTILE_SITE_KEY` | *(opcional)* | Llave pública de Cloudflare Turnstile |
| `TURNSTILE_SECRET_KEY` | *(opcional)* | Llave secreta de Cloudflare Turnstile |

> **Generar secreto robusto:**
> ```bash
> python -c "import secrets; print(secrets.token_urlsafe(48))"
> ```

---

## 4. Aplicación de Migraciones en Producción

Antes de dirigir tráfico al backend, ejecuta la migración inicial en el entorno de producción:

```bash
cd backend
alembic upgrade head
```

Esto ejecutará `migraciones/versions/0001_esquema_inicial.py`, creando:
- `registrations` (con índices en `created_at` y `status`)
- `admin_users` (con restricciones de roles)
- `admin_sessions` (con hashes SHA-256 de tokens)
- `audit_log` (para trazabilidad sin datos personales)

---

## 5. Creación de la Primera Cuenta Administrativa

Por seguridad, la plataforma **no tiene usuarios predeterminados** en la base de datos de producción.

Accede a la consola de tu servidor backend o ejecuta mediante SSH/CLI:

```bash
cd backend
python cli.py create-admin mayte --role admin
```

El script solicitará la contraseña de forma segura por terminal (sin mostrarla en pantalla ni guardarla en logs de comandos). La contraseña debe cumplir con:
- Mínimo 12 caracteres.
- Al menos una letra y un número o símbolo.
- No ser contraseñas comunes predecibles.

---

## 6. Despliegue del Frontend en Vercel (Opción Frontend Separado)

1. En la carpeta `frontend/`, si el backend corre en un dominio distinto (ej. `https://api.expolanda.com`), edita la etiqueta `<meta name="landa-api-base" content="https://api.expolanda.com">` en:
   - `frontend/index.html`
   - `frontend/admin.html`
   - `frontend/aviso-privacidad.html`
   - `frontend/derechos.html`
2. Configura Vercel para servir la carpeta `frontend/` como sitio estático.
3. Asegura que en el backend `ALLOWED_ORIGINS` contenga la URL exacta del proyecto en Vercel (ej. `https://expolanda.vercel.app,https://expolanda.com`).
4. En Vercel, habilita HTTPS automático (incluido por defecto).

---

## 7. Despliegue Monolítico Simplificado (Recomendado para servidores únicos)

Si prefieres desplegar todo en un único servicio (ej. Render Web Service o VPS):
1. Deja `SERVE_FRONTEND=true` en `.env`.
2. Mantén `<meta name="landa-api-base" content="">` (vacío).
3. FastAPI servirá el frontend directamente desde la raíz (`/`), la landing page en `index.html`, el panel en `/admin` y los estáticos en `/assets/`.
4. El comando de arranque es:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
   ```

---

## 8. Verificación Previa al Lanzamiento de Campañas

Antes de activar pautas publicitarias en Meta Ads:
1. **Prueba de registro real:** Ingresa a la landing, llena un registro y confirma que recibes el folio `LANDA-XXXX-XXXX`.
2. **Prueba de doble envío:** Haz clic dos veces rápido en el botón de confirmación; valida que no se dupliquen registros.
3. **Prueba de panel:** Inicia sesión en `/admin.html` con la cuenta creada; verifica que los contadores coincidan.
4. **Prueba de exportación:** Descarga el archivo Excel con el botón **EXPORTAR REGISTROS A EXCEL** y ábrelo en Microsoft Excel o Google Sheets.
5. **Verificación legal:** Confirma que el banner de borrador del Aviso de Privacidad esté oculto y que los datos del responsable correspondan a los definitivos.
