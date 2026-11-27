import pandas as pd
from typing import Optional, List, Dict, Any
import google.auth
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

from src.config import GCP_PROJECT_ID, BIGQUERY_DATASET_ID
from src.utils import sanitize_table_name, prepare_record_for_bigquery

class BigQuerySchemaManager:
    """Handles dataset verification, table creation, and schema definition for BigQuery."""

    def __init__(self, client: bigquery.Client, dataset_id: str = BIGQUERY_DATASET_ID):
        self.client = client
        self.dataset_id = dataset_id
        self.dataset_ref = bigquery.DatasetReference(self.client.project, self.dataset_id)

    def ensure_dataset_exists(self) -> None:
        """Verifies if the BigQuery dataset exists; creates it if missing."""
        try:
            self.client.get_dataset(self.dataset_ref)
            print(f"✅ Dataset '{self.dataset_id}' exists in BigQuery.")
        except NotFound:
            dataset = bigquery.Dataset(self.dataset_ref)
            dataset.location = "US"
            self.client.create_dataset(dataset, timeout=30)
            print(f"✨ Created missing Dataset '{self.dataset_id}'.")

    def get_table_schema(self) -> List[bigquery.SchemaField]:
        """Returns the default BigQuery schema for ClickUp activities."""
        return [
            bigquery.SchemaField("ID", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("Tipo", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("Padre_ID", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("Nombre", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("Estado", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("Responsables", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("Fecha_Inicio", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("Fecha_Vencimiento", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("Prioridad", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("Descripcion", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("Comentarios", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
        ]

    def ensure_table_exists(self, table_id: str) -> bigquery.Table:
        """Checks if a table exists; creates it with schema if it does not."""
        table_ref = self.dataset_ref.table(table_id)
        try:
            table = self.client.get_table(table_ref)
            print(f"✅ Table '{self.dataset_id}.{table_id}' exists.")
            return table
        except NotFound:
            schema = self.get_table_schema()
            table = bigquery.Table(table_ref, schema=schema)
            created_table = self.client.create_table(table)
            print(f"✨ Created missing Table '{self.dataset_id}.{table_id}'.")
            return created_table


class BigQuerySyncManager:
    """
    Handles UPSERT (MERGE) operations into BigQuery tables using
    Application Default Credentials (ADC).
    """

    def __init__(self, project_id: Optional[str] = GCP_PROJECT_ID, dataset_id: str = BIGQUERY_DATASET_ID):
        self.dataset_id = dataset_id

        try:
            credentials, default_project = google.auth.default()
            self.project_id = project_id or default_project
            if not self.project_id:
                raise ValueError("GCP Project ID could not be resolved from ADC or environment variables.")
            
            self.client = bigquery.Client(credentials=credentials, project=self.project_id)
            print(f"🔐 BigQuery Client initialized with Application Default Credentials (Project: {self.project_id}).")
        except Exception as e:
            print(f"❌ Failed to obtain Application Default Credentials (ADC): {e}")
            print("💡 Tip: Run 'gcloud auth application-default login' or set GOOGLE_APPLICATION_CREDENTIALS in your .env")
            raise e

        self.schema_manager = BigQuerySchemaManager(self.client, self.dataset_id)

    def sync_dataframe(self, table_name: str, df: pd.DataFrame) -> None:
        """
        Upserts (inserts new or updates existing based on 'ID') a Pandas DataFrame directly into BigQuery.
        """
        if df.empty:
            print("⚠️ The DataFrame is empty. Nothing to sync to BigQuery.")
            return

        clean_table_id = sanitize_table_name(table_name)

        # 1. Ensure dataset and target table exist
        self.schema_manager.ensure_dataset_exists()
        self.schema_manager.ensure_table_exists(clean_table_id)

        # 2. Prepare DataFrame copy and process list/dict columns to strings
        df_sync = df.copy()
        if "Comentarios" in df_sync.columns:
            df_sync["Comentarios"] = df_sync["Comentarios"].apply(
                lambda c: str(c) if isinstance(c, (list, dict)) else c
            )
        df_sync["updated_at"] = pd.Timestamp.utcnow()

        # 3. Load DataFrame into a temporary staging table
        temp_table_id = f"staging_{clean_table_id}_{int(pd.Timestamp.utcnow().timestamp())}"
        staging_table_ref = self.schema_manager.dataset_ref.table(temp_table_id)

        job_config = bigquery.LoadJobConfig(
            schema=self.schema_manager.get_table_schema(),
            write_disposition="WRITE_TRUNCATE",
        )

        load_job = self.client.load_table_from_dataframe(
            df_sync, staging_table_ref, job_config=job_config
        )
        load_job.result()  # Wait for staging load to complete

        # 4. Perform MERGE (UPSERT) query matching on ID
        target_table_full = f"`{self.client.project}.{self.dataset_id}.{clean_table_id}`"
        staging_table_full = f"`{self.client.project}.{self.dataset_id}.{temp_table_id}`"

        merge_query = f"""
        MERGE {target_table_full} T
        USING {staging_table_full} S
        ON T.ID = S.ID
        WHEN MATCHED THEN
          UPDATE SET
            T.Tipo = S.Tipo,
            T.Padre_ID = S.Padre_ID,
            T.Nombre = S.Nombre,
            T.Estado = S.Estado,
            T.Responsables = S.Responsables,
            T.Fecha_Inicio = S.Fecha_Inicio,
            T.Fecha_Vencimiento = S.Fecha_Vencimiento,
            T.Prioridad = S.Prioridad,
            T.Descripcion = S.Descripcion,
            T.Comentarios = S.Comentarios,
            T.updated_at = S.updated_at
        WHEN NOT MATCHED THEN
          INSERT (ID, Tipo, Padre_ID, Nombre, Estado, Responsables, Fecha_Inicio, Fecha_Vencimiento, Prioridad, Descripcion, Comentarios, updated_at)
          VALUES (S.ID, S.Tipo, S.Padre_ID, S.Nombre, S.Estado, S.Responsables, S.Fecha_Inicio, S.Fecha_Vencimiento, S.Prioridad, S.Descripcion, S.Comentarios, S.updated_at)
        """

        query_job = self.client.query(merge_query)
        query_job.result()  # Wait for query execution

        print(f"🚀 Successfully merged {len(df_sync)} rows from Pandas DataFrame into BigQuery table '{clean_table_id}'.")

        # 5. Clean up staging table
        self.client.delete_table(staging_table_ref, not_found_ok=True)

    def sync_activities(self, table_name: str, activities: List[Dict[str, Any]]) -> None:
        """
        Upserts activity dictionaries into BigQuery by converting them into a DataFrame first.
        """
        if not activities:
            print("⚠️ No activities to sync.")
            return

        processed_data = [prepare_record_for_bigquery(act) for act in activities]
        df = pd.DataFrame(processed_data)
        self.sync_dataframe(table_name, df)
