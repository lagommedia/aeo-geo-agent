from pydantic import BaseModel


class MetricPoint(BaseModel):
    label: str
    value: float


class MetricsOut(BaseModel):
    ai_citation_share: list[MetricPoint]
    non_branded_pipeline: list[MetricPoint]
    competitor_velocity: list[MetricPoint]
