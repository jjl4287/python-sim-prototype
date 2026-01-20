"""TUI panel components - Order tracker and Narrative display."""

from __future__ import annotations
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, RichLog
from textual.containers import ScrollableContainer
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from src.models.orders import Order, OrderTracker


class OrderPanel(Static):
    """Right panel showing active orders with progress bars."""
    
    DEFAULT_CSS = """
    OrderPanel {
        width: 100%;
        height: 100%;
        padding: 0 1;
    }
    """
    
    def __init__(self, tracker: "OrderTracker" = None, **kwargs):
        super().__init__(**kwargs)
        self.tracker = tracker
    
    def set_tracker(self, tracker: "OrderTracker") -> None:
        """Set or update the order tracker."""
        self.tracker = tracker
        self.refresh_display()
    
    def refresh_display(self) -> None:
        """Refresh the orders display."""
        if not self.tracker:
            self.update("[dim]No orders[/dim]")
            return
        
        lines = []
        
        # Show active orders
        if self.tracker.active:
            for order in self.tracker.active:
                # Progress bar
                bar = order.progress_bar(10)
                pct = order.progress_percent
                days = order.days_remaining
                
                # Status indicator
                if pct >= 80:
                    status_color = "green"
                elif pct >= 40:
                    status_color = "yellow"
                else:
                    status_color = "blue"
                
                lines.append(f"[{status_color}]{bar}[/{status_color}] {pct}%")
                lines.append(f"[bold]{order.description[:25]}...[/bold]" if len(order.description) > 25 else f"[bold]{order.description}[/bold]")
                
                advisor_name = order.advisor_name or order.assigned_to
                lines.append(f"[dim]{advisor_name} • {days}d left[/dim]")
                lines.append("")
        
        # Show recently completed (last 3)
        completed = [o for o in self.tracker.completed if o.outcome][-3:]
        if completed:
            lines.append("[bold green]─ COMPLETED ─[/bold green]")
            for order in reversed(completed):
                lines.append(f"[green]✓[/green] {order.description[:25]}...")
                if order.outcome:
                    outcome_short = order.outcome[:30] + "..." if len(order.outcome) > 30 else order.outcome
                    lines.append(f"  [dim]{outcome_short}[/dim]")
                lines.append("")
        
        if not lines:
            lines.append("[dim]No active orders[/dim]")
            lines.append("")
            lines.append("[dim]Orders appear here[/dim]")
            lines.append("[dim]when advisors act[/dim]")
        
        self.update("\n".join(lines))


class NarrativeLog(RichLog):
    """Left panel showing narrative and conversation history."""
    
    DEFAULT_CSS = """
    NarrativeLog {
        width: 100%;
        height: 100%;
        border: none;
        scrollbar-gutter: stable;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(highlight=True, markup=True, wrap=True, **kwargs)
    
    def add_narrator(self, text: str) -> None:
        """Add narrator text."""
        self.write(Panel(text, title="Narrator", border_style="dim", padding=(0, 1)))
    
    def add_advisor(self, name: str, text: str, actions: list[str] = None) -> None:
        """Add advisor response."""
        content = text
        if actions:
            content += "\n\n[dim]Actions:[/dim]"
            for action in actions:
                content += f"\n  • {action}"
        self.write(Panel(content, title=name, border_style="cyan", padding=(0, 1)))
    
    def add_player(self, text: str) -> None:
        """Add player input for display."""
        self.write(f"[bold green]>[/bold green] {text}\n")
    
    def add_system(self, text: str) -> None:
        """Add system message."""
        self.write(f"[dim]{text}[/dim]\n")
    
    def add_event(self, text: str) -> None:
        """Add event notification."""
        self.write(f"[yellow]⚡[/yellow] {text}\n")
    
    def add_order_complete(self, description: str, outcome: str) -> None:
        """Add order completion notification."""
        self.write(Panel(
            f"[bold]{description}[/bold]\n\n{outcome}",
            title="Order Complete",
            border_style="green",
            padding=(0, 1),
        ))


class StatusBar(Static):
    """Bottom status bar showing time and resources."""
    
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: $surface;
        padding: 0 1;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__("Day 1", **kwargs)
        self._date = "Day 1"
        self._resources = {}
    
    def update_state(self, date: str, resources: dict) -> None:
        """Update the status bar with current state."""
        self._date = date
        self._resources = resources
        self._refresh_content()
    
    def _refresh_content(self) -> None:
        """Refresh the status bar content."""
        parts = [f"[bold]{self._date}[/bold]"]
        
        # Show key resources
        if self._resources:
            res_parts = []
            for key in ["treasury", "food", "labor"]:
                if key in self._resources:
                    val = self._resources[key]
                    color = "green" if val > 50 else "yellow" if val > 20 else "red"
                    icon = {"treasury": "💰", "food": "🍞", "labor": "⚒️"}.get(key, "")
                    res_parts.append(f"{icon}[{color}]{val}[/{color}]")
            if res_parts:
                parts.append(" │ ".join(res_parts))
        
        self.update(" │ ".join(parts))
