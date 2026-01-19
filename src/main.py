"""Main entry point - PTUI REPL interface for the game."""

from __future__ import annotations
import sys
import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from thefuzz import fuzz

from src.models.world_state import WorldState
from src.models.events import Event, EventType
from src.models.advisors import AdvisorCouncil, AdvisorProfile
from src.tools.registry import ToolRegistry
from src.tools.handlers import ToolHandlers
from src.systems.claim_system import ClaimSystem
from src.systems.time_system import TimeSystem
from src.systems.event_log import EventLog
from src.llm.openrouter import OpenRouterClient, ModelTier
from src.advisors.base import DynamicAdvisor
from src.scenarios.bootstrap import ScenarioBootstrap


console = Console()

# Ensure history directory exists
HISTORY_DIR = Path.home() / ".delegative_game"
HISTORY_DIR.mkdir(exist_ok=True)


class Game:
    """Main game controller."""
    
    def __init__(self):
        self.world_state: Optional[WorldState] = None
        self.advisor_council: Optional[AdvisorCouncil] = None
        self.llm: Optional[OpenRouterClient] = None
        self.tools: Optional[ToolRegistry] = None
        self.handlers: Optional[ToolHandlers] = None
        self.claim_system: Optional[ClaimSystem] = None
        self.time_system: Optional[TimeSystem] = None
        self.event_log: Optional[EventLog] = None
        self.advisors: dict[str, DynamicAdvisor] = {}
        self._save_dir = Path("saves")
        self._save_dir.mkdir(exist_ok=True)
    
    def initialize(self, world_state: WorldState, advisor_council: AdvisorCouncil) -> None:
        """Initialize game systems with a world state and advisor council."""
        self.world_state = world_state
        self.advisor_council = advisor_council
        
        # Initialize LLM client
        try:
            self.llm = OpenRouterClient()
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            console.print("[yellow]Set OPENROUTER_API_KEY in your .env file[/yellow]")
            sys.exit(1)
        
        # Initialize systems
        self.tools = ToolRegistry()
        self.claim_system = ClaimSystem(world_state)
        self.time_system = TimeSystem(world_state)
        self.event_log = EventLog()
        
        self.handlers = ToolHandlers(
            world_state=world_state,
            claim_system=self.claim_system,
            time_system=self.time_system,
            event_log=self.event_log,
        )
        
        # Initialize advisors from dynamic profiles
        self.advisors = {
            "steward": DynamicAdvisor(
                profile=advisor_council.steward,
                llm_client=self.llm,
                tool_registry=self.tools,
                tool_handlers=self.handlers,
                world_state=world_state,
            ),
            "marshal": DynamicAdvisor(
                profile=advisor_council.marshal,
                llm_client=self.llm,
                tool_registry=self.tools,
                tool_handlers=self.handlers,
                world_state=world_state,
            ),
            "chancellor": DynamicAdvisor(
                profile=advisor_council.chancellor,
                llm_client=self.llm,
                tool_registry=self.tools,
                tool_handlers=self.handlers,
                world_state=world_state,
            ),
        }
        
        # Log game start
        self.event_log.add(Event(
            event_type=EventType.GAME_START,
            description=f"Game started: {world_state.scenario_title}",
            actor="system",
            game_tick=0,
            game_date=world_state.current_date,
        ))
    
    def save(self, filename: str = "quicksave") -> bool:
        """Save the current game state."""
        if not self.world_state or not self.advisor_council:
            console.print("[red]No game to save[/red]")
            return False
        
        save_data = {
            "version": 2,
            "world_state": self.world_state.model_dump(mode="json"),
            "advisor_council": self.advisor_council.model_dump(mode="json"),
            "claims": self.claim_system.export_claims() if self.claim_system else [],
            "events": self.event_log.export() if self.event_log else [],
            "pending_actions": [a.model_dump(mode="json") for a in self.handlers.get_pending_actions()] if self.handlers else [],
        }
        
        filepath = self._save_dir / f"{filename}.json"
        with open(filepath, 'w') as f:
            json.dump(save_data, f, indent=2, default=str)
        
        console.print(f"[green]Game saved to {filepath}[/green]")
        return True
    
    def load(self, filename: str = "quicksave") -> bool:
        """Load a saved game."""
        filepath = self._save_dir / f"{filename}.json"
        
        if not filepath.exists():
            console.print(f"[red]Save file not found: {filepath}[/red]")
            return False
        
        with open(filepath, 'r') as f:
            save_data = json.load(f)
        
        world_state = WorldState(**save_data["world_state"])
        
        if "advisor_council" in save_data:
            advisor_council = AdvisorCouncil(**save_data["advisor_council"])
        else:
            from src.models.advisors import AdvisorRole
            advisor_council = AdvisorCouncil(
                steward=AdvisorProfile(role=AdvisorRole.STEWARD, name="Steward", title="Keeper of Stores", background="A trusted advisor.", description="", speech_style="Formal"),
                marshal=AdvisorProfile(role=AdvisorRole.MARSHAL, name="Marshal", title="War Leader", background="A trusted advisor.", description="", speech_style="Direct"),
                chancellor=AdvisorProfile(role=AdvisorRole.CHANCELLOR, name="Chancellor", title="Council Keeper", background="A trusted advisor.", description="", speech_style="Measured"),
            )
        
        self.initialize(world_state, advisor_council)
        
        if self.claim_system and "claims" in save_data:
            self.claim_system.import_claims(save_data["claims"])
        
        if self.event_log and "events" in save_data:
            self.event_log.import_events(save_data["events"])
        
        console.print(f"[green]Game loaded from {filepath}[/green]")
        return True
    
    def list_saves(self) -> list[str]:
        """List available save files."""
        return [f.stem for f in self._save_dir.glob("*.json")]
    
    def fuzzy_match_location(self, query: str, threshold: int = 70) -> Optional[str]:
        """Find a location that fuzzy-matches the query."""
        if not self.world_state:
            return None
        
        best_match = None
        best_score = 0
        
        # Check terrain
        for t in self.world_state.terrain:
            score = fuzz.ratio(query.lower(), t.name.lower())
            if score > best_score and score >= threshold:
                best_score = score
                best_match = t.name
        
        # Check settlements
        for s in self.world_state.settlements:
            score = fuzz.ratio(query.lower(), s.name.lower())
            if score > best_score and score >= threshold:
                best_score = score
                best_match = s.name
        
        return best_match
    
    def get_narrator_response(self, query: str) -> str:
        """Get a response from the neutral narrator."""
        if not self.llm or not self.world_state:
            return "No game is currently active."
        
        ctx = self.world_state.advisor_context
        
        system_prompt = f"""You are a neutral narrator for a strategy simulation game. You have no personality, biases, or agenda.

Your role:
- Describe the current situation objectively
- Summarize what advisors have said
- Help the player understand the world state
- Route complex questions to the appropriate advisor

Current World State:
{self.world_state.summary()}

Historical Period: {ctx.historical_period}
Technology Level: {ctx.technology_level}

When the player asks about:
- Economy, resources, trade → suggest talking to the steward
- Military, security, defense → suggest talking to the marshal  
- Law, factions, diplomacy → suggest talking to the chancellor

Be concise and helpful. Don't roleplay or have opinions."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        
        response = self.llm.chat(
            messages=messages,
            tier=ModelTier.ADVISOR,
            temperature=0.3,
            max_tokens=500,
        )
        
        return response.content or "I could not formulate a response."


def print_help(in_conversation: bool = False):
    """Print help information."""
    table = Table(title="Commands", show_header=True, header_style="bold magenta")
    table.add_column("Command", style="cyan")
    table.add_column("Description")
    
    if in_conversation:
        commands = [
            ("<message>", "Send a message to the advisor"),
            ("leave / back / exit", "End conversation and return to main prompt"),
            ("status", "Show current world state"),
            ("claims", "List pending claims"),
            ("help", "Show this help"),
        ]
    else:
        commands = [
            ("talk <advisor>", "Start a conversation with an advisor (by name or role)"),
            ("<question>", "Ask the narrator a general question"),
            ("advisors [name]", "Show your advisors (or details on one)"),
            ("terrain", "Show all known terrain and locations"),
            ("claims", "List pending claims (interactive)"),
            ("actions", "List pending actions (interactive)"),
            ("advance <days>", "Advance time by days (1-30)"),
            ("status", "Show current world state"),
            ("events [n]", "Show recent events (default: 10)"),
            ("save [name]", "Save game (default: quicksave)"),
            ("load [name]", "Load game (default: quicksave)"),
            ("saves", "List available saves"),
            ("help", "Show this help"),
            ("quit", "Exit the game"),
        ]
    
    for cmd, desc in commands:
        table.add_row(cmd, desc)
    
    console.print(table)


def resolve_advisor(game: Game, name_or_role: str) -> tuple[str, DynamicAdvisor] | None:
    """Resolve an advisor by role OR by name."""
    name_lower = name_or_role.lower()
    
    if name_lower in game.advisors:
        return name_lower, game.advisors[name_lower]
    
    for key, advisor in game.advisors.items():
        advisor_name_lower = advisor.name.lower()
        first_name = advisor_name_lower.split()[0] if advisor_name_lower else ""
        
        if name_lower == advisor_name_lower or name_lower == first_name:
            return key, advisor
    
    return None


def handle_advisors(game: Game, parts: list[str] = None) -> None:
    """Show the player's advisors."""
    if not game.advisors or not game.advisor_council:
        console.print("[dim]No advisors available[/dim]")
        return
    
    if parts and len(parts) > 1:
        result = resolve_advisor(game, parts[1])
        if result:
            _, advisor = result
            console.print(Panel(
                advisor.get_full_description(),
                title=f"{advisor.name}",
                border_style="cyan",
            ))
            return
        else:
            console.print(f"[red]Unknown advisor: {parts[1]}[/red]")
            return
    
    console.print("\n[bold]Your Council[/bold]\n")
    
    for key, advisor in game.advisors.items():
        profile = advisor.profile
        console.print(f"[bold cyan]{profile.name}[/bold cyan], {profile.title} [dim]({key})[/dim]")
        if profile.description:
            desc = profile.description[:80] + "..." if len(profile.description) > 80 else profile.description
            console.print(f"  [dim]{desc}[/dim]")
        if profile.personal_goals:
            console.print(f"  [yellow]Goal:[/yellow] {profile.personal_goals[0]}")
        console.print()
    
    console.print("[dim]Use 'talk <name>' to start a conversation[/dim]")


def conversation_loop(game: Game, advisor: DynamicAdvisor, session: PromptSession) -> None:
    """Run a conversation loop with an advisor."""
    console.print(f"\n[bold green]Entering conversation with {advisor.name}, {advisor.title}[/bold green]")
    console.print("[dim]Type 'leave', 'back', or 'exit' to end conversation[/dim]\n")
    
    first_name = advisor.name.split()[0]
    
    while True:
        try:
            user_input = session.prompt(f"[{first_name}] > ")
            
            if not user_input.strip():
                continue
            
            cmd = user_input.strip().lower()
            
            # Exit commands
            if cmd in ("leave", "back", "exit", "quit"):
                console.print(f"\n[dim]Left conversation with {advisor.name}[/dim]\n")
                break
            
            # In-conversation commands
            if cmd == "help":
                print_help(in_conversation=True)
                continue
            
            if cmd == "status":
                console.print(game.world_state.summary())
                continue
            
            if cmd == "claims":
                handle_claims_interactive(game, session)
                continue
            
            # Process as message to advisor
            console.print()  # spacing
            
            try:
                result = advisor.process_query(user_input)
                
                if result.get("response"):
                    console.print(Panel(
                        result["response"],
                        title=advisor.name,
                        border_style="blue",
                    ))
                
                if result.get("tool_calls"):
                    console.print("[bold]Actions:[/bold]")
                    for tc in result["tool_calls"]:
                        msg = tc['result'].get('message', str(tc['result']))
                        console.print(f"  • {tc['tool']}: {msg}")
                
                console.print()
                
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
        
        except KeyboardInterrupt:
            console.print("\n[dim]Type 'leave' to exit conversation[/dim]")
        except EOFError:
            break


def handle_claims_interactive(game: Game, session: PromptSession) -> None:
    """Interactive claims menu."""
    if not game.claim_system:
        return
    
    pending = game.claim_system.get_pending_claims()
    
    if not pending:
        console.print("[dim]No pending claims[/dim]")
        return
    
    console.print("\n[bold]Pending Claims:[/bold]\n")
    
    for i, claim in enumerate(pending, 1):
        console.print(f"  [{i}] {claim.description[:60]}...")
        console.print(f"      [dim]Proposed by: {claim.proposed_by}[/dim]")
    
    console.print("\n[dim]Enter number to approve, 'd<number>' to deny, or press Enter to cancel[/dim]")
    
    try:
        choice = session.prompt("Choice: ")
        
        if not choice.strip():
            return
        
        deny = choice.strip().lower().startswith('d')
        if deny:
            choice = choice.strip()[1:]
        
        try:
            idx = int(choice.strip()) - 1
            if 0 <= idx < len(pending):
                claim = pending[idx]
                
                if deny:
                    result = game.handlers.resolve_claim(
                        claim_id=claim.id,
                        verdict="denied",
                        reasoning="Denied by ruler",
                        resolved_by="player",
                    )
                    console.print(f"[yellow]Claim denied[/yellow]")
                else:
                    result = game.handlers.resolve_claim(
                        claim_id=claim.id,
                        verdict="confirmed",
                        reasoning="Approved by ruler",
                        resolved_by="player",
                    )
                    console.print(f"[green]Claim approved[/green]")
            else:
                console.print("[red]Invalid selection[/red]")
        except ValueError:
            console.print("[red]Invalid input[/red]")
    
    except (KeyboardInterrupt, EOFError):
        pass


def handle_actions_interactive(game: Game, session: PromptSession) -> None:
    """Interactive actions menu."""
    if not game.handlers:
        return
    
    actions = game.handlers.get_pending_actions()
    
    if not actions:
        console.print("[dim]No pending actions[/dim]")
        return
    
    console.print("\n[bold]Pending Actions:[/bold]\n")
    
    for i, action in enumerate(actions, 1):
        console.print(f"  [{i}] {action.description[:60]}...")
        console.print(f"      [dim]Cost: {action.cost_summary()} | By: {action.proposed_by}[/dim]")
        if action.risks:
            console.print(f"      [red]Risks: {', '.join(action.risks[:2])}[/red]")
    
    console.print("\n[dim]Enter number to approve, 'd<number>' to deny, or press Enter to cancel[/dim]")
    
    try:
        choice = session.prompt("Choice: ")
        
        if not choice.strip():
            return
        
        deny = choice.strip().lower().startswith('d')
        if deny:
            choice = choice.strip()[1:]
        
        try:
            idx = int(choice.strip()) - 1
            if 0 <= idx < len(actions):
                action = actions[idx]
                
                if deny:
                    result = game.handlers.reject_action(action.id, "player")
                    console.print(f"[yellow]Action rejected[/yellow]")
                else:
                    result = game.handlers.approve_action(action.id, "player")
                    if result.get("success"):
                        console.print(f"[green]Action approved and executed[/green]")
                    else:
                        console.print(f"[red]{result.get('error', 'Action failed')}[/red]")
            else:
                console.print("[red]Invalid selection[/red]")
        except ValueError:
            console.print("[red]Invalid input[/red]")
    
    except (KeyboardInterrupt, EOFError):
        pass


def handle_terrain(game: Game) -> None:
    """Show all terrain and locations."""
    if not game.world_state:
        return
    
    ws = game.world_state
    
    if not ws.terrain:
        console.print("[dim]No terrain recorded in world state[/dim]")
        return
    
    console.print("\n[bold]Known Terrain & Locations[/bold]\n")
    for t in ws.terrain:
        controlled = "[green]✓[/green]" if t.controlled else "[red]✗[/red]"
        console.print(f"{controlled} [bold]{t.name}[/bold] ({t.type.value})")
        if t.description:
            console.print(f"    {t.description}")
        if t.resources_available:
            console.print(f"    [cyan]Resources:[/cyan] {', '.join(t.resources_available)}")
        if t.hazards:
            console.print(f"    [red]Hazards:[/red] {', '.join(t.hazards)}")


def handle_events(game: Game, parts: list[str]) -> None:
    """Show recent events."""
    count = 10
    if len(parts) > 1:
        try:
            count = int(parts[1])
        except ValueError:
            pass
    
    if game.event_log:
        console.print(game.event_log.summary(count))


def handle_advance(game: Game, parts: list[str]) -> None:
    """Advance time."""
    days = 1
    if len(parts) > 1:
        try:
            days = int(parts[1])
        except ValueError:
            console.print("[red]Days must be a number[/red]")
            return
    
    result = game.handlers.advance_time(days)
    
    if result.get("success"):
        console.print(f"[green]Advanced to {result['current_date']}[/green]")
        
        if result.get("events"):
            console.print("\n[bold]Events:[/bold]")
            for event_summary in result["events"]:
                console.print(f"  • {event_summary}")
    else:
        console.print(f"[red]{result.get('error', 'Failed to advance time')}[/red]")


def new_game(game: Game, session: PromptSession) -> bool:
    """Start a new game with scenario bootstrap."""
    console.print(Panel(
        "[bold]Welcome to the Delegative Strategy Game[/bold]\n\n"
        "You are a ruler. Describe your realm and situation, and the world will be created.\n\n"
        "Examples:\n"
        "• 'A rural English manor in the late 1000s, unstable borders with Wales'\n"
        "• 'A post-coup Sub-Saharan African nation in the 1970s'\n"
        "• 'A trading post on the Silk Road during the Mongol conquests'",
        title="New Game",
    ))
    
    try:
        scenario_prompt = session.prompt("\nDescribe your scenario: ")
    except (KeyboardInterrupt, EOFError):
        return False
    
    if not scenario_prompt.strip():
        console.print("[red]No scenario provided[/red]")
        return False
    
    console.print("\n[yellow]Generating world and advisors... (this may take a moment)[/yellow]\n")
    
    try:
        llm = OpenRouterClient()
        bootstrap = ScenarioBootstrap(llm)
        world_state, advisor_council = bootstrap.generate(scenario_prompt)
        game.initialize(world_state, advisor_council)
        
        console.print(Panel(
            f"[bold]{world_state.scenario_title}[/bold]\n\n"
            f"{world_state.scenario_description or 'No description'}\n\n"
            f"[dim]Type 'help' for commands, 'talk <advisor>' to begin[/dim]",
            title="World Created",
            border_style="green",
        ))
        
        console.print("\n[bold cyan]Your Council:[/bold cyan]")
        for advisor in advisor_council.all_advisors():
            console.print(f"  • [bold]{advisor.name}[/bold], {advisor.title}")
            if advisor.personal_goals:
                console.print(f"    [dim]{advisor.personal_goals[0]}[/dim]")
        
        tensions = getattr(world_state, 'starting_tensions', None)
        if tensions:
            console.print("\n[bold yellow]Starting Tensions:[/bold yellow]")
            for tension in tensions:
                console.print(f"  • {tension}")
        
        return True
        
    except Exception as e:
        console.print(f"[red]Failed to generate scenario: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    console.print(Panel(
        "[bold magenta]Delegative Strategy Game[/bold magenta]\n"
        "[dim]Govern through AI advisors[/dim]",
        border_style="magenta",
    ))
    
    # Create prompt session with history
    session = PromptSession(
        history=FileHistory(str(HISTORY_DIR / "command_history")),
        auto_suggest=AutoSuggestFromHistory(),
    )
    
    game = Game()
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "load" and len(sys.argv) > 2:
            if not game.load(sys.argv[2]):
                sys.exit(1)
        else:
            console.print("[yellow]Usage: python -m src.main [load <savename>][/yellow]")
            sys.exit(1)
    else:
        if not new_game(game, session):
            sys.exit(1)
    
    console.print("\n[dim]Type 'help' for commands[/dim]\n")
    
    # Main REPL loop
    while True:
        try:
            command = session.prompt("> ")
            
            if not command.strip():
                continue
            
            parts = command.strip().split()
            cmd = parts[0].lower()
            
            # Exit commands
            if cmd in ("quit", "exit"):
                console.print("[dim]Farewell, ruler.[/dim]")
                break
            
            # Help
            elif cmd == "help":
                print_help()
            
            # Talk to advisor (conversation mode)
            elif cmd == "talk":
                if len(parts) < 2:
                    console.print("[red]Usage: talk <advisor>[/red]")
                    names = [f"{a.name.split()[0]} ({k})" for k, a in game.advisors.items()]
                    console.print(f"[yellow]Available: {', '.join(names)}[/yellow]")
                    continue
                
                result = resolve_advisor(game, parts[1])
                if result:
                    _, advisor = result
                    conversation_loop(game, advisor, session)
                else:
                    console.print(f"[red]Unknown advisor: {parts[1]}[/red]")
                    names = [f"{a.name.split()[0]} ({k})" for k, a in game.advisors.items()]
                    console.print(f"[yellow]Available: {', '.join(names)}[/yellow]")
            
            # Advisors list
            elif cmd == "advisors":
                handle_advisors(game, parts)
            
            # Terrain
            elif cmd == "terrain":
                handle_terrain(game)
            
            # Claims (interactive)
            elif cmd == "claims":
                handle_claims_interactive(game, session)
            
            # Actions (interactive)
            elif cmd == "actions":
                handle_actions_interactive(game, session)
            
            # Advance time
            elif cmd == "advance":
                handle_advance(game, parts)
            
            # Status
            elif cmd == "status":
                if game.world_state:
                    console.print(game.world_state.summary())
            
            # Events
            elif cmd == "events":
                handle_events(game, parts)
            
            # Save/Load
            elif cmd == "save":
                name = parts[1] if len(parts) > 1 else "quicksave"
                game.save(name)
            
            elif cmd == "load":
                name = parts[1] if len(parts) > 1 else "quicksave"
                game.load(name)
            
            elif cmd == "saves":
                saves = game.list_saves()
                if saves:
                    console.print("[bold]Available saves:[/bold]")
                    for s in saves:
                        console.print(f"  • {s}")
                else:
                    console.print("[dim]No saves found[/dim]")
            
            # Default: Ask narrator
            else:
                # Treat as question to narrator
                console.print("\n[dim]Asking narrator...[/dim]\n")
                response = game.get_narrator_response(command)
                console.print(Panel(response, title="Narrator", border_style="dim"))
                console.print()
        
        except KeyboardInterrupt:
            console.print("\n[dim]Type 'quit' to exit[/dim]")
        
        except EOFError:
            console.print("\n[dim]Farewell, ruler.[/dim]")
            break
        
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
