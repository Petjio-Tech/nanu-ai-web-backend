from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_KEY: str

    PETJIO_ANDROID_APP_URL: str

    CANONICAL_DOMAIN: str = "https://www.petjio.in"
    SITEMAP_URL: str = "https://www.petjio.in/sitemap.xml"
    CRAWL_EXCLUDE_SUBSTRINGS: str = "/admin,/wp-admin,/login"
    CRAWL_EXCLUDE_DOMAINS: str = "admin.petjio.in"

    DATABASE_URL: str
    RAG_TOP_K: int = 6
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    @property
    def exclude_substrings(self) -> list[str]:
        return [s.strip() for s in self.CRAWL_EXCLUDE_SUBSTRINGS.split(",") if s.strip()]

    @property
    def exclude_domains(self) -> list[str]:
        return [s.strip() for s in self.CRAWL_EXCLUDE_DOMAINS.split(",") if s.strip()]


settings = Settings()