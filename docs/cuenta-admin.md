# Gestión de Cuentas Administrativas — EXPO LANDA

El acceso al panel privado (`/admin.html`) está restringido mediante autenticación basada en base de datos con contraseñas protegidas por **Argon2id**.

Por principios de seguridad, el sistema **no contiene credenciales ni cuentas por defecto**. Todas las cuentas administrativas deben crearse o modificarse mediante la herramienta de línea de comandos `cli.py` en el servidor.

---

## 1. Creación de la Primera Cuenta de Administrador

Para dar de alta a la organizadora o a un usuario con privilegios totales:

```bash
cd backend
python cli.py create-admin mayte --role admin
```

El script te solicitará la contraseña de manera segura utilizando `getpass` (la contraseña no se imprimirá en pantalla ni se grabará en el historial del shell):

```text
Contraseña (mínimo 12 caracteres): ************
Repite la contraseña: ************
Cuenta creada: mayte (admin)
```

---

## 2. Roles Disponibles

El sistema soporta dos niveles de privilegio:

1. **`admin` (Administrador):**
   - Visualización de estadísticas y total de asistentes.
   - Búsqueda y filtrado de registros.
   - Acceso al detalle completo de cada asistente.
   - Modificación de estado (Pendiente / Confirmado / Cancelado).
   - Registro de revocación publicitaria.
   - **Exportación de registros a Excel (.xlsx)**.
   - Anonimización y eliminación de registros por solicitudes ARCO.
   - Consulta de la bitácora de auditoría.

2. **`viewer` (Solo Lectura):**
   - Visualización de estadísticas y total de asistentes.
   - Búsqueda y consulta de registros en pantalla.
   - **Bloqueado** para exportar a Excel, cambiar estados, anonimizar o eliminar.

Para crear una cuenta de solo lectura:
```bash
python cli.py create-admin asesor --role viewer
```

---

## 3. Política de Contraseñas

Cualquier contraseña creada o actualizada debe cumplir las siguientes validaciones automáticas:
- **Longitud mínima:** 12 caracteres.
- **Complejidad:** Debe combinar letras con al menos un dígito o carácter especial.
- **Variedad:** Debe contener al menos 5 caracteres únicos distintos.
- **Filtro de contraseñas comunes:** Se rechazan automáticamente contraseñas triviales (ej. `password1234`, `contraseña123`).

---

## 4. Restablecimiento de Contraseñas y Recuperación

Si un administrador olvida su contraseña o si se sospecha un compromiso de credenciales:

```bash
python cli.py reset-password mayte
```

El comando:
1. Solicita la nueva contraseña segura por terminal.
2. Actualiza el hash Argon2id en la base de datos.
3. Resetea los intentos fallidos de inicio de sesión (`failed_attempts = 0`).
4. Remueve cualquier bloqueo temporal de cuenta (`locked_until = None`).
5. **Invalida inmediatamente todas las sesiones activas** de ese usuario en el servidor, forzando un nuevo inicio de sesión.

---

## 5. Desactivación de Cuentas

Si un colaborador deja la organización o ya no requiere acceso:

```bash
python cli.py deactivate asesor
```

Esto marca `is_active = false`, invalida sus sesiones en el servidor e impide cualquier intento subsecuente de login.

---

## 6. Listado de Cuentas Existentes

Para auditar qué cuentas existen actualmente en el sistema (sin revelar contraseñas ni hashes):

```bash
python cli.py list-admins
```

Salida de ejemplo:
```text
mayte                admin   activo=True  último acceso=2026-10-12 14:10:00
asesor               viewer  activo=True  último acceso=None
```
