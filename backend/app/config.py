from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    app_mode: str = "demo"
    local_data_dir: Path = ROOT / "local-data"
    cors_allowed_origins: str = "http://localhost:5173"
    aws_region: str = ""
    aws_profile: str = ""
    bedrock_model_id: str = ""
    bedrock_guardrail_id: str = ""
    bedrock_guardrail_version: str = ""
    s3_document_bucket: str = ""
    dynamodb_cases_table: str = ""
    worker_lambda_function_name: str = ""

    def validate_mode(self) -> None:
        if self.app_mode not in {"demo", "aws"}:
            raise ValueError("APP_MODE must be demo or aws.")
        if self.app_mode == "aws":
            required = [
                "aws_region",
                "bedrock_model_id",
                "bedrock_guardrail_id",
                "bedrock_guardrail_version",
                "s3_document_bucket",
                "dynamodb_cases_table",
                "worker_lambda_function_name",
            ]
            missing = [
                key.upper() for key in required if not getattr(self, key).strip()
            ]
            if missing:
                raise ValueError("AWS configuration missing: " + ", ".join(missing))
            raise ValueError(
                "AWS composition is not enabled in this starter. See docs/handoff.md; no demo fallback is permitted."
            )
