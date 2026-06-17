from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Content Demand Capture Agent"
    database_url: str = "sqlite:///./local.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    our_domain: str = "zeni.ai"
    brand_terms: str = "zeni,zeni ai,zeni.ai"
    gsc_site_url: str | None = None
    gsc_credentials_json: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str = "http://localhost:3000/oauth/google/callback"
    google_oauth_scopes: str = "https://www.googleapis.com/auth/webmasters.readonly"
    semrush_api_key: str | None = None
    ahrefs_api_key: str | None = None
    source_encryption_key: str | None = None
    web_base_url: str = "http://localhost:3000"
    auto_seed_on_startup: bool = False
    demo_email: str = "demo@zeni.ai"
    demo_password: str = "demo1234"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
