from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

from wgs_fmt_platform.paths import PROJECT_ROOT, project_path, workspace_root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_prefix="WGS_", extra="ignore"
    )

    env: str = "development"
    workspace: Path = Path("./var")
    mproject_bin: str = "mProject"
    mproject_database: Path = Path("./var/databases/human-gut")
    claim_api_url: str = "http://127.0.0.1:8080"
    claim_api_token: str = ""
    claim_api_openapi_path: str = "/openapi.json"
    claim_api_search_path: str = ""
    claim_api_search_method: str = "AUTO"
    claim_api_version_path: str = ""
    claim_api_timeout: float = 20.0
    claim_api_knowledge_base_id: int = 7
    claim_api_scan_limit: int = 1000
    claim_api_startup_probe: bool = True
    claim_api_probe_required: bool = False
    default_knowledge_version: str = "current"
    default_model_version: str = "baseline-v1"
    feature_schema_version: str = "feature-schema-v1"
    report_template_version: str = "report-template-v1"
    metadata_database_url: str = "sqlite:///./var/metadata.db"
    mysql_url: str = "mysql+pymysql://wgs:change-me@127.0.0.1:3306/wgs_fmt"
    mysql_pool_size: int = 10
    redis_url: str = "redis://127.0.0.1:6379/0"
    memory_short_ttl_seconds: int = 86400
    memory_long_ttl_seconds: int = 0
    elasticsearch_url: str = "http://127.0.0.1:9200"
    elasticsearch_index: str = "wgs-knowledge"
    elasticsearch_api_key: str = ""
    embedding_dimensions: int = 384
    graph_text_search_path: str = "/api/knowledge-bases/{knowledge_base_id}/claims"
    artifact_root: Path = Path("./var/artifacts")
    workflow_engine: str = "local"
    nextflow_bin: str = "nextflow"
    nextflow_pipeline: Path = Path("./workflows/main.nf")
    model_registry_root: Path = Path("./var/model-registry")

    @model_validator(mode="after")
    def resolve_runtime_paths(self) -> "Settings":
        self.workspace = (
            project_path(self.workspace)
            if "workspace" in self.model_fields_set
            else workspace_root()
        )
        for name, suffix in {
            "mproject_database": "databases/human-gut",
            "artifact_root": "artifacts",
            "model_registry_root": "model-registry",
        }.items():
            value = getattr(self, name)
            setattr(
                self,
                name,
                project_path(value) if name in self.model_fields_set else self.workspace / suffix,
            )
        if "metadata_database_url" not in self.model_fields_set:
            self.metadata_database_url = f"sqlite:///{self.workspace / 'metadata.db'}"
        self.nextflow_pipeline = project_path(self.nextflow_pipeline)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
