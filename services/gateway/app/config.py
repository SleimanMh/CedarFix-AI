from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    text_service_url: str = "http://text-understanding:8001"
    image_service_url: str = "http://image-understanding:8002"
    embedding_service_url: str = "http://embedding-service:8003"
    clustering_service_url: str = "http://clustering-service:8004"
    priority_service_url: str = "http://priority-engine:8005"
    routing_service_url: str = "http://routing-engine:8006"
    explanation_service_url: str = "http://explanation-service:8007"
    database_url: str = "postgresql://cedarfix:cedarfix_secret@postgres:5432/cedarfix"
    uploads_dir: str = "/data/uploads"

    class Config:
        env_file = ".env"

settings = Settings()
