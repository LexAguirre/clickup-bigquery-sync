import os
import argparse
import pandas as pd
from src.clickup_client import ClickUpAPI
from src.bigquery_client import BigQuerySyncManager

def run_diagnose():
    """Ejecuta únicamente el diagnóstico jerárquico de accesos al Workspace de ClickUp."""
    print("\n--- Modo: Diagnóstico de Workspace ---")
    client = ClickUpAPI()
    client.explore_and_diagnose_access()

def run_fetch_activities(list_id: str = None, sync_bq: bool = False):
    """Extrae las actividades de ClickUp y opcionalmente las sincroniza con BigQuery."""
    print("\n--- Modo: Extracción de Actividades ---")
    clickup_client = ClickUpAPI()
    
    selected_list_id = list_id or os.getenv("CLICKUP_LIST_ID", "901705208158")
    print(f"Consultando Lista ID: {selected_list_id}")
    
    actividades = clickup_client.parse_and_show_activities(selected_list_id)

    if not actividades:
        print("\nNo se obtuvieron actividades.")
        return None

    df = pd.DataFrame(actividades)
    print("\n--- Resumen del DataFrame ---")
    print(df.head())

    if sync_bq:
        print("\n--- Sincronizando actividades con BigQuery ---")
        table_name = clickup_client.get_table_name_for_list(selected_list_id)
        
        bq_manager = BigQuerySyncManager()
        bq_manager.sync_activities(table_name, actividades)

    return df

def run_sync_dataframe_to_bigquery(list_id: str = None):
    """
    Proceso dedicado: Extrae las actividades de ClickUp, las convierte a un Pandas DataFrame
    y envía/actualiza directamente el DataFrame en BigQuery usando el nombre de tabla determinista
    (Folder_Lista_ID).
    """
    print("\n--- Modo: Extracción y Envío de Pandas DataFrame a BigQuery ---")
    clickup_client = ClickUpAPI()
    
    selected_list_id = list_id or os.getenv("CLICKUP_LIST_ID", "901705208158")
    print(f"1. Obteniendo actividades de la Lista ID: {selected_list_id}")
    
    actividades = clickup_client.parse_and_show_activities(selected_list_id)
    if not actividades:
        print("\n❌ No se encontraron actividades para enviar.")
        return None

    # 2. Generación del Pandas DataFrame
    df = pd.DataFrame(actividades)
    print(f"\n2. Pandas DataFrame generado exitosamente con {len(df)} filas y {len(df.columns)} columnas.")
    print("Muestra del DataFrame:")
    print(df.head(3))

    # 3. Obtener nombre de tabla determinista (Folder_Lista_ID)
    table_name = clickup_client.get_table_name_for_list(selected_list_id)

    # 4. Enviar DataFrame a BigQuery vía BigQuerySyncManager
    print(f"\n3. Enviando DataFrame a la tabla '{table_name}' en BigQuery...")
    bq_manager = BigQuerySyncManager()
    bq_manager.sync_dataframe(table_name, df)
    
    return df

def main():
    parser = argparse.ArgumentParser(
        description="CLI para la integración de ClickUp y BigQuery"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")
    
    # Subcomando 1: diagnose
    subparsers.add_parser("diagnose", help="Explora y diagnostica la jerarquía de acceso del token de ClickUp")
    
    # Subcomando 2: fetch-activities
    fetch_parser = subparsers.add_parser("fetch-activities", help="Extrae las actividades de una lista específica")
    fetch_parser.add_argument("--list-id", type=str, help="ID de la lista de ClickUp")
    fetch_parser.add_argument("--sync-bq", action="store_true", help="Sincroniza directamente las actividades en BigQuery")
    
    # Subcomando 3: sync-dataframe
    df_parser = subparsers.add_parser("sync-dataframe", help="Extrae la lista, genera un Pandas DataFrame y lo envía a BigQuery")
    df_parser.add_argument("--list-id", type=str, help="ID de la lista de ClickUp")

    args = parser.parse_args()
    
    if args.command == "diagnose":
        run_diagnose()
    elif args.command == "fetch-activities":
        run_fetch_activities(list_id=args.list_id, sync_bq=args.sync_bq)
    elif args.command == "sync-dataframe":
        run_sync_dataframe_to_bigquery(list_id=args.list_id)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
