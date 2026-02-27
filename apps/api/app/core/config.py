from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Content Demand Capture Agent"
    database_url: str = "sqlite:///./local.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    openai_api_key: str | None = None
    our_domain: str = "zeni.ai"
    brand_terms: str = "zeni,zeni ai,zeni.ai"
    gsc_site_url: str | None = None
    gsc_credentials_json: str | None = None
    semrush_api_key: str | None = None
    ahrefs_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
