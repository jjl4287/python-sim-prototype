"""Action schemas - structured state mutations proposed by advisors."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class ActionType(str, Enum):
    """Types of actions that can be taken."""
    # Resource actions
    RESOURCE_TRANSFER = "resource_transfer"   # Move resources between pools
    RESOURCE_PRODUCTION = "resource_production"  # Produce resources
    RESOURCE_CONSUMPTION = "resource_consumption"  # Consume resources
    
    # Population actions
    LEVY_TROOPS = "levy_troops"
    DISMISS_TROOPS = "dismiss_troops"
    RELOCATE_POPULATION = "relocate_population"
    
    # Construction/infrastructure
    BUILD = "build"
    REPAIR = "repair"
    DEMOLISH = "demolish"
    
    # Legal/political
    GRANT_RIGHT = "grant_right"
    REVOKE_RIGHT = "revoke_right"
    ISSUE_DECREE = "issue_decree"
    
    # Diplomacy/factions
    NEGOTIATE = "negotiate"
    REWARD_FACTION = "reward_faction"
    PUNISH_FACTION = "punish_faction"
    
    # Military
    DEPLOY_FORCES = "deploy_forces"
    FORTIFY = "fortify"
    PATROL = "patrol"
    
    # Investigation/survey
    SURVEY = "survey"
    INVESTIGATE = "investigate"
    
    # Custom
    CUSTOM = "custom"


class ActionCost(BaseModel):
    """Resources required to execute an action."""
    treasury: int = 0
    food: int = 0
    timber: int = 0
    iron: int = 0
    labor: int = 0
    time_days: int = 0
    
    model_config = {"extra": "allow"}


class ActionEffect(BaseModel):
    """A single effect of an action."""
    target_type: str  # "resource", "settlement", "faction", "population", etc.
    target_id: Optional[str] = None  # ID of specific target, if applicable
    field: str  # Field to modify
    change: Any  # Value to set or delta to apply
    is_delta: bool = True  # If True, change is added; if False, change replaces
    
    model_config = {"extra": "allow"}


class ActionSpec(BaseModel):
    """A structured action proposal from an advisor."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # What action
    action_type: ActionType
    description: str
    
    # Who proposed it
    proposed_by: str
    proposed_at: datetime = Field(default_factory=datetime.now)
    
    # Target and parameters
    target: Optional[str] = None  # Primary target (settlement, faction, etc.)
    parameters: dict[str, Any] = Field(default_factory=dict)
    
    # Costs
    costs: ActionCost = Field(default_factory=ActionCost)
    
    # Expected effects
    effects: list[ActionEffect] = Field(default_factory=list)
    
    # Approval requirements
    requires_approval: bool = True
    approval_reason: Optional[str] = None
    
    # Execution status
    approved: Optional[bool] = None
    approved_by: Optional[str] = None
    executed: bool = False
    executed_at: Optional[datetime] = None
    
    # Risk/notes
    risks: list[str] = Field(default_factory=list)
    advisor_notes: Optional[str] = None
    
    model_config = {"extra": "allow"}
    
    def is_structural(self) -> bool:
        """Check if this is a structural change requiring player approval."""
        structural_types = {
            ActionType.BUILD,
            ActionType.DEMOLISH,
            ActionType.GRANT_RIGHT,
            ActionType.REVOKE_RIGHT,
            ActionType.ISSUE_DECREE,
            ActionType.LEVY_TROOPS,
            ActionType.DEPLOY_FORCES,
        }
        
        # Also structural if costs are significant
        significant_cost = (
            self.costs.treasury > 50 or
            self.costs.food > 50 or
            self.costs.labor > 20
        )
        
        return self.action_type in structural_types or significant_cost
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        approval = "⏳" if self.approved is None else ("✓" if self.approved else "✗")
        return f"[{self.id}] {approval} {self.action_type.value}: {self.description}"
    
    def cost_summary(self) -> str:
        """Generate cost string."""
        costs = []
        if self.costs.treasury:
            costs.append(f"{self.costs.treasury} gold")
        if self.costs.food:
            costs.append(f"{self.costs.food} food")
        if self.costs.timber:
            costs.append(f"{self.costs.timber} timber")
        if self.costs.iron:
            costs.append(f"{self.costs.iron} iron")
        if self.costs.labor:
            costs.append(f"{self.costs.labor} labor")
        if self.costs.time_days:
            costs.append(f"{self.costs.time_days} days")
        return ", ".join(costs) if costs else "no cost"


class ActionProposal(BaseModel):
    """Input schema for proposing a new action (used by tools)."""
    action_type: ActionType
    description: str
    target: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    costs: dict[str, int] = Field(default_factory=dict)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    advisor_notes: Optional[str] = None
    
    def to_action_spec(self, proposed_by: str) -> ActionSpec:
        """Convert proposal to full ActionSpec."""
        costs = ActionCost(**self.costs)
        effects = [ActionEffect(**e) for e in self.effects]
        
        spec = ActionSpec(
            action_type=self.action_type,
            description=self.description,
            proposed_by=proposed_by,
            target=self.target,
            parameters=self.parameters,
            costs=costs,
            effects=effects,
            risks=self.risks,
            advisor_notes=self.advisor_notes,
        )
        spec.requires_approval = spec.is_structural()
        return spec
