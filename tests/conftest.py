import pytest
from app.infrastructure.repositories.in_memory_rule_repository import InMemoryRuleRepository
from app.application.use_cases.evaluate_incident import EvaluateIncidentUseCase


@pytest.fixture
def rule_repo():
    return InMemoryRuleRepository()


@pytest.fixture
def use_case(rule_repo):
    return EvaluateIncidentUseCase(rule_repo)


@pytest.fixture
def inc_101_payload():
    """Exact example incident from the problem statement."""
    return {
        "incidentId": "INC-101",
        "towerId": "T-Delhi-101",
        "region": "Delhi",
        "affectedUsers": 15000,
        "vipCustomersAffected": True,
        "networkLoad": 94,
        "slaTier": "Gold",
        "maintenanceWindow": False,
        "weatherSeverity": "Moderate",
        "historicalFailures": 4,
        "incidentType": "Tower Down",
    }
