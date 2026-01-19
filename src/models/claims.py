"""Claim system schemas - for proposing and validating new world facts."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class ClaimStatus(str, Enum):
    """Status of a claim in the validation pipeline."""
    PENDING = "pending"      # Awaiting review
    CONFIRMED = "confirmed"  # Accepted as canon
    DENIED = "denied"        # Rejected
    CONTESTED = "contested"  # Needs more information or arbitration


class ClaimType(str, Enum):
    """Types of claims that can be made about the world."""
    # Existence claims
    ENTITY_EXISTS = "entity_exists"       # A settlement, terrain, etc. exists
    ENTITY_PROPERTY = "entity_property"   # Property of existing entity
    
    # Relationship claims  
    RELATIONSHIP = "relationship"         # Connection between entities
    OWNERSHIP = "ownership"               # Legal ownership/rights
    
    # State claims
    RESOURCE_LEVEL = "resource_level"     # Current resource amounts
    POPULATION_STATE = "population_state" # Population conditions
    
    # Event claims
    HISTORICAL_EVENT = "historical_event" # Something that happened in the past
    CURRENT_CONDITION = "current_condition" # Present state of affairs
    
    # Custom/other
    CUSTOM = "custom"


class ClaimEvidence(BaseModel):
    """Evidence supporting a claim."""
    type: str  # "observation", "report", "survey", "historical", "logical"
    description: str
    confidence: int = Field(default=50, ge=0, le=100)
    source: Optional[str] = None  # Who/what provided this evidence


class Claim(BaseModel):
    """A proposed fact about the world that needs validation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # What is being claimed
    claim_type: ClaimType
    description: str
    
    # Structured claim data (depends on claim_type)
    claim_data: dict[str, Any] = Field(default_factory=dict)
    
    # Provenance
    proposed_by: str  # Advisor role or "player" or "orchestrator"
    proposed_at: datetime = Field(default_factory=datetime.now)
    proposed_tick: int = 0  # Game tick when proposed
    
    # Evidence
    evidence: list[ClaimEvidence] = Field(default_factory=list)
    
    # Status tracking
    status: ClaimStatus = ClaimStatus.PENDING
    resolved_by: Optional[str] = None  # Who resolved it
    resolved_at: Optional[datetime] = None
    resolution_reason: Optional[str] = None
    
    # If confirmed, what changes to apply
    effects_on_confirm: dict[str, Any] = Field(default_factory=dict)
    
    model_config = {"extra": "allow"}
    
    def confirm(self, resolver: str, reason: Optional[str] = None) -> None:
        """Mark claim as confirmed."""
        self.status = ClaimStatus.CONFIRMED
        self.resolved_by = resolver
        self.resolved_at = datetime.now()
        self.resolution_reason = reason
    
    def deny(self, resolver: str, reason: Optional[str] = None) -> None:
        """Mark claim as denied."""
        self.status = ClaimStatus.DENIED
        self.resolved_by = resolver
        self.resolved_at = datetime.now()
        self.resolution_reason = reason
    
    def contest(self, resolver: str, reason: Optional[str] = None) -> None:
        """Mark claim as contested (needs more info)."""
        self.status = ClaimStatus.CONTESTED
        self.resolved_by = resolver
        self.resolved_at = datetime.now()
        self.resolution_reason = reason
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        status_emoji = {
            ClaimStatus.PENDING: "⏳",
            ClaimStatus.CONFIRMED: "✓",
            ClaimStatus.DENIED: "✗",
            ClaimStatus.CONTESTED: "⚠",
        }
        return f"[{self.id}] {status_emoji[self.status]} {self.claim_type.value}: {self.description}"


class ClaimProposal(BaseModel):
    """Input schema for proposing a new claim (used by tools)."""
    claim_type: ClaimType
    description: str
    claim_data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    effects_on_confirm: dict[str, Any] = Field(default_factory=dict)
    
    def to_claim(self, proposed_by: str, current_tick: int) -> Claim:
        """Convert proposal to a full Claim object."""
        evidence_objs = [
            ClaimEvidence(**e) if isinstance(e, dict) else e 
            for e in self.evidence
        ]
        return Claim(
            claim_type=self.claim_type,
            description=self.description,
            claim_data=self.claim_data,
            proposed_by=proposed_by,
            proposed_tick=current_tick,
            evidence=evidence_objs,
            effects_on_confirm=self.effects_on_confirm,
        )
