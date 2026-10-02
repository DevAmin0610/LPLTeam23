from app.config import Settings
from app.providers.interfaces import Providers
from app.providers.aws.adapters import (
    TextractExtractor,
    GuardrailPrivacyFilter,
    BedrockExplanationGenerator,
    S3DocumentStorage,
    DynamoCaseStorage,
    DynamoMemoryStore,
    LambdaJobDispatcher,
)
from app.services.cases import CaseService


def create_aws_service(
    settings: Settings,
    *,
    worker: bool = False,
) -> CaseService:
    if settings.app_mode != "aws":
        raise ValueError("AWS runtime requires APP_MODE=aws.")

    settings.validate_mode(worker=worker)

    providers = Providers(
        extraction=TextractExtractor(settings),
        privacy=GuardrailPrivacyFilter(settings),
        explanations=BedrockExplanationGenerator(settings),
        documents=S3DocumentStorage(settings),
        cases=DynamoCaseStorage(settings),
        dispatcher=None if worker else LambdaJobDispatcher(settings),
        # Review memory is read and written by the API only.
        memory=None if worker else DynamoMemoryStore(settings),
    )

    return CaseService(providers)