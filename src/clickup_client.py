import time
import requests
from typing import Optional, List, Dict, Any

from src.config import CLICKUP_BASE_URL, CLICKUP_TOKEN, get_clickup_headers
from src.utils import format_timestamp, parse_task_comments, construct_table_name

class ClickUpAPI:
    """Handles interactions with the ClickUp API, including workspace browsing and list management."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or CLICKUP_TOKEN

    def get_clickup_headers(self) -> Dict[str, str]:
        """Generates headers for ClickUp API requests."""
        return get_clickup_headers(self.api_key)

    def _request_with_retry(self, method: str, url: str, max_retries: int = 5, backoff_factor: float = 2.0, **kwargs) -> Optional[requests.Response]:
        """
        Executes an HTTP request with exponential backoff retry when hit by 429 Rate Limit.
        """
        headers = kwargs.pop("headers", self.get_clickup_headers())
        delay = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.request(method, url, headers=headers, **kwargs)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    sleep_time = float(retry_after) if retry_after else delay
                    print(f"⚠️ Rate limit (429) alcanzado. Esperando {sleep_time:.1f}s antes de reintentar (Intento {attempt}/{max_retries})...")
                    time.sleep(sleep_time)
                    delay *= backoff_factor
                    continue
                return response
            except requests.RequestException as e:
                print(f"❌ Error de conexión ({e}). Esperando {delay:.1f}s antes de reintentar...")
                time.sleep(delay)
                delay *= backoff_factor

        print(f"❌ Excedido el número máximo de reintentos ({max_retries}) para la URL: {url}")
        return None

    def get_list_details(self, list_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves details of a specific list, including its name and folder info."""
        url = f"{CLICKUP_BASE_URL}/list/{list_id}"
        response = self._request_with_retry("GET", url)
        if response and response.status_code == 200:
            return response.json()
        return None

    def get_table_name_for_list(self, list_id: str) -> str:
        """
        Constructs a consistent BigQuery table name based on Folder Name, List Name, and List ID.
        """
        list_details = self.get_list_details(list_id)
        if not list_details:
            return construct_table_name(None, None, list_id)
        
        list_name = list_details.get("name")
        folder_info = list_details.get("folder", {})
        folder_name = folder_info.get("name") if isinstance(folder_info, dict) else None
        
        return construct_table_name(folder_name, list_name, list_id)

    def get_clickup_userid_by_email(self, user_email: str) -> Optional[int]:
        """Searches ClickUp workspace members to find a user's ID by their email address."""
        response = self._request_with_retry("GET", f"{CLICKUP_BASE_URL}/team")
        if not response or response.status_code != 200:
            return None

        teams_data = response.json()
        for team in teams_data.get("teams", []):
            for member in team.get("members", []):
                user = member.get("user", {})
                if user.get("email") == user_email:
                    return user.get("id")
        return None

    def create_task(self, list_id: str, payload: Dict[str, Any]) -> Optional[requests.Response]:
        """Creates a new task in ClickUp inside the specified list ID."""
        url = f"{CLICKUP_BASE_URL}/list/{list_id}/task"
        return self._request_with_retry("POST", url, json=payload)

    def create_dependency(self, blocked_task_id: str, blocking_task_id: str) -> bool:
        """Links two tasks in ClickUp where blocked_task_id becomes 'Blocked by' blocking_task_id."""
        url = f"{CLICKUP_BASE_URL}/task/{blocked_task_id}/dependency"
        payload = {"depends_on": str(blocking_task_id).strip()}
        response = self._request_with_retry("POST", url, json=payload)
        if response and response.status_code in [200, 201]:
            print(f"    🔗 Dependency created: {blocked_task_id} blocked by {blocking_task_id}")
            return True
        return False

    def get_teams(self) -> List[Dict[str, Any]]:
        """Retrieves all Authorized Teams (Workspaces) for the account."""
        url = f"{CLICKUP_BASE_URL}/team"
        response = self._request_with_retry("GET", url)
        if response and response.status_code == 200:
            return response.json().get("teams", [])
        return []

    def get_spaces(self, team_id: str) -> List[Dict[str, Any]]:
        """Retrieves all Spaces within a specific Team (Workspace)."""
        url = f"{CLICKUP_BASE_URL}/team/{team_id}/space"
        response = self._request_with_retry("GET", url)
        if response and response.status_code == 200:
            return response.json().get("spaces", [])
        return []

    def get_folders(self, space_id: str) -> List[Dict[str, Any]]:
        """Retrieves all Folders within a specific Space."""
        url = f"{CLICKUP_BASE_URL}/space/{space_id}/folder"
        response = self._request_with_retry("GET", url)
        if response and response.status_code == 200:
            return response.json().get("folders", [])
        return []

    def get_lists_in_folder(self, folder_id: str) -> List[Dict[str, Any]]:
        """Retrieves all Lists nested inside a specific Folder."""
        url = f"{CLICKUP_BASE_URL}/folder/{folder_id}/list"
        response = self._request_with_retry("GET", url)
        if response and response.status_code == 200:
            return response.json().get("lists", [])
        return []

    def get_folderless_lists(self, space_id: str) -> List[Dict[str, Any]]:
        """Retrieves all folderless Lists directly hosted inside a Space."""
        url = f"{CLICKUP_BASE_URL}/space/{space_id}/list"
        response = self._request_with_retry("GET", url)
        if response and response.status_code == 200:
            return response.json().get("lists", [])
        return []

    def get_tasks_in_list(self, list_id: str, include_subtasks: bool = True, include_closed: bool = True, request_delay: float = 0.2) -> List[Dict[str, Any]]:
        """
        Obtiene todas las tareas (actividades) de una lista manejando la paginación de ClickUp y agregando una leve pausa preventiva entre páginas.
        """
        url = f"{CLICKUP_BASE_URL}/list/{list_id}/task"
        all_tasks = []
        page = 0

        while True:
            params = {
                "page": page,
                "subtasks": str(include_subtasks).lower(),
                "include_closed": str(include_closed).lower(),
            }
            response = self._request_with_retry("GET", url, params=params)
            if not response or response.status_code != 200:
                break

            data = response.json()
            tasks = data.get("tasks", [])
            if not tasks:
                break

            all_tasks.extend(tasks)

            if data.get("last_page", False) or len(tasks) < 100:
                break
            page += 1
            
            # Pausa preventiva para no saturar el límite de peticiones por minuto
            if request_delay > 0:
                time.sleep(request_delay)

        return all_tasks

    def get_task_comments(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene los comentarios asociados a una tarea específica.
        """
        url = f"{CLICKUP_BASE_URL}/task/{task_id}/comment"
        response = self._request_with_retry("GET", url)
        if response and response.status_code == 200:
            return response.json().get("comments", [])
        return []

    def explore_and_diagnose_access(self) -> None:
        """
        Explora de forma jerárquica todo el árbol de accesos de tu Token actual.
        """
        print("🔍 Iniciando diagnóstico de alcance del Token de ClickUp...")
        teams = self.get_teams()

        if not teams:
            print("❌ El token no tiene acceso a ningún Workspace (Team) o es inválido.")
            return

        print(f"✅ Token Válido. Tienes acceso a {len(teams)} Workspace(s):")
        for team in teams:
            team_id = team.get("id")
            team_name = team.get("name")
            print(f"\n🏢 Workspace: '{team_name}' (ID: {team_id})")

            spaces = self.get_spaces(team_id)
            if not spaces:
                print("   └── 📁 No se encontraron Spaces accesibles en este Workspace.")
                continue

            for space in spaces:
                space_id = space.get("id")
                space_name = space.get("name")
                print(f"   └── 🌌 Space: '{space_name}' (ID: {space_id})")

                folderless_lists = self.get_folderless_lists(space_id)
                for fl in folderless_lists:
                    print(f"       ├── 📋 [Lista Directa] '{fl.get('name')}' (ID: {fl.get('id')})")

                folders = self.get_folders(space_id)
                for folder in folders:
                    folder_id = folder.get("id")
                    folder_name = folder.get("name")
                    print(f"       └── 📁 Folder: '{folder_name}' (ID: {folder_id})")

                    lists = self.get_lists_in_folder(folder_id)
                    for l in lists:
                        print(f"           └── 📋 [Lista] '{l.get('name')}' (ID: {l.get('id')})")

    def parse_and_show_activities(self, list_id: str, max_comments: int = 3, comment_delay: float = 0.1) -> List[Dict[str, Any]]:
        """
        Extrae las actividades una a una, incluyendo la Fecha de Inicio y los comentarios,
        imprimiendo un reporte formateado y detallado.
        """
        raw_tasks = self.get_tasks_in_list(list_id)
        if not raw_tasks:
            print(f"⚠️ No se encontraron actividades en la lista ID: {list_id}")
            return []

        structured_activities = []

        print(f"\n======================================================================")
        print(f"📋 DESGLOSE DETALLADO DE ACTIVIDADES - LISTA ID: {list_id}")
        print(f"======================================================================\n")

        for idx, task in enumerate(raw_tasks, start=1):
            task_id = task.get("id")
            name = task.get("name", "Sin Título")
            status = task.get("status", {}).get("status", "N/A").upper()

            assignees = [user.get("username") or user.get("email") for user in task.get("assignees", [])]
            assignees_str = ", ".join(assignees) if assignees else "Sin asignar"

            start_date_raw = task.get("start_date")
            start_date_str = format_timestamp(start_date_raw) if start_date_raw else "Sin fecha de inicio"

            due_date_raw = task.get("due_date")
            due_date_str = format_timestamp(due_date_raw) if due_date_raw else "Sin fecha límite"

            priority_data = task.get("priority")
            priority = priority_data.get("priority", "Media").capitalize() if priority_data else "Sin prioridad"

            desc = (task.get("description") or "").strip()
            desc_preview = (desc[:120] + "...") if len(desc) > 120 else (desc or "Sin descripción")

            parent_id = task.get("parent")
            type_str = f"↳ Subtarea de [{parent_id}]" if parent_id else "📌 Tarea Principal"

            # Consulta de comentarios con leve pausa preventiva
            comments_data = self.get_task_comments(task_id)
            comments_list = parse_task_comments(comments_data, max_comments=max_comments)

            if comment_delay > 0:
                time.sleep(comment_delay)

            print(f"🔹 [{idx}] {type_str} | ID: {task_id}")
            print(f"   📂 Actividad:   {name}")
            print(f"   🟢 Estado:      {status}")
            print(f"   👤 Asignado:    {assignees_str}")
            print(f"   📅 Inicio:      {start_date_str} 🟢")
            print(f"   📅 Vence:       {due_date_str} 🔴")
            print(f"   ⚡ Prioridad:   {priority}")
            print(f"   📝 Descripción: {desc_preview}")

            if comments_list:
                print(f"   💬 Últimos Comentarios ({len(comments_list)}):")
                for c in comments_list:
                    print(f"      • {c}")
            else:
                print(f"   💬 Comentarios: Sin comentarios registrados")

            print(f"{'-'*70}")

            structured_activities.append({
                "ID": task_id,
                "Tipo": "Subtarea" if parent_id else "Principal",
                "Padre_ID": parent_id,
                "Nombre": name,
                "Estado": status,
                "Responsables": assignees_str,
                "Fecha_Inicio": start_date_str,
                "Fecha_Vencimiento": due_date_str,
                "Prioridad": priority,
                "Descripcion": desc,
                "Comentarios": comments_list
            })

        return structured_activities
