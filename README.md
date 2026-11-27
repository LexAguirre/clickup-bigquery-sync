# ClickUp & BigQuery Sync Integration

Este proyecto permite extraer tareas, subtareas y comentarios desde la API de ClickUp y sincronizarlos de forma incremental en Google Cloud BigQuery.

---

## 📁 Estructura del Proyecto

```
clickup-bigquery-sync/
│
├── src/
│   ├── __init__.py           # Inicializador de paquete
│   ├── config.py             # Configuración de variables de entorno (ClickUp & BigQuery)
│   ├── utils.py              # Funciones auxiliares (formato de fechas, limpieza de nombres de tablas, parseo)
│   ├── clickup_client.py     # Clase ClickUpAPI (comunicación con API de ClickUp)
│   └── bigquery_client.py    # Clases GCP (BigQuerySchemaManager & BigQuerySyncManager)
│
├── .venv/                    # Entorno virtual aislado
├── main.py                   # CLI con subcomandos independientes (diagnose y fetch-activities)
├── requirements.txt          # Dependencias de Python
├── .env.example              # Plantilla de variables de entorno
├── .gitignore               # Reglas de exclusión para Git
└── README.md                 # Documentación
```

---

## ⚙️ Configuración del Entorno Virtual

### 1. Creación y Activación del `.venv`

```bash
# Crear entorno virtual
python3 -m venv .venv

# Activar en macOS/Linux:
source .venv/bin/activate

# Activar en Windows (CMD):
# .venv\Scripts\activate.bat

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Variables de Entorno (`.env`)

Copia la plantilla de variables de entorno:

```bash
cp .env.example .env
```

### 2. Autenticación y Credenciales (Application Default Credentials - ADC)

Para interactuar con Google Cloud BigQuery, el código utiliza el estándar oficial **Application Default Credentials (ADC)** (`google.auth.default()`).

Puedes autenticarte de dos maneras:

#### Opción A: Vía gcloud CLI (Recomendada para desarrollo local)
```bash
gcloud auth application-default login
```

#### Opción B: Mediante Cuenta de Servicio (`.env`)
Establece en tu archivo `.env` la ruta absoluta al JSON de tu Service Account:

```env
GCP_PROJECT_ID=tu_gcp_project_id
BIGQUERY_DATASET_ID=clickup_sync
GOOGLE_APPLICATION_CREDENTIALS=/ruta/a/tu/service_account.json
```

---

## 🚀 Ejecución

El CLI cuenta con tres subcomandos independientes:

### 1. Diagnóstico de Workspace de ClickUp (`diagnose`)
Explora la jerarquía de accesos (Workspaces, Spaces, Folders y Listas) permitidos por tu Token:

```bash
python main.py diagnose
```

### 2. Extracción de Actividades (`fetch-activities`)
Extrae y muestra las actividades en consola / DataFrame:

```bash
python main.py fetch-activities --list-id 901705208158
```

### 3. Generación y Sincronización de Pandas DataFrame a BigQuery (`sync-dataframe`)
Extrae las actividades de ClickUp, genera un **Pandas DataFrame** y lo envía/actualiza (**UPSERT / MERGE**) en BigQuery.

> **Nomenclatura de la Tabla:** El nombre de la tabla en BigQuery se genera de forma determinista usando el **Folder**, **Lista** e **ID de Lista** (ej. `mxConnect_CRM_mxConnect_1600210000001089`). De esta forma, siempre actualizará la misma tabla sin duplicarla.

```bash
# Sincroniza el Pandas DataFrame en la tabla unificada Folder_Lista_ID
python main.py sync-dataframe --list-id 1600210000001089
```

---

## 🏛️ Clases y Arquitectura GCP / BigQuery

El módulo `src/bigquery_client.py` implementa dos clases principales:

1. **`BigQuerySchemaManager`**:
   - `ensure_dataset_exists()`: Verifica si el Dataset existe en BigQuery; si no existe, lo crea automáticamente.
   - `ensure_table_exists(table_id)`: Revisa si la tabla con el nombre sanitizado de la Lista de ClickUp existe; si no, la genera con el esquema correspondiente.
   - `get_table_schema()`: Define la estructura de campos (ID, Tipo, Nombre, Estado, Responsables, Fechas, Descripcion, Comentarios, updated_at).

2. **`BigQuerySyncManager`**:
   - `sync_activities(table_name, activities)`: Carga los registros actualizados en una tabla temporal de staging y ejecuta una sentencia `MERGE` usando el **`ID`** como clave única para insertar registros nuevos y actualizar los existentes.
