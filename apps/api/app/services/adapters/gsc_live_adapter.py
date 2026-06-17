from datetime import date, timedelta
from urllib.parse import quote

import httpx


class GSCLiveAdapter:
    def __init__(self, access_token: str, site_url: str):
        self.access_token = access_token
        self.site_url = site_url

    def fetch(self, days: int = 90):
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days)
        encoded_site = quote(self.site_url, safe="")
        endpoint = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/searchAnalytics/query"

        payload = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": ["query", "page", "date"],
            "rowLimit": 25000,
        }

        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        rows = []
        for row in data.get("rows", []):
            keys = row.get("keys", [])
            if len(keys) < 3:
                continue
            query, page, day = keys[0], keys[1], keys[2]
            clicks = float(row.get("clicks", 0))
            impressions = float(row.get("impressions", 0))
            ctr = float(row.get("ctr", 0))
            position = float(row.get("position", 0))
            rows.append(
                {
                    "date": day,
                    "query": query,
                    "page": page,
                    "impressions": impressions,
                    "clicks": clicks,
                    "position": position,
                    "ctr": ctr,
                }
            )
        return rows
