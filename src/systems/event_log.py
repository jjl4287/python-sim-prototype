"""Event log system - maintains chronological record of all events."""

from __future__ import annotations
from typing import Optional

from src.models.events import Event, EventType, EventLog as EventLogModel


class EventLog:
    """System for managing the game's event log."""
    
    def __init__(self) -> None:
        self._log = EventLogModel()
    
    def add(self, event: Event) -> None:
        """Add an event to the log."""
        self._log.add(event)
    
    def get_recent(self, count: int = 10) -> list[Event]:
        """Get most recent events."""
        return self._log.get_recent(count)
    
    def get_all(self) -> list[Event]:
        """Get all events."""
        return self._log.events
    
    def get_by_tick(self, tick: int) -> list[Event]:
        """Get events from a specific game tick."""
        return self._log.get_by_tick(tick)
    
    def get_by_type(self, event_type: EventType) -> list[Event]:
        """Get events of a specific type."""
        return self._log.get_by_type(event_type)
    
    def get_by_actor(self, actor: str) -> list[Event]:
        """Get events by a specific actor."""
        return self._log.get_by_actor(actor)
    
    def get_visible(self) -> list[Event]:
        """Get all player-visible events."""
        return self._log.get_visible()
    
    def get_since_tick(self, tick: int) -> list[Event]:
        """Get all events since a specific tick."""
        return [e for e in self._log.events if e.game_tick >= tick]
    
    def search(self, query: str) -> list[Event]:
        """Search events by description."""
        query_lower = query.lower()
        return [e for e in self._log.events if query_lower in e.description.lower()]
    
    def count(self) -> int:
        """Total number of events."""
        return len(self._log.events)
    
    def summary(self, count: int = 10) -> str:
        """Generate summary of recent events."""
        return self._log.summary(count)
    
    def detailed_summary(self, count: int = 5) -> str:
        """Generate detailed summary of recent events."""
        recent = self.get_recent(count)
        if not recent:
            return "No events recorded."
        
        lines = ["=== Recent Events ==="]
        for event in recent:
            lines.append("")
            lines.append(event.detailed())
        
        return "\n".join(lines)
    
    def export(self) -> list[dict]:
        """Export all events for serialization."""
        return [e.model_dump() for e in self._log.events]
    
    def import_events(self, events_data: list[dict]) -> None:
        """Import events from serialized data."""
        self._log.events.clear()
        for data in events_data:
            # Handle datetime serialization
            event = Event(**data)
            self._log.events.append(event)
    
    def clear(self) -> None:
        """Clear all events (use with caution)."""
        self._log.events.clear()
    
    def generate_report(
        self,
        start_tick: Optional[int] = None,
        end_tick: Optional[int] = None,
        actor_filter: Optional[str] = None,
    ) -> str:
        """Generate a filtered report of events."""
        events = self._log.events
        
        if start_tick is not None:
            events = [e for e in events if e.game_tick >= start_tick]
        
        if end_tick is not None:
            events = [e for e in events if e.game_tick <= end_tick]
        
        if actor_filter:
            events = [e for e in events if e.actor == actor_filter]
        
        if not events:
            return "No events match the filter criteria."
        
        lines = [
            f"=== Event Report ===",
            f"Events: {len(events)}",
            f"Period: Tick {events[0].game_tick} to {events[-1].game_tick}",
            "",
        ]
        
        # Group by tick
        current_tick = -1
        for event in events:
            if event.game_tick != current_tick:
                current_tick = event.game_tick
                lines.append(f"--- {event.game_date} (Tick {current_tick}) ---")
            lines.append(f"  [{event.actor}] {event.description}")
        
        return "\n".join(lines)
