from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",  # looked up in the current working directory first
        env_file_depth=2,  # then in the parent directory (the repo root)
        extra="ignore",  # unknown lines in .env are discarded instead of failing
    )

    k_consumers: int = 2
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str  # no default: it is required, startup fails if it is missing
