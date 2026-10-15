from pydantic import BaseModel, Field

from wgs_fmt_platform.contracts import EvidenceBundle, StructuredReport


class FactCheckIssue(BaseModel):
    statement_id: str
    code: str
    message: str


class FactCheckResult(BaseModel):
    passed: bool
    checked_statements: int
    supported_statements: int
    issues: list[FactCheckIssue] = Field(default_factory=list)

    @property
    def support_rate(self) -> float:
        if self.checked_statements == 0:
            return 1.0
        return self.supported_statements / self.checked_statements


class ReportFactChecker:
    def check(self, report: StructuredReport, bundle: EvidenceBundle) -> FactCheckResult:
        feature_ids = {item.feature_id for item in bundle.analysis.features}
        claim_ids = {item.claim_id for item in bundle.claims}
        prediction_tasks = {item.task for item in bundle.analysis.predictions}
        issues: list[FactCheckIssue] = []
        checked = 0
        supported = 0

        for statement in report.statements:
            if statement.is_disclaimer:
                continue
            checked += 1
            statement_issues: list[FactCheckIssue] = []
            if not (statement.feature_ids or statement.claim_ids or statement.prediction_tasks):
                statement_issues.append(
                    FactCheckIssue(
                        statement_id=statement.statement_id,
                        code="unsupported_statement",
                        message="statement has no feature, claim, or prediction reference",
                    )
                )
            for feature_id in set(statement.feature_ids) - feature_ids:
                statement_issues.append(
                    FactCheckIssue(
                        statement_id=statement.statement_id,
                        code="unknown_feature",
                        message=f"feature does not exist in analysis: {feature_id}",
                    )
                )
            for claim_id in set(statement.claim_ids) - claim_ids:
                statement_issues.append(
                    FactCheckIssue(
                        statement_id=statement.statement_id,
                        code="unknown_claim",
                        message=f"claim does not exist in evidence bundle: {claim_id}",
                    )
                )
            for task in set(statement.prediction_tasks) - prediction_tasks:
                statement_issues.append(
                    FactCheckIssue(
                        statement_id=statement.statement_id,
                        code="unknown_prediction",
                        message=f"prediction does not exist in analysis: {task}",
                    )
                )
            if not statement_issues:
                supported += 1
            issues.extend(statement_issues)

        return FactCheckResult(
            passed=not issues,
            checked_statements=checked,
            supported_statements=supported,
            issues=issues,
        )

