from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://adaptive_user:change_me_local_only@localhost:5432/adaptive_learning"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    frontend_origin: str = "http://localhost:5173"
    embedding_dimension: int = 768
    # Set JWT_SECRET_KEY in backend/.env. Do not use a public/default secret.
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
