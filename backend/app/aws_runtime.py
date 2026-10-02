from app.config import Settings
from app.providers.interfaces import Providers
from app.providers.aws.adapters import (
    TextractExtractor,
    GuardrailPrivacyFilter,
    BedrockExplanationGenerator,
    S3DocumentStorage,
    DynamoCaseStorage,
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
    )

    return CaseService(providers)