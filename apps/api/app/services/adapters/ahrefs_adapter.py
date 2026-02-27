import json
from pathlib import Path

from app.services.adapters.base import BaseAdapter


class AhrefsAdapter(BaseAdapter):
    def __init__(self, json_path: str = "sample_data/ahrefs.json"):
        self.json_path = json_path

    def validate_config(self) -> None:
        if not Path(self.json_path).exists():
            raise FileNotFoundError(f"Ahrefs sample not found: {self.json_path}")

    def fetch(self):
        self.validate_config()
        with open(self.json_path, encoding="utf-8") as f:
            return json.load(f)

    def normalize(self, raw_data):
        items = []
        for row in raw_data.get("queries", []):
            items.append(
                {
                    "query_text": row["query"].strip().lower(),
                    "source": "ahrefs",
                    "competitor_gap": float(row.get("competitor_gap", 0)),
                    "intent": row.get("intent", "informational"),
                    "links": row.get("urls", []),
                }
            )
        return items


# TODO: replace mocked file-based fetch with Ahrefs API client when key is provided.
