"""RC6.7 immutable change-plan and confirmation contract tests."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from services.protection_models import (
    ChangePlan,
    ChangePlanItem,
    ChangeTarget,
    ConfirmationRequirement,
    OperationRisk,
    PlanConfirmation,
    PlanValidationError,
    Reversibility,
)
from services.protection_service import ProtectionService


def _item(target: ChangeTarget = ChangeTarget.DATABASE) -> ChangePlanItem:
    return ChangePlanItem(
        target=target,
        action="update_title",
        description="Replace a weak title with a reviewed title.",
        book_id=7,
        book_title="Example",
        before_summary="Old title",
        after_summary="Reviewed title",
        reversible=True,
    )


def _plan(**overrides) -> ChangePlan:
    values = {
        "operation_type": "metadata_update",
        "title": "Update reviewed metadata",
        "summary": "Apply one reviewed title correction.",
        "component": "metadata_studio",
        "initiator": "user",
        "affected_book_count": 1,
        "risk": OperationRisk.MEDIUM,
        "reversibility": Reversibility.FULL,
        "confirmation_requirement": ConfirmationRequirement.EXPLICIT,
        "basis_token": "catalogue-revision-12",
        "database_changes": (_item(),),
        "warnings": ("A verified backup will be required before Apply.",),
    }
    values.update(overrides)
    return ChangePlan(**values)


def test_plan_and_items_are_immutable_and_round_trip() -> None:
    plan = _plan()
    restored = ChangePlan.from_dict(plan.to_dict())

    assert restored == plan
    assert plan.change_count == 1
    with pytest.raises(FrozenInstanceError):
        plan.title = "Changed"
    with pytest.raises(FrozenInstanceError):
        plan.database_changes[0].action = "changed"


def test_plan_requires_human_readable_changes_and_consistent_targets() -> None:
    with pytest.raises(PlanValidationError, match="at least one"):
        _plan(database_changes=())
    with pytest.raises(PlanValidationError, match="database target"):
        _plan(database_changes=(_item(ChangeTarget.FILE),))
    with pytest.raises(PlanValidationError, match="smaller"):
        _plan(affected_book_count=0)
    with pytest.raises(PlanValidationError, match="stable identifier"):
        _plan(operation_type="metadata update")


def test_high_risk_plan_requires_explicit_confirmation_contract() -> None:
    with pytest.raises(PlanValidationError, match="explicit confirmation"):
        _plan(
            risk=OperationRisk.HIGH,
            confirmation_requirement=ConfirmationRequirement.NONE,
        )
    with pytest.raises(PlanValidationError, match="clear phrase"):
        _plan(
            risk=OperationRisk.CRITICAL,
            confirmation_requirement=ConfirmationRequirement.TYPE_PHRASE,
            confirmation_phrase="no",
        )


def test_typed_confirmation_is_exact_and_bound_to_plan_and_basis() -> None:
    plan = _plan(
        risk=OperationRisk.HIGH,
        confirmation_requirement=ConfirmationRequirement.TYPE_PHRASE,
        confirmation_phrase="APPLY 1 REVIEWED CHANGE",
    )
    confirmation = PlanConfirmation(
        plan_token=plan.plan_token,
        approved=True,
        confirmer="user",
        confirmation_text="APPLY 1 REVIEWED CHANGE",
    )

    ProtectionService.validate_plan_confirmation(
        plan,
        confirmation,
        current_basis_token=plan.basis_token,
    )

    with pytest.raises(PlanValidationError, match="phrase"):
        ProtectionService.validate_plan_confirmation(
            plan,
            PlanConfirmation(
                plan_token=plan.plan_token,
                approved=True,
                confirmer="user",
                confirmation_text="apply",
            ),
            current_basis_token=plan.basis_token,
        )
    with pytest.raises(PlanValidationError, match="basis changed"):
        ProtectionService.validate_plan_confirmation(
            plan,
            confirmation,
            current_basis_token="catalogue-revision-13",
        )
    with pytest.raises(PlanValidationError, match="already been applied"):
        ProtectionService.validate_plan_confirmation(
            plan,
            confirmation,
            current_basis_token=plan.basis_token,
            applied_plan_tokens=(plan.plan_token,),
        )


def test_expired_plan_cannot_be_approved() -> None:
    created = datetime.now(timezone.utc) - timedelta(minutes=10)
    plan = _plan(
        created_at=created.isoformat(),
        expires_at=(created + timedelta(minutes=1)).isoformat(),
    )
    confirmation = PlanConfirmation(
        plan_token=plan.plan_token,
        approved=True,
        confirmer="user",
    )

    with pytest.raises(PlanValidationError, match="expired"):
        ProtectionService.validate_plan_confirmation(
            plan,
            confirmation,
            current_basis_token=plan.basis_token,
        )


def test_safety_check_plan_truthfully_describes_no_catalogue_change() -> None:
    plan = ProtectionService.build_safety_check_plan()

    assert plan.affected_book_count == 0
    assert plan.file_changes == ()
    assert plan.risk == OperationRisk.LOW
    assert plan.reversibility == Reversibility.NOT_APPLICABLE
    assert "does not change books" in plan.summary
    assert "audit" in plan.database_changes[0].description
