"""Main Textual app - split screen TUI for the delegative strategy game."""

from __future__ import annotations
import asyncio
from typing import Optional, TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Container
from textual.widgets import Input, Header, Footer, Static
from textual.binding import Binding

from src.tui.panels import OrderPanel, NarrativeLog, StatusBar
from src.models.orders import Order, OrderTracker

if TYPE_CHECKING:
    from src.models.world_state import WorldState
    from src.models.advisors import AdvisorCouncil
    from src.advisors.base import DynamicAdvisor
    from src.narrator import AutonomousNarrator


class DelegativeApp(App):
    """The main TUI application - unified flow through narrator."""
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #main-container {
        height: 1fr;
    }
    
    #narrative-container {
        width: 2fr;
        border: solid $primary;
        border-title-color: $text;
    }
    
    #orders-container {
        width: 1fr;
        border: solid $secondary;
        border-title-color: $text;
    }
    
    #input-area {
        height: 3;
        dock: bottom;
        padding: 0 1;
    }
    
    #command-input {
        width: 100%;
    }
    
    NarrativeLog {
        scrollbar-size: 1 1;
    }
    
    OrderPanel {
        padding: 1;
    }
    
    StatusBar {
        dock: bottom;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("escape", "focus_input", "Focus Input", show=False),
    ]
    
    TITLE = "Delegative Strategy"
    
    def __init__(
        self,
        world_state: "WorldState" = None,
        advisor_council: "AdvisorCouncil" = None,
        advisors: dict[str, "DynamicAdvisor"] = None,
        narrator: "AutonomousNarrator" = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.world_state = world_state
        self.advisor_council = advisor_council
        self.advisors = advisors or {}
        self.narrator = narrator
        
        # Order tracking - use narrator's tracker if available
        self.order_tracker = narrator.order_tracker if narrator else OrderTracker()
        
        # Processing state
        self._processing = False
    
    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()
        
        # Main content area - narrative and orders side by side
        with Horizontal(id="main-container"):
            with Container(id="narrative-container"):
                yield NarrativeLog(id="narrative")
            
            with Container(id="orders-container"):
                yield Static("[bold]ORDERS[/bold]", id="orders-title")
                yield OrderPanel(self.order_tracker, id="orders")
        
        # Input at the bottom
        with Container(id="input-area"):
            yield Input(placeholder="Enter command...", id="command-input")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app starts."""
        # Set border titles
        self.query_one("#narrative-container").border_title = self.world_state.scenario_title if self.world_state else "Narrative"
        self.query_one("#orders-container").border_title = "Orders"
        
        # Focus input
        self.query_one("#command-input").focus()
        
        # Show initial narrative
        narrative = self.query_one("#narrative", NarrativeLog)
        
        if self.world_state:
            # Show scenario description
            if self.world_state.scenario_description:
                narrative.add_narrator(self.world_state.scenario_description)
            
            # Show starting tensions
            if self.world_state.starting_tensions:
                tensions = "\n".join(f"• {t}" for t in self.world_state.starting_tensions)
                narrative.add_system(f"\n[bold yellow]Starting Tensions:[/bold yellow]\n{tensions}\n")
            
            # Show advisors
            if self.advisors:
                advisor_list = []
                for key, adv in self.advisors.items():
                    advisor_list.append(f"• [bold]{adv.name}[/bold], {adv.title}")
                narrative.add_system(f"\n[bold cyan]Your Council:[/bold cyan]\n" + "\n".join(advisor_list) + "\n")
                narrative.add_system("[dim]Just type naturally. Summon advisors by name, give orders, ask questions.[/dim]")
        else:
            narrative.add_system("No world loaded. Use 'new' to create a scenario.")
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input."""
        if self._processing:
            return
        
        command = event.value.strip()
        if not command:
            return
        
        # Clear input
        event.input.value = ""
        
        # Show player input
        narrative = self.query_one("#narrative", NarrativeLog)
        narrative.add_player(command)
        
        # Process command
        await self._process_command(command)
    
    async def _process_command(self, command: str) -> None:
        """Process a command through the unified flow."""
        self._processing = True
        narrative = self.query_one("#narrative", NarrativeLog)
        orders_panel = self.query_one("#orders", OrderPanel)
        
        cmd = command.lower().strip()
        
        try:
            # System commands
            if cmd in ("quit", "exit"):
                self.exit()
                return
            
            if cmd == "help":
                self._show_help()
                return
            
            if cmd == "status":
                if self.world_state:
                    narrative.add_system(self.world_state.summary())
                return
            
            if cmd.startswith("advance"):
                parts = cmd.split()
                days = int(parts[1]) if len(parts) > 1 else 1
                await self._advance_time(days)
                return
            
            # Everything else goes through narrator
            await self._process_through_narrator(command)
        
        except Exception as e:
            narrative.add_system(f"[red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()
        
        finally:
            self._processing = False
            orders_panel.refresh_display()
    
    async def _process_through_narrator(self, command: str) -> None:
        """Process any command through the narrator's unified flow."""
        narrative = self.query_one("#narrative", NarrativeLog)
        orders_panel = self.query_one("#orders", OrderPanel)
        
        if not self.narrator:
            narrative.add_narrator("I cannot respond without being properly initialized.")
            return
        
        # Show thinking indicator
        narrative.add_system("[dim]...[/dim]")
        
        # Run narrator in thread to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.narrator.process, command)
        
        response = result.get("response", "")
        orders_created = result.get("orders_created", [])
        needs_confirmation = result.get("needs_confirmation", False)
        advisor_response = result.get("advisor_response", False)
        advisor_name = result.get("advisor_name")
        entered_conversation = result.get("entered_conversation", False)
        left_conversation = result.get("left_conversation", False)
        
        # Display response appropriately
        if entered_conversation:
            narrative.add_system(response)
        elif left_conversation:
            narrative.add_system(response)
        elif advisor_response and advisor_name:
            narrative.add_advisor(advisor_name, response)
        else:
            narrative.add_narrator(response)
        
        # Show orders created
        if orders_created:
            for order in orders_created:
                narrative.add_system(f"[dim][Order: \"{order.description}\" - {order.advisor_name} - {order.duration_days}d][/dim]")
            orders_panel.refresh_display()
        
        # Note if confirmation is needed
        if needs_confirmation:
            narrative.add_system("[dim]Awaiting your response...[/dim]")
    
    async def _advance_time(self, days: int) -> None:
        """Advance time and process order progress."""
        narrative = self.query_one("#narrative", NarrativeLog)
        orders_panel = self.query_one("#orders", OrderPanel)
        
        if not self.world_state:
            return
        
        # Advance world time
        self.world_state.current_tick += days
        self.world_state.current_date = f"Day {self.world_state.current_tick + 1}"
        
        narrative.add_system(f"\n[bold]Time advances... {days} day(s) pass.[/bold]\n")
        
        # Advance orders and get completions
        completed_orders = self.order_tracker.advance_all(days)
        
        # Report completions - use narrator to generate outcomes (which applies effects first!)
        for order in completed_orders:
            if not order.outcome and self.narrator:
                # Generate outcome via narrator (applies effects + generates narrative)
                loop = asyncio.get_event_loop()
                narrative.add_system(f"[dim]Completing: {order.description}...[/dim]")
                outcome = await loop.run_in_executor(
                    None, self.narrator.complete_order, order
                )
            elif not order.outcome:
                order.complete(f"The task '{order.description}' has been completed.")
            
            narrative.add_order_complete(order.description, order.outcome)
        
        # Show updated status
        if completed_orders and self.world_state:
            narrative.add_system(f"[dim]{self.world_state.summary()}[/dim]")
        
        orders_panel.refresh_display()
    
    def _show_help(self) -> None:
        """Show help information."""
        narrative = self.query_one("#narrative", NarrativeLog)
        
        help_text = """[bold]How to play:[/bold]
Just type naturally. The narrator understands intent.

[bold cyan]Giving Orders:[/bold cyan]
  "Tell Elena to recruit 100 men"
  "I want the iron situation handled"
  "Deploy troops to the pass"

[bold cyan]Asking Questions:[/bold cyan]
  "Ask Viktor about the food situation"
  "What does Elena think of the major?"
  
[bold cyan]Summoning Advisors:[/bold cyan]
  "Bring Elena here"
  "I want to speak with the marshal"
  (then just chat, say 'leave' when done)

[bold cyan]System Commands:[/bold cyan]
  advance <days> - Advance time (orders progress/complete)
  status - Show world state
  help - This help
  quit - Exit game"""
        
        narrative.add_system(help_text)
    
    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()
    
    def action_save(self) -> None:
        """Save the game."""
        narrative = self.query_one("#narrative", NarrativeLog)
        narrative.add_system("[yellow]Save not implemented in TUI yet[/yellow]")
    
    def action_focus_input(self) -> None:
        """Focus the input field."""
        self.query_one("#command-input").focus()
