from app.domain.entities.incident import Incident


def test_remote_fix_sequencing_tries_remote_before_dispatch(use_case):
    """R033 has a sequencing hint; even though it suppresses the flat dispatchEngineer
    flag to False, the execution plan should still show remote-restart-then-dispatch
    as an ordered fallback (design doc §3d)."""
    incident = Incident(
        incident_id="INC-REMOTE",
        payload={"affectedUsers": 12000},
        enriched_context={"remoteFixAvailable": True},
    )
    decision = use_case.execute(incident)

    assert decision.actions["dispatchEngineer"] is False
    plan_types = [step["type"] for step in decision.execution_plan]
    assert plan_types.index("remoteRestart") < plan_types.index("dispatchEngineer")
    dispatch_step = next(s for s in decision.execution_plan if s["type"] == "dispatchEngineer")
    assert "fallback" in dispatch_step["condition"] or "fails" in dispatch_step["condition"]
