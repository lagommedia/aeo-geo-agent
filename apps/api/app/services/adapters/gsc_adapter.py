import csv
from pathlib import Path

from app.services.adapters.base import BaseAdapter


class GSCAdapter(BaseAdapter):
    def __init__(self, csv_path: str = "sample_data/gsc.csv"):
        self.csv_path = csv_path

    def validate_config(self) -> None:
        if not Path(self.csv_path).exists():
            raise FileNotFoundError(f"GSC CSV not found: {self.csv_path}")

    def fetch(self):
        self.validate_config()
        rows = []
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows

    def normalize(self, raw_data):
        grouped = {}
        for row in raw_data:
            key = row["query"].strip().lower()
            grouped.setdefault(key, {"timeseries": [], "landing_pages": set()})
            grouped[key]["timeseries"].append(
                {
                    "date": row["date"],
                    "impressions": float(row.get("impressions", 0) or 0),
                    "clicks": float(row.get("clicks", 0) or 0),
                    "position": float(row.get("position", 0) or 0),
                    "ctr": float(row.get("ctr", 0) or 0),
                }
            )
            grouped[key]["landing_pages"].add(row.get("page", ""))

        normalized = []
        for query, values in grouped.items():
            normalized.append(
                {
                    "query_text": query,
                    "source": "gsc",
                    "timeseries": sorted(values["timeseries"], key=lambda x: x["date"]),
                    "links": [x for x in values["landing_pages"] if x],
                }
            )
        return normalized
