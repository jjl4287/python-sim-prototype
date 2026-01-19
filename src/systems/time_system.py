"""Time system - manages game time and time-based effects."""

from __future__ import annotations
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.world_state import WorldState

from src.models.events import Event, EventType, EventEffect


class TimeSystem:
    """Manages game time and triggers time-based effects."""
    
    def __init__(self, world_state: "WorldState"):
        self.world_state = world_state
        self._tick_handlers: list[Callable[[int], list[Event]]] = []
        self._register_default_handlers()
    
    def _register_default_handlers(self) -> None:
        """Register default time-based effect handlers."""
        self._tick_handlers.append(self._handle_resource_consumption)
        self._tick_handlers.append(self._handle_population_effects)
        self._tick_handlers.append(self._handle_infrastructure_decay)
    
    def register_handler(self, handler: Callable[[int], list[Event]]) -> None:
        """Register a custom tick handler."""
        self._tick_handlers.append(handler)
    
    def advance(self, days: int) -> dict[str, Any]:
        """Advance time by the specified number of days."""
        if days < 1:
            return {"success": False, "error": "Days must be at least 1"}
        if days > 30:
            return {"success": False, "error": "Cannot advance more than 30 days at once"}
        
        events: list[Event] = []
        old_tick = self.world_state.current_tick
        
        for _ in range(days):
            self.world_state.current_tick += 1
            
            # Run all tick handlers
            for handler in self._tick_handlers:
                handler_events = handler(self.world_state.current_tick)
                events.extend(handler_events)
        
        # Update display date
        self.world_state.current_date = f"Day {self.world_state.current_tick + 1}"
        
        return {
            "success": True,
            "days_advanced": days,
            "old_tick": old_tick,
            "new_tick": self.world_state.current_tick,
            "current_date": self.world_state.current_date,
            "events_generated": len(events),
            "events": [e.summary() for e in events],
        }
    
    def _handle_resource_consumption(self, tick: int) -> list[Event]:
        """Handle daily resource consumption."""
        events: list[Event] = []
        ws = self.world_state
        
        # Calculate total population
        total_pop = sum(p.count for p in ws.populations)
        
        # Food consumption: 1 unit per 100 population per day
        food_consumed = max(1, total_pop // 100)
        old_food = ws.resources.food
        
        if ws.resources.food >= food_consumed:
            ws.resources.food -= food_consumed
        else:
            # Food shortage!
            ws.resources.food = 0
            shortage = food_consumed - old_food
            
            events.append(Event(
                event_type=EventType.RESOURCE_CHANGE,
                description=f"Food shortage! {shortage} units needed but unavailable.",
                actor="system",
                game_tick=tick,
                game_date=ws.current_date,
                effects=[EventEffect(
                    target_type="resource",
                    field="food",
                    old_value=old_food,
                    new_value=0,
                    description="Food depleted",
                )],
            ))
            
            # Reduce approval due to shortage
            for pop in ws.populations:
                if pop.count > 0:
                    old_approval = pop.approval
                    pop.approval = max(0, pop.approval - 5)
                    if pop.approval != old_approval:
                        events.append(Event(
                            event_type=EventType.POPULATION_CHANGE,
                            description=f"{pop.social_class.value} approval dropped due to food shortage",
                            actor="system",
                            game_tick=tick,
                            game_date=ws.current_date,
                            effects=[EventEffect(
                                target_type="population",
                                target_id=pop.social_class.value,
                                field="approval",
                                old_value=old_approval,
                                new_value=pop.approval,
                            )],
                        ))
        
        return events
    
    def _handle_population_effects(self, tick: int) -> list[Event]:
        """Handle population-based effects."""
        events: list[Event] = []
        ws = self.world_state
        
        # Every 7 days, check approval and potentially trigger events
        if tick % 7 == 0:
            for pop in ws.populations:
                if pop.count > 0 and pop.approval < 25:
                    events.append(Event(
                        event_type=EventType.INCIDENT,
                        description=f"Unrest among the {pop.social_class.value}! Approval critically low.",
                        actor="system",
                        game_tick=tick,
                        game_date=ws.current_date,
                        metadata={"population_class": pop.social_class.value, "approval": pop.approval},
                    ))
        
        return events
    
    def _handle_infrastructure_decay(self, tick: int) -> list[Event]:
        """Handle infrastructure decay over time."""
        events: list[Event] = []
        ws = self.world_state
        
        # Every 30 days, infrastructure decays slightly
        if tick % 30 == 0:
            for infra in ws.infrastructure:
                if infra.condition > 0:
                    old_condition = infra.condition
                    infra.condition = max(0, infra.condition - 5)
                    
                    if infra.condition < 50 and old_condition >= 50:
                        events.append(Event(
                            event_type=EventType.INFRASTRUCTURE_CHANGE,
                            description=f"{infra.name} is deteriorating and needs repairs.",
                            actor="system",
                            game_tick=tick,
                            game_date=ws.current_date,
                            effects=[EventEffect(
                                target_type="infrastructure",
                                target_id=infra.id,
                                field="condition",
                                old_value=old_condition,
                                new_value=infra.condition,
                            )],
                        ))
        
        return events
    
    def get_current_time(self) -> dict[str, Any]:
        """Get current time information."""
        return {
            "tick": self.world_state.current_tick,
            "date": self.world_state.current_date,
        }
