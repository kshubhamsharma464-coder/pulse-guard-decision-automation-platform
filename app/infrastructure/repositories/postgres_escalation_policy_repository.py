from typing import Optional
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.escalation_policy_repository import EscalationPolicyRepository
from app.domain.entities.escalation import EscalationPolicy
from app.infrastructure.db.models import EscalationPolicyORM
from app.infrastructure.db.mappers import escalation_policy_to_domain


class PostgresEscalationPolicyRepository(EscalationPolicyRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def get_for_severity(self, severity_band: str) -> Optional[EscalationPolicy]:
        with self._session_factory() as session:
            row = (
                session.query(EscalationPolicyORM)
                .filter(EscalationPolicyORM.severity_band == severity_band)
                .first()
            )
            return escalation_policy_to_domain(row) if row else None
