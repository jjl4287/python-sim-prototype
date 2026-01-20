"""Main entry point - TUI interface for the delegative strategy game."""

from __future__ import annotations
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from src.models.world_state import WorldState
from src.models.orders import OrderTracker
from src.models.advisors import AdvisorCouncil, AdvisorProfile, AdvisorRole
from src.tools.registry import ToolRegistry
from src.tools.handlers import ToolHandlers
from src.systems.time_system import TimeSystem
from src.systems.event_log import EventLog
from src.llm.openrouter import OpenRouterClient
from src.advisors.base import DynamicAdvisor
from src.scenarios.bootstrap import ScenarioBootstrap
from src.narrator import AutonomousNarrator
from src.tui.app import DelegativeApp


console = Console()

# Ensure history directory exists
HISTORY_DIR = Path.home() / ".delegative_game"
HISTORY_DIR.mkdir(exist_ok=True)


def create_game_components(world_state: WorldState, advisor_council: AdvisorCouncil):
    """Create all game components from a world state and advisor council."""
    # Initialize LLM client
    try:
        llm = OpenRouterClient()
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Set OPENROUTER_API_KEY in your .env file[/yellow]")
        sys.exit(1)
    
    # Initialize core systems
    tools = ToolRegistry()
    time_system = TimeSystem(world_state)
    event_log = EventLog()
    
    handlers = ToolHandlers(
        world_state=world_state,
        claim_system=None,  # No longer using claim system
        time_system=time_system,
        event_log=event_log,
    )
    
    # Initialize advisors from dynamic profiles
    advisors = {
        "steward": DynamicAdvisor(
            profile=advisor_council.steward,
            llm_client=llm,
            tool_registry=tools,
            tool_handlers=handlers,
            world_state=world_state,
        ),
        "marshal": DynamicAdvisor(
            profile=advisor_council.marshal,
            llm_client=llm,
            tool_registry=tools,
            tool_handlers=handlers,
            world_state=world_state,
        ),
        "chancellor": DynamicAdvisor(
            profile=advisor_council.chancellor,
            llm_client=llm,
            tool_registry=tools,
            tool_handlers=handlers,
            world_state=world_state,
        ),
    }
    
    # Initialize order tracker
    order_tracker = OrderTracker()
    
    # Initialize autonomous narrator
    narrator = AutonomousNarrator(
        llm=llm,
        world_state=world_state,
        advisor_council=advisor_council,
        advisors=advisors,
        order_tracker=order_tracker,
    )
    
    return {
        "llm": llm,
        "advisors": advisors,
        "narrator": narrator,
        "order_tracker": order_tracker,
    }


def new_game_prompt() -> tuple[WorldState, AdvisorCouncil] | None:
    """Prompt for a new game scenario and bootstrap it."""
    console.print(Panel(
        "[bold]Welcome to the Delegative Strategy Game[/bold]\n\n"
        "You are a ruler. Describe your realm and situation, and the world will be created.\n\n"
        "Examples:\n"
        "• 'A rural English manor in the late 1000s, unstable borders with Wales'\n"
        "• 'A post-coup Sub-Saharan African nation in the 1970s'\n"
        "• 'A trading post on the Silk Road during the Mongol conquests'\n"
        "• 'A Viking jarl's hall in 9th century Norway'",
        title="New Game",
        border_style="magenta",
    ))
    
    session = PromptSession(
        history=FileHistory(str(HISTORY_DIR / "scenario_history")),
    )
    
    try:
        scenario_prompt = session.prompt("\nDescribe your scenario: ")
    except (KeyboardInterrupt, EOFError):
        return None
    
    if not scenario_prompt.strip():
        console.print("[red]No scenario provided[/red]")
        return None
    
    console.print("\n[yellow]Generating world and advisors... (this may take a moment)[/yellow]\n")
    
    try:
        llm = OpenRouterClient()
        bootstrap = ScenarioBootstrap(llm)
        world_state, advisor_council = bootstrap.generate(scenario_prompt)
        return world_state, advisor_council
    except Exception as e:
        console.print(f"[red]Failed to generate scenario: {e}[/red]")
        import traceback
        traceback.print_exc()
        return None


def run_tui(world_state: WorldState, advisor_council: AdvisorCouncil):
    """Run the TUI with the given world state."""
    components = create_game_components(world_state, advisor_council)
    
    app = DelegativeApp(
        world_state=world_state,
        advisor_council=advisor_council,
        advisors=components["advisors"],
        narrator=components["narrator"],
    )
    
    app.run()


def main():
    """Main entry point."""
    console.print(Panel(
        "[bold magenta]Delegative Strategy Game[/bold magenta]\n"
        "[dim]Govern through AI advisors[/dim]",
        border_style="magenta",
    ))
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "load" and len(sys.argv) > 2:
            # TODO: Implement save/load
            console.print("[yellow]Save/load not yet implemented for TUI mode[/yellow]")
            sys.exit(1)
        else:
            console.print("[yellow]Usage: python -m src.main[/yellow]")
            sys.exit(1)
    
    # Start new game
    result = new_game_prompt()
    if not result:
        sys.exit(1)
    
    world_state, advisor_council = result
    
    # Show the created world briefly before launching TUI
    console.print(Panel(
        f"[bold]{world_state.scenario_title}[/bold]\n\n"
        f"{world_state.scenario_description or 'No description'}\n\n"
        f"[dim]Launching game interface...[/dim]",
        title="World Created",
        border_style="green",
    ))
    
    # Brief pause to let user see the world
    import time
    time.sleep(1)
    
    # Run the TUI
    run_tui(world_state, advisor_council)


if __name__ == "__main__":
    main()
