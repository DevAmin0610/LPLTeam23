from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
# Synthetic sample packets ship inside the app package so the Lambda bundle
# (which copies only backend/app) includes them for "Load sample case".
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    app_mode: str = "demo"
    local_data_dir: Path = ROOT / "local-data"
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    aws_region: str = ""
    aws_profile: str = ""
    bedrock_model_id: str = ""
    bedrock_guardrail_id: str = ""
    bedrock_guardrail_version: str = ""
    s3_document_bucket: str = ""
    dynamodb_cases_table: str = ""
    worker_lambda_function_name: str = ""
    # Optional AgentCore Memory (long-term review lessons). Blank disables it;
    # the namespace must match the semantic strategy's template in infra.
    agentcore_memory_id: str = ""
    agentcore_memory_strategy_id: str = ""
    agentcore_memory_namespace: str = "/clearpath/lessons/{memoryStrategyId}/{actorId}/"

    def validate_mode(self, *, worker: bool = False) -> None:
        if self.app_mode not in {"demo", "aws"}:
            raise ValueError("APP_MODE must be demo or aws.")
        if bool(self.agentcore_memory_id.strip()) != bool(
            self.agentcore_memory_strategy_id.strip()
        ):
            raise ValueError(
                "AGENTCORE_MEMORY_ID and AGENTCORE_MEMORY_STRATEGY_ID must be supplied together."
            )
        if self.app_mode == "aws":
            required = [
                "aws_region",
                "bedrock_model_id",
                "bedrock_guardrail_id",
                "bedrock_guardrail_version",
                "s3_document_bucket",
                "dynamodb_cases_table",
            ]

            if not worker:
                required.append("worker_lambda_function_name")

            missing = [
                key.upper() for key in required if not getattr(self, key).strip()
            ]
            if missing:
                raise ValueError("AWS configuration missing: " + ", ".join(missing))
