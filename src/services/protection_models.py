"""Immutable RC6.7 change-plan and operation-history contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class PlanValidationError(ValueError):
    """Raised when a proposed change plan is incomplete or unsafe."""


class ChangeTarget(StrEnum):
    DATABASE = "database"
    FILE = "file"


class OperationRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Reversibility(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    NOT_APPLICABLE = "not_applicable"


class ConfirmationRequirement(StrEnum):
    NONE = "none"
    EXPLICIT = "explicit"
    TYPE_PHRASE = "type_phrase"


class OperationStatus(StrEnum):
    PLANNED = "planned"
    APPROVED = "approved"
    CANCELLED = "cancelled"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIAL = "partial"
    UNDONE = "undone"


@dataclass(frozen=True)
class ChangePlanItem:
    """One human-readable intended database or file change."""

    target: ChangeTarget
    action: str
    description: str
    book_id: int | None = None
    book_title: str = ""
    before_summary: str = ""
    after_summary: str = ""
    reversible: bool = False

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "target", ChangeTarget(self.target))
        except ValueError as error:
            raise PlanValidationError("Unknown change target.") from error
        action = str(self.action).strip()
        description = str(self.description).strip()
        if not action or not description:
            raise PlanValidationError(
                "Every plan item requires an action and description."
            )
        if self.book_id is not None and int(self.book_id) <= 0:
            raise PlanValidationError("Book IDs must be positive.")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "book_title", str(self.book_title).strip())
        object.__setattr__(
            self,
            "before_summary",
            str(self.before_summary).strip(),
        )
        object.__setattr__(
            self,
            "after_summary",
            str(self.after_summary).strip(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target.value,
            "action": self.action,
            "description": self.description,
            "book_id": self.book_id,
            "book_title": self.book_title,
            "before_summary": self.before_summary,
            "after_summary": self.after_summary,
            "reversible": self.reversible,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ChangePlanItem":
        return cls(
            target=ChangeTarget(str(value["target"])),
            action=str(value["action"]),
            description=str(value["description"]),
            book_id=(
                int(value["book_id"])
                if value.get("book_id") is not None
                else None
            ),
            book_title=str(value.get("book_title", "")),
            before_summary=str(value.get("before_summary", "")),
            after_summary=str(value.get("after_summary", "")),
            reversible=bool(value.get("reversible", False)),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_expiry() -> str:
    return (
        datetime.now(timezone.utc) + timedelta(minutes=30)
    ).isoformat()


@dataclass(frozen=True)
class ChangePlan:
    """Detached, immutable description of a proposed protected operation."""

    operation_type: str
    title: str
    summary: str
    component: str
    initiator: str
    affected_book_count: int
    risk: OperationRisk
    reversibility: Reversibility
    confirmation_requirement: ConfirmationRequirement
    basis_token: str
    database_changes: tuple[ChangePlanItem, ...] = ()
    file_changes: tuple[ChangePlanItem, ...] = ()
    warnings: tuple[str, ...] = ()
    confirmation_phrase: str = ""
    plan_token: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=_utc_now)
    expires_at: str = field(default_factory=_default_expiry)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "database_changes",
            tuple(self.database_changes),
        )
        object.__setattr__(self, "file_changes", tuple(self.file_changes))
        object.__setattr__(
            self,
            "warnings",
            tuple(str(warning).strip() for warning in self.warnings),
        )
        try:
            object.__setattr__(self, "risk", OperationRisk(self.risk))
            object.__setattr__(
                self,
                "reversibility",
                Reversibility(self.reversibility),
            )
            object.__setattr__(
                self,
                "confirmation_requirement",
                ConfirmationRequirement(
                    self.confirmation_requirement
                ),
            )
        except ValueError as error:
            raise PlanValidationError(
                "The plan contains an unknown safety classification."
            ) from error

        text_fields = {
            "operation type": self.operation_type,
            "title": self.title,
            "summary": self.summary,
            "component": self.component,
            "initiator": self.initiator,
            "basis token": self.basis_token,
            "plan token": self.plan_token,
        }
        for label, value in text_fields.items():
            if not str(value).strip():
                raise PlanValidationError(
                    f"Change plan {label} cannot be empty."
                )
        if not all(
            character.isalnum() or character in "._-"
            for character in self.operation_type
        ):
            raise PlanValidationError(
                "Operation type must be a stable identifier."
            )
        if self.affected_book_count < 0:
            raise PlanValidationError(
                "Affected-book count cannot be negative."
            )
        if not self.database_changes and not self.file_changes:
            raise PlanValidationError(
                "A change plan must describe at least one intended change."
            )
        if any(
            item.target != ChangeTarget.DATABASE
            for item in self.database_changes
        ):
            raise PlanValidationError(
                "Database changes must use the database target."
            )
        if any(
            item.target != ChangeTarget.FILE
            for item in self.file_changes
        ):
            raise PlanValidationError(
                "File changes must use the file target."
            )
        identified_books = {
            item.book_id
            for item in self.database_changes + self.file_changes
            if item.book_id is not None
        }
        if len(identified_books) > self.affected_book_count:
            raise PlanValidationError(
                "Affected-book count is smaller than the listed books."
            )
        if any(not warning for warning in self.warnings):
            raise PlanValidationError("Plan warnings cannot be blank.")
        if (
            self.risk in {OperationRisk.HIGH, OperationRisk.CRITICAL}
            and self.confirmation_requirement
            == ConfirmationRequirement.NONE
        ):
            raise PlanValidationError(
                "High-risk plans require explicit confirmation."
            )
        if (
            self.confirmation_requirement
            == ConfirmationRequirement.TYPE_PHRASE
            and len(self.confirmation_phrase.strip()) < 4
        ):
            raise PlanValidationError(
                "Typed confirmation requires a clear phrase."
            )
        created_at = _parse_timestamp(self.created_at, "creation")
        expires_at = _parse_timestamp(self.expires_at, "expiry")
        if expires_at <= created_at:
            raise PlanValidationError(
                "Plan expiry must be after its creation time."
            )

    @property
    def change_count(self) -> int:
        return len(self.database_changes) + len(self.file_changes)

    def is_expired(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return current >= _parse_timestamp(self.expires_at, "expiry")

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_type": self.operation_type,
            "title": self.title,
            "summary": self.summary,
            "component": self.component,
            "initiator": self.initiator,
            "affected_book_count": self.affected_book_count,
            "risk": self.risk.value,
            "reversibility": self.reversibility.value,
            "confirmation_requirement": (
                self.confirmation_requirement.value
            ),
            "basis_token": self.basis_token,
            "database_changes": [
                item.to_dict() for item in self.database_changes
            ],
            "file_changes": [
                item.to_dict() for item in self.file_changes
            ],
            "warnings": list(self.warnings),
            "confirmation_phrase": self.confirmation_phrase,
            "plan_token": self.plan_token,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ChangePlan":
        return cls(
            operation_type=str(value["operation_type"]),
            title=str(value["title"]),
            summary=str(value["summary"]),
            component=str(value["component"]),
            initiator=str(value["initiator"]),
            affected_book_count=int(value["affected_book_count"]),
            risk=OperationRisk(str(value["risk"])),
            reversibility=Reversibility(str(value["reversibility"])),
            confirmation_requirement=ConfirmationRequirement(
                str(value["confirmation_requirement"])
            ),
            basis_token=str(value["basis_token"]),
            database_changes=tuple(
                ChangePlanItem.from_dict(item)
                for item in value.get("database_changes", ())
            ),
            file_changes=tuple(
                ChangePlanItem.from_dict(item)
                for item in value.get("file_changes", ())
            ),
            warnings=tuple(
                str(warning) for warning in value.get("warnings", ())
            ),
            confirmation_phrase=str(
                value.get("confirmation_phrase", "")
            ),
            plan_token=str(value["plan_token"]),
            created_at=str(value["created_at"]),
            expires_at=str(value["expires_at"]),
        )


@dataclass(frozen=True)
class PlanConfirmation:
    """Detached confirmation evidence for one exact plan token."""

    plan_token: str
    approved: bool
    confirmer: str
    confirmation_text: str = ""
    confirmed_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.plan_token.strip() or not self.confirmer.strip():
            raise PlanValidationError(
                "Confirmation requires a plan token and confirmer."
            )
        _parse_timestamp(self.confirmed_at, "confirmation")

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_token": self.plan_token,
            "approved": self.approved,
            "confirmer": self.confirmer,
            "confirmation_text": self.confirmation_text,
            "confirmed_at": self.confirmed_at,
        }


@dataclass(frozen=True)
class OperationItemRecord:
    sequence: int
    target: ChangeTarget
    action: str
    description: str
    book_id: int | None
    book_title: str
    before_summary: str
    after_summary: str
    reversible: bool
    status: str
    error_summary: str = ""
    inverse_json: str = ""


@dataclass(frozen=True)
class OperationRecord:
    """One persistent operation with its original immutable plan."""

    operation_id: int
    operation_token: str
    plan: ChangePlan
    status: OperationStatus
    created_at: str
    updated_at: str
    started_at: str = ""
    finished_at: str = ""
    confirmation: PlanConfirmation | None = None
    backup_identity: str = ""
    error_summary: str = ""
    rollback_outcome: str = ""
    source_operation_id: int | None = None
    items: tuple[OperationItemRecord, ...] = ()


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise PlanValidationError(
            f"Plan {label} timestamp is invalid."
        ) from error
    if timestamp.tzinfo is None:
        raise PlanValidationError(
            f"Plan {label} timestamp must include a timezone."
        )
    return timestamp
