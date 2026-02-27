from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from app.services.adapters.base import BaseAdapter


class CompetitorVelocityAdapter(BaseAdapter):
    def __init__(self, directory: str = "sample_data/competitors"):
        self.directory = Path(directory)

    def validate_config(self) -> None:
        if not self.directory.exists():
            raise FileNotFoundError(f"Competitor directory missing: {self.directory}")

    def fetch(self):
        self.validate_config()
        return list(self.directory.glob("*.xml"))

    def normalize(self, raw_data):
        weekly = defaultdict(int)
        for xml_file in raw_data:
            root = ElementTree.parse(xml_file).getroot()
            for url in root.findall("{*}url"):
                lastmod = url.find("{*}lastmod")
                if lastmod is None or not lastmod.text:
                    continue
                dt = datetime.fromisoformat(lastmod.text.replace("Z", "+00:00"))
                iso_week = f"{dt.year}-W{dt.isocalendar().week:02d}"
                weekly[iso_week] += 1

        return [{"week": week, "posts": count} for week, count in sorted(weekly.items())]
