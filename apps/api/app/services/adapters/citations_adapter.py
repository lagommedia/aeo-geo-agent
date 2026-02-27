import json
from pathlib import Path

from app.services.adapters.base import BaseAdapter


class CitationMonitorAdapter(BaseAdapter):
    def __init__(self, json_path: str = "sample_data/citations.json"):
        self.json_path = json_path

    def validate_config(self) -> None:
        if not Path(self.json_path).exists():
            raise FileNotFoundError(f"Citations sample not found: {self.json_path}")

    def fetch(self):
        self.validate_config()
        with open(self.json_path, encoding="utf-8") as f:
            return json.load(f)

    def normalize(self, raw_data):
        normalized = []
        for row in raw_data.get("records", []):
            normalized.append(
                {
                    "query_text": row["prompt"].strip().lower(),
                    "source": "ai_citations",
                    "brand_mentioned": bool(row.get("brand_mentioned", False)),
                    "brand_cited": bool(row.get("brand_cited", False)),
                    "cited_urls": row.get("cited_urls", []),
                    "competitor_cited": row.get("competitor_cited", []),
                    "date": row.get("date"),
                }
            )
        return normalized
