import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_ID: str = os.getenv("GOOGLE_CLOUD_PROJECT", "genesis-rpg")
    REGION: str = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    GEMINI_FLASH_MODEL: str = os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash")
    IMAGEN_MODEL: str = os.getenv("IMAGEN_MODEL", "imagen-4")
    VEO_MODEL: str = os.getenv("VEO_MODEL", "veo-3")

    FIRESTORE_DATABASE: str = os.getenv("FIRESTORE_DATABASE", "(default)")
    STORAGE_BUCKET: str = os.getenv("STORAGE_BUCKET", f"{PROJECT_ID}-media")
    CLOUD_TASKS_QUEUE: str = os.getenv("CLOUD_TASKS_QUEUE", "video-generation")

    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000"
    ).split(",")

    ART_STYLE: str = os.getenv(
        "ART_STYLE",
        "dark fantasy illustration, detailed, dramatic lighting, painterly style"
    )


settings = Settings()
