from functools import lru_cache
from uuid import UUID
from pydantic import BaseModel, ConfigDict, ValidationError
from app.aws_runtime import create_aws_service
from app.config import Settings


class AnalysisEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    run_id: UUID


@lru_cache(maxsize=1)
def get_service():
    return create_aws_service(Settings(), worker=True)


def handler(event, context):
    try:
        job = AnalysisEvent.model_validate(event)
    except ValidationError:
        raise ValueError("Invalid analysis event.") from None
    get_service().process(str(job.case_id), str(job.run_id))
