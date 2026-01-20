"""State change schemas - for proposing and validating world state mutations."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class ChangeType(str, Enum):
    """Types of state changes."""
    SET_EXTENSION = "set_extension"      # Set/update an extension path
    DELETE_EXTENSION = "delete_extension"  # Remove an extension path
    ADD_RULE = "add_rule"                 # Create a dynamic rule
    MODIFY_CORE = "modify_core"           # Modify core state (resources, etc.)
    ADD_ENTITY = "add_entity"             # Add settlement, faction, etc.
    REMOVE_ENTITY = "remove_entity"       # Remove an entity


class ValidationStatus(str, Enum):
    """Status of change validation."""
    PENDING = "pending"
    PASSED_STRUCTURAL = "passed_structural"
    PASSED_SEMANTIC = "passed_semantic"
    APPROVED = "approved"         # Fully validated, can be applied
    REJECTED_STRUCTURAL = "rejected_structural"
    REJECTED_SEMANTIC = "rejected_semantic"
    REJECTED_HUMAN = "rejected_human"


class ValidationIssue(BaseModel):
    """A specific issue found during validation."""
    stage: str  # "structural" or "semantic"
    severity: str  # "error", "warning", "info"
    code: str  # Machine-readable error code
    message: str  # Human-readable explanation
    path: Optional[str] = None  # Related state path if applicable
    suggestion: Optional[str] = None  # How to fix it


class SemanticValidation(BaseModel):
    """Results of semantic (LLM) validation."""
    is_consistent: bool = Field(description="Does this fit the established world?")
    is_specific: bool = Field(description="Is this specific enough, not generic slop?")
    has_contradictions: bool = Field(description="Does this contradict existing state?")
    contradictions: list[str] = Field(default_factory=list, description="List of contradictions found")
    quality_score: int = Field(default=50, ge=0, le=100, description="Quality rating 0-100")
    quality_issues: list[str] = Field(default_factory=list, description="Quality problems found")
    cascading_effects: list[dict[str, Any]] = Field(
        default_factory=list, 
        description="Other state changes that should happen as a result"
    )
    reasoning: str = Field(default="", description="Explanation of validation decision")


class StateChange(BaseModel):
    """A proposed mutation to the world state."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # What is being changed
    change_type: ChangeType
    path: str = Field(description="Dot-notation path for the change")
    old_value: Optional[Any] = None
    new_value: Any = None
    reason: str = Field(description="Why this change is being made")
    
    # Who proposed it
    proposed_by: str  # Advisor role, "orchestrator", or "player"
    proposed_at: datetime = Field(default_factory=datetime.now)
    
    # Validation status
    status: ValidationStatus = ValidationStatus.PENDING
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    semantic_validation: Optional[SemanticValidation] = None
    
    # If approved, when it was applied
    applied_at: Optional[datetime] = None
    applied_by: Optional[str] = None
    
    # For cascading changes
    triggered_by: Optional[str] = None  # ID of parent change
    cascaded_changes: list[str] = Field(default_factory=list)  # IDs of child changes
    
    model_config = {"extra": "allow"}
    
    def add_issue(self, stage: str, severity: str, code: str, message: str, 
                  path: Optional[str] = None, suggestion: Optional[str] = None):
        """Add a validation issue."""
        self.validation_issues.append(ValidationIssue(
            stage=stage,
            severity=severity,
            code=code,
            message=message,
            path=path,
            suggestion=suggestion,
        ))
    
    def has_errors(self) -> bool:
        """Check if there are any error-level issues."""
        return any(i.severity == "error" for i in self.validation_issues)
    
    def is_approved(self) -> bool:
        """Check if this change is approved and ready to apply."""
        return self.status == ValidationStatus.APPROVED
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        status_emoji = {
            ValidationStatus.PENDING: "⏳",
            ValidationStatus.PASSED_STRUCTURAL: "🔧",
            ValidationStatus.PASSED_SEMANTIC: "🧠",
            ValidationStatus.APPROVED: "✓",
            ValidationStatus.REJECTED_STRUCTURAL: "❌",
            ValidationStatus.REJECTED_SEMANTIC: "🚫",
            ValidationStatus.REJECTED_HUMAN: "👎",
        }
        emoji = status_emoji.get(self.status, "?")
        return f"[{self.id}] {emoji} {self.change_type.value}: {self.path} - {self.reason[:50]}"


class StateChangeBatch(BaseModel):
    """A batch of related state changes (e.g., cascading effects)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    changes: list[StateChange] = Field(default_factory=list)
    triggered_by: Optional[str] = None  # What caused this batch
    status: ValidationStatus = ValidationStatus.PENDING
    
    def add_change(self, change: StateChange) -> None:
        """Add a change to the batch."""
        self.changes.append(change)
    
    def all_approved(self) -> bool:
        """Check if all changes in the batch are approved."""
        return all(c.is_approved() for c in self.changes)
