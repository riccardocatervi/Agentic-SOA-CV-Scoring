from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # TODO env_file and extras
    )

    # TODO k_consumers, llm_base_url, llm_api_key