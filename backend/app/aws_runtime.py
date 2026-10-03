from app.config import Settings
from app.providers.interfaces import Providers
from app.providers.aws.agentcore import AgentCoreLessons
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
        # The API records approved lessons; the worker reads them so explanations
        # can mention past reviewer decisions (requires read access in both roles).
        memory=DynamoMemoryStore(settings),
        lessons=AgentCoreLessons(settings) if settings.agentcore_memory_id else None,
    )

    return CaseService(providers)
