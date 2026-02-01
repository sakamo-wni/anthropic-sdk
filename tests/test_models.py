"""Tests for data models."""

from datetime import datetime, timezone

import pytest

from cloudwatch_triage_agent.models.schemas import (
    Environment,
    InvestigationReport,
    RootCauseCandidate,
    TriageContext,
)


class TestEnvironment:
    """Tests for Environment enum."""

    def test_dev_environment(self) -> None:
        assert Environment.DEV.value == "dev"

    def test_prod_environment(self) -> None:
        assert Environment.PROD.value == "prod"


class TestTriageContext:
    """Tests for TriageContext model."""

    def test_create_triage_context(self) -> None:
        now = datetime.now(timezone.utc)
        context = TriageContext(
            service="test-service",
            environment=Environment.PROD,
            start_time=now,
            end_time=now,
            symptoms="Test symptoms",
            log_group="/aws/lambda/test",
        )

        assert context.service == "test-service"
        assert context.environment == Environment.PROD
        assert context.log_group == "/aws/lambda/test"


class TestRootCauseCandidate:
    """Tests for RootCauseCandidate model."""

    def test_create_root_cause(self) -> None:
        rc = RootCauseCandidate(
            rank=1,
            summary="Test cause",
            evidence=["Evidence 1", "Evidence 2"],
            confidence="high",
        )

        assert rc.rank == 1
        assert rc.confidence == "high"
        assert len(rc.evidence) == 2

    def test_rank_validation(self) -> None:
        with pytest.raises(ValueError):
            RootCauseCandidate(
                rank=5,  # Invalid: must be 1-3
                summary="Test",
                evidence=[],
                confidence="low",
            )


class TestInvestigationReport:
    """Tests for InvestigationReport model."""

    def test_create_report(self) -> None:
        now = datetime.now(timezone.utc)
        context = TriageContext(
            service="test-service",
            environment=Environment.PROD,
            start_time=now,
            end_time=now,
            symptoms="Test symptoms",
            log_group="/aws/lambda/test",
        )

        report = InvestigationReport(
            context=context,
            root_causes=[
                RootCauseCandidate(
                    rank=1,
                    summary="Primary cause",
                    evidence=["Evidence"],
                    confidence="high",
                )
            ],
            recommendations=["Fix the issue"],
        )

        assert report.context.service == "test-service"
        assert len(report.root_causes) == 1
        assert report.root_causes[0].rank == 1
