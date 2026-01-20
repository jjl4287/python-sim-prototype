"""Order model - tracks actions that take time to complete."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid


class OrderStatus(str, Enum):
    """Status of an order."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrderEffect(BaseModel):
    """A state change that occurs when an order completes."""
    path: str = Field(description="Dot-path to the state field (e.g., 'settlements.Camp Malina.population')")
    delta: Optional[int] = Field(default=None, description="Change amount (for numeric fields)")
    set_value: Optional[Any] = Field(default=None, description="Value to set (for non-numeric fields)")
    
    model_config = {"extra": "allow"}


class Order(BaseModel):
    """An order given to an advisor that takes time to complete."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # What
    description: str = Field(description="Short description of the order (AI-generated)")
    details: Optional[str] = Field(default=None, description="Full details of the plan")
    original_request: Optional[str] = Field(default=None, description="What the player originally asked for")
    
    # Who
    assigned_to: str = Field(description="Advisor role handling this order")
    advisor_name: Optional[str] = Field(default=None, description="Advisor's actual name")
    
    # When
    duration_days: int = Field(ge=1, description="How many days this takes")
    progress_days: int = Field(default=0, ge=0, description="Days of progress so far")
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Status
    status: OrderStatus = Field(default=OrderStatus.IN_PROGRESS)
    
    # Effects to apply on completion
    effects: list[OrderEffect] = Field(default_factory=list, description="State changes to apply when order completes")
    
    # Outcome (set when completed/failed)
    outcome: Optional[str] = Field(default=None, description="What happened when the order finished")
    
    model_config = {"extra": "allow"}
    
    @property
    def progress_percent(self) -> int:
        """Progress as a percentage 0-100."""
        if self.duration_days == 0:
            return 100
        return min(100, int((self.progress_days / self.duration_days) * 100))
    
    @property
    def days_remaining(self) -> int:
        """Days left until completion."""
        return max(0, self.duration_days - self.progress_days)
    
    @property
    def is_complete(self) -> bool:
        """Whether the order has finished (success or failure)."""
        return self.status in (OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.CANCELLED)
    
    def advance(self, days: int = 1) -> bool:
        """Advance progress by days. Returns True if order just completed."""
        if self.is_complete:
            return False
        
        self.progress_days += days
        
        if self.progress_days >= self.duration_days:
            self.progress_days = self.duration_days
            # Mark as complete (outcome will be set by narrator)
            self.status = OrderStatus.COMPLETED
            return True  # Just finished
        
        return False
    
    def complete(self, outcome: str) -> None:
        """Mark order as successfully completed with narrative outcome."""
        self.status = OrderStatus.COMPLETED
        self.outcome = outcome
    
    def fail(self, reason: str) -> None:
        """Mark order as failed."""
        self.status = OrderStatus.FAILED
        self.outcome = reason
    
    def cancel(self, reason: str = "Cancelled by ruler") -> None:
        """Cancel the order."""
        self.status = OrderStatus.CANCELLED
        self.outcome = reason
    
    def progress_bar(self, width: int = 10) -> str:
        """Generate a text progress bar."""
        filled = int((self.progress_percent / 100) * width)
        empty = width - filled
        return "▓" * filled + "░" * empty


class OrderTracker(BaseModel):
    """Tracks all active and completed orders."""
    active: list[Order] = Field(default_factory=list)
    completed: list[Order] = Field(default_factory=list)
    
    def add(self, order: Order) -> None:
        """Add a new order to tracking."""
        self.active.append(order)
    
    def advance_all(self, days: int = 1) -> list[Order]:
        """Advance all active orders. Returns list of newly completed orders."""
        just_completed = []
        still_active = []
        
        for order in self.active:
            if order.advance(days):
                just_completed.append(order)
            
            if order.is_complete:
                self.completed.append(order)
            else:
                still_active.append(order)
        
        self.active = still_active
        return just_completed
    
    def get_by_id(self, order_id: str) -> Optional[Order]:
        """Find an order by ID."""
        for order in self.active + self.completed:
            if order.id == order_id:
                return order
        return None
    
    def get_active_by_advisor(self, role: str) -> list[Order]:
        """Get all active orders for a specific advisor."""
        return [o for o in self.active if o.assigned_to == role]
    
    def cancel_by_id(self, order_id: str, reason: str = "Cancelled") -> bool:
        """Cancel an active order."""
        for order in self.active:
            if order.id == order_id:
                order.cancel(reason)
                self.active.remove(order)
                self.completed.append(order)
                return True
        return False
