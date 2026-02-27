import json
from pathlib import Path

from app.services.adapters.base import BaseAdapter


class SEMrushAdapter(BaseAdapter):
    def __init__(self, json_path: str = "sample_data/semrush.json"):
        self.json_path = json_path

    def validate_config(self) -> None:
        if not Path(self.json_path).exists():
            raise FileNotFoundError(f"SEMrush sample not found: {self.json_path}")

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
                    "source": "semrush",
                    "competitor_gap": float(row.get("competitor_gap", 0)),
                    "intent": row.get("intent", "informational"),
                    "links": row.get("urls", []),
                }
            )
        return items


# TODO: replace mocked file-based fetch with SEMrush API client when key is provided.
