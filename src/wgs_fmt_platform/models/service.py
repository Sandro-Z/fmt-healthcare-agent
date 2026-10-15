from wgs_fmt_platform.contracts import EvidenceBundle, ModelPrediction
from wgs_fmt_platform.models.base import ModelProvider
from wgs_fmt_platform.models.registry import FileModelRegistry


class ModelInferenceService:
    def __init__(
        self,
        provider: ModelProvider,
        registry: FileModelRegistry,
        model_name: str,
        environment: str = "production",
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.model_name = model_name
        self.environment = environment

    async def predict(self, evidence: EvidenceBundle) -> list[ModelPrediction]:
        deployment = self.registry.deployment(self.model_name, self.environment)
        if deployment is None:
            raise RuntimeError("no deployed model")
        predictions = await self.provider.predict(evidence)
        for prediction in predictions:
            if prediction.model_version != deployment.active.model_version:
                raise RuntimeError("provider model version does not match registry deployment")
        return predictions

