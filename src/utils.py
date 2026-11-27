import json
import re
from typing import Optional, Any, List, Dict
from datetime import datetime

def format_timestamp(timestamp_ms: Optional[Any], date_format: str = "%Y-%m-%d %H:%M") -> str:
    """
    Converts a millisecond POSIX timestamp into a formatted date string.
    Returns default message if timestamp is None or invalid.
    """
    if not timestamp_ms:
        return "N/A"
    try:
        return datetime.fromtimestamp(int(timestamp_ms) / 1000).strftime(date_format)
    except (ValueError, TypeError):
        return "Invalid date"

def parse_task_comments(comments_data: List[Dict[str, Any]], max_comments: int = 3) -> List[str]:
    """
    Parses a list of comment raw objects into formatted comment strings.
    """
    comments_list = []
    for comment in comments_data[:max_comments]:
        comment_text = comment.get("comment_text", "").strip()
        comment_user = comment.get("user", {}).get("username", "Usuario Desconocido")
        comments_list.append(f"💬 {comment_user}: {comment_text}")
    return comments_list

def sanitize_table_name(name: str) -> str:
    """
    Sanitizes a string to be a valid BigQuery table name.
    Replaces non-alphanumeric characters with underscores and ensures valid characters.
    """
    clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    clean_name = re.sub(r'_+', '_', clean_name).strip('_')
    if clean_name and clean_name[0].isdigit():
        clean_name = f"list_{clean_name}"
    return clean_name or "clickup_tasks"

def construct_table_name(folder_name: Optional[str], list_name: Optional[str], list_id: str) -> str:
    """
    Constructs a deterministic table name using Folder Name, List Name, and List ID.
    Example output: 'mxConnect_CRM_mxConnect_1600210000001089'
    """
    parts = []
    if folder_name and folder_name.strip():
        parts.append(folder_name.strip())
    if list_name and list_name.strip():
        parts.append(list_name.strip())
    parts.append(list_id.strip())
    
    raw_name = "_".join(parts)
    return sanitize_table_name(raw_name)

def prepare_record_for_bigquery(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepares a single activity dictionary for BigQuery insertion.
    Converts list/dict fields into JSON strings if needed.
    """
    processed = row.copy()
    if isinstance(processed.get("Comentarios"), list):
        processed["Comentarios"] = json.dumps(processed["Comentarios"], ensure_ascii=False)
    return processed
