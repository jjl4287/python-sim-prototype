"""Event schemas - chronological record of everything that happens."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class EventType(str, Enum):
    """Categories of events."""
    # System events
    GAME_START = "game_start"
    TIME_ADVANCE = "time_advance"
    SAVE = "save"
    LOAD = "load"
    
    # Player events
    PLAYER_ORDER = "player_order"
    PLAYER_QUERY = "player_query"
    PLAYER_APPROVAL = "player_approval"
    PLAYER_DENIAL = "player_denial"
    
    # Advisor events
    ADVISOR_RESPONSE = "advisor_response"
    ADVISOR_PROPOSAL = "advisor_proposal"
    
    # Claim events
    CLAIM_PROPOSED = "claim_proposed"
    CLAIM_CONFIRMED = "claim_confirmed"
    CLAIM_DENIED = "claim_denied"
    CLAIM_CONTESTED = "claim_contested"
    
    # Action events
    ACTION_PROPOSED = "action_proposed"
    ACTION_APPROVED = "action_approved"
    ACTION_REJECTED = "action_rejected"
    ACTION_EXECUTED = "action_executed"
    
    # World events
    RESOURCE_CHANGE = "resource_change"
    POPULATION_CHANGE = "population_change"
    FACTION_CHANGE = "faction_change"
    INFRASTRUCTURE_CHANGE = "infrastructure_change"
    
    # Narrative events
    INCIDENT = "incident"
    DISCOVERY = "discovery"
    ARRIVAL = "arrival"
    DEPARTURE = "departure"
    CONFLICT = "conflict"
    RESOLUTION = "resolution"
    
    # Custom
    CUSTOM = "custom"


class EventEffect(BaseModel):
    """An effect that resulted from an event."""
    target_type: str  # "resource", "faction", "population", etc.
    target_id: Optional[str] = None
    field: str
    old_value: Any = None
    new_value: Any = None
    description: Optional[str] = None


class Event(BaseModel):
    """A recorded event in the game history."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # When
    timestamp: datetime = Field(default_factory=datetime.now)
    game_tick: int = 0
    game_date: str = "Day 1"
    
    # What
    event_type: EventType
    description: str
    
    # Who/what caused it
    actor: str  # "player", "steward", "marshal", "chancellor", "system", etc.
    
    # Effects
    effects: list[EventEffect] = Field(default_factory=list)
    
    # Related objects
    related_claim_id: Optional[str] = None
    related_action_id: Optional[str] = None
    
    # Additional context
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    # Visibility
    visible_to_player: bool = True
    
    model_config = {"extra": "allow"}
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        return f"[{self.game_date}] {self.actor}: {self.description}"
    
    def detailed(self) -> str:
        """Generate detailed event description."""
        lines = [
            f"Event: {self.event_type.value}",
            f"Date: {self.game_date} (Tick {self.game_tick})",
            f"Actor: {self.actor}",
            f"Description: {self.description}",
        ]
        
        if self.effects:
            lines.append("Effects:")
            for effect in self.effects:
                change = f"{effect.old_value} → {effect.new_value}"
                lines.append(f"  - {effect.target_type}.{effect.field}: {change}")
        
        return "\n".join(lines)


class EventLog(BaseModel):
    """Container for game event history."""
    events: list[Event] = Field(default_factory=list)
    
    def add(self, event: Event) -> None:
        """Add an event to the log."""
        self.events.append(event)
    
    def get_recent(self, count: int = 10) -> list[Event]:
        """Get most recent events."""
        return self.events[-count:] if self.events else []
    
    def get_by_tick(self, tick: int) -> list[Event]:
        """Get all events from a specific tick."""
        return [e for e in self.events if e.game_tick == tick]
    
    def get_by_type(self, event_type: EventType) -> list[Event]:
        """Get all events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_by_actor(self, actor: str) -> list[Event]:
        """Get all events by a specific actor."""
        return [e for e in self.events if e.actor == actor]
    
    def get_visible(self) -> list[Event]:
        """Get all player-visible events."""
        return [e for e in self.events if e.visible_to_player]
    
    def summary(self, count: int = 10) -> str:
        """Generate summary of recent events."""
        recent = self.get_recent(count)
        if not recent:
            return "No events recorded."
        return "\n".join(e.summary() for e in recent)
