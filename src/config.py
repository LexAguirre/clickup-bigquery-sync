import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# ClickUp API Base Configuration
CLICKUP_BASE_URL: str = os.getenv("CLICKUP_BASE_URL", "https://api.clickup.com/api/v2")
CLICKUP_TOKEN: Optional[str] = os.getenv("CLICKUP_TOKEN")

# Google Cloud BigQuery Configuration
GCP_PROJECT_ID: Optional[str] = os.getenv("GCP_PROJECT_ID")
BIGQUERY_DATASET_ID: str = os.getenv("BIGQUERY_DATASET_ID", "clickup_sync")

def get_clickup_headers(token: Optional[str] = None) -> Dict[str, str]:
    """Generates standard headers for ClickUp API requests."""
    api_key = token or CLICKUP_TOKEN
    return {
        "Authorization": api_key if api_key else "",
        "Content-Type": "application/json",
    }
