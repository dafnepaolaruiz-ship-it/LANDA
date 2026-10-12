# EXPO LANDA — Plataforma de Registro, Panel Administrativo y Protección de Datos

Aplicación web integral para la captación, registro seguro y administración de asistentes al evento inmobiliario **EXPO LANDA**, optimizada para tráfico proveniente de campañas publicitarias en Facebook e Instagram.

Combina una dirección de arte editorial contemporánea con un backend robusto en Python (FastAPI), almacenamiento persistente (SQLAlchemy / PostgreSQL), panel administrativo con autenticación de alta seguridad, exportación a Excel (.xlsx) con neutralización de fórmulas y cumplimiento estricto con la Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP) de México.

---

## 1. Información Oficial del Evento

- **Nombre del evento:** EXPO LANDA
- **Concepto:** Tu hogar al alcance
- **Organizadora y contacto:** Mayte Ramírez (449 348 1867)
- **Ubicación:** Landa Entorno Residencial, Blvd. El Chichimeco, a un minuto del Parque Industrial, Jesús María, Aguascalientes.
- **Fecha:** 7 de noviembre de 2026
- **Horario:** 10:00 a. m. a 7:00 p. m.
- **Entrada:** Gratuita
- **Actividades oficiales:**
  - Recorridos por 3 modelos de vivienda con entrega inmediata.
  - Ideas de muebles y decoración.
  - Asesoría gratuita sobre opciones de crédito para vivienda.
  - Sorpresas y regalos para los asistentes.

---

## 2. Arquitectura del Proyecto

```
LANDA/
├── frontend/
│   ├── index.html            # Landing page principal (7 secciones editoriales)
│   ├── styles.css            # Hoja de estilos con variables de color, tipografía y responsive
│   ├── app.js                # Validación del formulario, idempotencia y confirmación
│   ├── admin.html            # Interfaz del panel administrativo privado
│   ├── admin.css             # Estilos del panel administrativo
│   ├── admin.js              # Lógica del panel (sin innerHTML; uso exclusivo de textContent)
│   ├── aviso-privacidad.html # Aviso de privacidad integral editable conforme a LFPDPPP
│   ├── derechos.html         # Procedimiento para ejercer derechos ARCO y revocación
│   ├── legal.js              # Carga dinámica de datos legales y baja de publicidad
│   ├── robots.txt            # Bloqueo de indexación para /admin y /api/
│   └── assets/
│       ├── fonts/            # Tipografías autoalojadas Fraunces e Inter (licencia SIL OFL)
│       ├── img/              # Fotografías oficiales de Landa y carátula Open Graph
│       └── favicon.svg       # Favicon vectorial oficial
├── backend/
│   ├── main.py               # Servidor FastAPI, middleware de seguridad y montado estático
│   ├── config.py             # Configuración centralizada vía Pydantic Settings
│   ├── database.py           # Conexión SQLAlchemy (SQLite local / PostgreSQL prod)
│   ├── models.py             # Modelos: Registration, AdminUser, AdminSession, AuditLog
│   ├── schemas.py            # Validación estricta Pydantic y normalización de teléfonos MX
│   ├── security.py           # Rate limiting, tokens HMAC, sanitización de fórmulas Excel
│   ├── auth.py               # Hashing Argon2id, cookies __Host-, sesiones y tokens CSRF
│   ├── cli.py                # CLI para creación de administradores y purga de datos
│   ├── requirements.txt      # Dependencias fijadas para producción
│   ├── alembic.ini           # Configuración de migraciones
│   ├── migraciones/          # Historial de migraciones con Alembic
│   ├── routes/
│   │   ├── public.py         # Endpoints de registro público, tokens y baja de publicidad
│   │   └── admin.py          # Endpoints protegidos: KPIs, búsqueda, Excel y auditoría
│   ├── services/
│   │   ├── registrations.py  # Lógica de creación idempotente, búsqueda y anonimización
│   │   └── export.py         # Generación segura de archivos Excel (.xlsx) con openpyxl
│   └── tests/
│       ├── conftest.py       # Fixtures y base de datos aislada para pruebas
│       ├── test_registration.py    # Pruebas del formulario público y persistencia
│       ├── test_admin_security.py  # Pruebas de autenticación, panel, Excel y seguridad
│       └── e2e/e2e_visual.py       # Pruebas E2E completas en navegador real (Edge/Chromium)
├── docs/
│   ├── despliegue.md         # Guía de puesta en marcha en servidores de producción
│   ├── seguridad-privacidad.md # Procedimientos ARCO, auditoría y protección de datos
│   └── cuenta-admin.md       # Administración de usuarios y políticas de contraseñas
├── .gitignore                # Exclusión de bases de datos, secretos y archivos .xlsx
└── README.md                 # Este documento
```

---

## 3. Puesta en Marcha Local (Desarrollo)

### Requisitos previos:
- Python 3.9 o superior.
- Navegador moderno (Edge, Chrome, Firefox o Safari).

### Pasos de instalación:

1. **Crear y activar el entorno virtual:**
   ```powershell
   cd backend
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. **Instalar dependencias:**
   ```powershell
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Configurar el archivo de entorno:**
   ```powershell
   Copy-Item .env.example .env
   ```

4. **Aplicar las migraciones a la base de datos local:**
   ```powershell
   alembic upgrade head
   ```

5. **Crear una cuenta administrativa local:**
   ```powershell
   python cli.py create-admin demo --role admin
   ```

6. **Iniciar el servidor local:**
   ```powershell
   python -m uvicorn main:app --port 8000 --reload
   ```

7. **Abrir en el navegador:**
   - **Landing page pública:** [http://localhost:8000/](http://localhost:8000/)
   - **Aviso de Privacidad integral:** [http://localhost:8000/aviso-privacidad.html](http://localhost:8000/aviso-privacidad.html)
   - **Panel Administrativo:** [http://localhost:8000/admin.html](http://localhost:8000/admin.html)

---

## 4. Batería de Pruebas Automatizadas

El proyecto cuenta con dos niveles de validación exhaustiva:

### A. Pruebas Unitarias y de Integración con Pytest (96 pruebas)
Ejecuta la suite completa con:
```powershell
cd backend
.venv\Scripts\python -m pytest -v
```
**Resultado:** `96 passed in 13.2s`
- Validación de campos del formulario (teléfonos mexicanos con prefijos +52, correos RFC, nombres, límites).
- Prevención de doble clic y reintentos idempotentes.
- Persistencia de registros y suma del aforo independiente de dispositivos.
- Autenticación con Argon2id, bloqueo temporal por intentos fallidos y rotación de sesiones.
- Control de acceso por roles (`admin` vs `viewer`).
- Paginación del lado del servidor y búsqueda no expuesta en URLs.
- Exportación a Excel con neutralización de inyección de fórmulas (`=`, `+`, `-`, `@`).
- Verificación de ausencia de PII en logs, URLs y respuestas de error.

### B. Pruebas End-to-End (E2E) en Navegador Real con Playwright (39 verificaciones)
Ejecuta la prueba visual y funcional con Edge/Chromium:
```powershell
$env:E2E_ADMIN_USER="demo"; $env:E2E_ADMIN_PASS="[Tu-Password]"; python tests\e2e\e2e_visual.py
```
**Resultado:** `39/39 verificaciones correctas`
- Carga responsiva sin desbordamiento horizontal en Escritorio (1440px), Tableta (820px) y Celular (390px).
- Desplazamiento suave al formulario mediante el CTA del hero.
- Interacción con stepper accesible de asistentes (+ / -).
- Flujo de confirmación con folio generado, enlace a WhatsApp con mensaje precargado y descarga de archivo de calendario `.ics`.
- Manejo elegante de fallas transitorias de servidor (HTTP 503) conservando los datos sin confirmar falsamente.
- Inicio de sesión en panel administrativo, filtrado en tiempo real, cambio de estado, descarga real del reporte Excel y cierre de sesión efectivo.

---

## 5. Medidas de Seguridad y Protección de Datos

1. **Principio de Minimización:** Solo se solicitan nombre, celular, correo y total de asistentes. No se piden credenciales, identificaciones oficiales, datos de tarjetas bancarias ni información de acompañantes.
2. **Consentimiento Dual Desmarcado:**
   - Casilla 1 (Obligatoria): Gestión de asistencia conforme al Aviso de Privacidad.
   - Casilla 2 (Opcional): Autorización de publicidad comercial independiente.
3. **Manejo Seguro de Excel:** Todas las cadenas se escriben como texto y se prefijan con apóstrofo si inician con caracteres de fórmula. Se excluyen secretos, hashes o identificadores internos.
4. **Protección Anti-Abuso:** Honeypot transparente, tokens firmados temporalmente por HMAC y limitación de tasa de solicitudes (Rate Limiting).
5. **Mitigación de XSS e Inyecciones:** No se utiliza `innerHTML` para renderizar datos de usuarios. Encabezados HTTP de seguridad estrictos (CSP, X-Content-Type-Options, HSTS, X-Frame-Options).

---

## 6. Lista de Tareas y Datos Pendientes Antes del Lanzamiento

Antes de activar los anuncios en Facebook e Instagram, deben completarse los siguientes puntos administrativos y de configuración:

### A. Datos Legales que Mayte Ramírez debe Proporcionar:
- [ ] **Nombre o Razón Social del Responsable:** Especificar si la persona responsable del tratamiento es una persona física (ej. Mayte Ramírez) o una persona moral (empresa desarrolladora).
- [ ] **Domicilio Legal Completo:** Calle, número, colonia, código postal y municipio para el Aviso de Privacidad.
- [ ] **Correo Electrónico de Privacidad:** Cuenta designada para recibir solicitudes ARCO (ej. `privacidad@landa.com.mx`).
- [ ] **Confirmación de Fechas y Horario:** Confirmar si la fecha del 7 de noviembre de 2026 de 10:00 a. m. a 7:00 p. m. es definitiva para cambiar `EVENT_DETAILS_CONFIRMED=true`.

### B. Servicios Externos a Configurar:
- [ ] **Base de Datos PostgreSQL:** Aprovisionar base de datos administrada con backups automáticos (Neon, Supabase o Render).
- [ ] **Dominio y Certificado SSL:** Configurar el dominio definitivo (ej. `expolanda.com`) con HTTPS forzado.
- [ ] **Variables de Entorno de Producción:** Configurar `FORM_SIGNING_SECRET`, `DATABASE_URL` y orígenes autorizados en `ALLOWED_ORIGINS`.
- [ ] **Antispam Adicional (Opcional):** Si se desea Cloudflare Turnstile, registrar el sitio en Cloudflare y configurar las llaves en `.env`.
- [ ] **Meta Ads:** Configurar la URL de destino de los anuncios con parámetros UTM (ej. `?utm_source=facebook&utm_medium=paid&utm_campaign=expo_nov2026`).

---

## 7. Licencia y Créditos

- **Tipografías:** Fraunces (SIL Open Font License) e Inter (SIL Open Font License).
- **Fotografías:** Fotografías arquitectónicas originales de Landa Entorno Residencial.
- **Desarrollo:** Antigravity Pair Programming para EXPO LANDA.
