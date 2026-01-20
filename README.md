# Delegative Strategy Game

A text-based strategy simulation where you govern through AI advisors. Give intent, not mechanics—your advisors interpret your will and take action.

## Concept

You are a ruler. You don't manage resources directly—you delegate to advisors who have expertise, personalities, biases, and goals. Describe any scenario and the game bootstraps a living world with unique advisors, factions, and tensions.

**Examples:**
- "A small mountain town in the Swiss Alps during the Franco-Prussian War"
- "A native village on the east coast, 20 miles from a new pilgrim settlement"  
- "A rural tech town where a data center is displacing farmers"

## Quick Start

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up API key
cp .env.example .env
# Edit .env with your OpenRouter API key

# Run the game
python -m src.main
```

## How to Play

Just type naturally. The narrator understands your intent.

### Giving Orders
```
> Tell Mack to suppress the peasant resistance
> I want solar panels installed by next week
> Get that food situation handled
```
Orders are acknowledged briefly, then tracked in the Orders panel. They complete when you advance time.

### Asking Questions
```
> Ask Evie what she thinks about the water crisis
> What's the treasury situation?
```

### Summoning Advisors
```
> Get Sheriff Miller in here right now
> I need to speak with Dr. Thorne
```
Enters conversation mode. Say `leave` when done.

### System Commands
| Command | Description |
|---------|-------------|
| `advance <days>` | Advance time (orders progress/complete) |
| `status` | View current world state |
| `help` | Show available commands |
| `quit` | Exit game |

## Interface

Split-screen TUI with:
- **Left panel**: Narrative log (narrator responses, advisor dialogue, events)
- **Right panel**: Active orders with progress bars
- **Bottom**: Command input

Orders show progress and complete when time advances. Completed orders apply effects to the world state (population changes, resource costs, faction disposition shifts).

## Architecture

```
Player Input
     ↓
LLM Intent Classification
(ORDER / QUESTION / SUMMON / GENERAL)
     ↓
┌─────────────────────────────────────┐
│  ORDER → Generate order details     │
│          (name, duration, effects)  │
│          Brief acknowledgment       │
│          Track in OrderTracker      │
│                                     │
│  QUESTION → Route to advisor        │
│             Return information      │
│                                     │
│  SUMMON → Enter conversation mode   │
│           Atmospheric entrance      │
│                                     │
│  GENERAL → Narrator handles         │
└─────────────────────────────────────┘
     ↓
On `advance`:
  - Tick order progress
  - Apply effects to world state
  - Generate completion narratives
```

**Two-Tier Model Architecture:**
- **Advisor Tier** (cheap, fast): Day-to-day queries, order generation, conversations
- **Orchestrator Tier** (smart, rare): Scenario bootstrap, validation, conflict resolution

## Order System

Orders track actions that take time:

```python
Order:
  description: "Deploy solar panels to municipal grid"
  duration_days: 3
  effects: [
    {"path": "resources.treasury", "delta": -110},
    {"path": "resources.labor", "delta": -120}
  ]
```

When an order completes:
1. Effects are applied to world state (resources change, populations shift)
2. Narrator generates outcome narrative reflecting the new state

## Configuration

Set in `.env`:
```
OPENROUTER_API_KEY=your_key_here
ADVISOR_MODEL=moonshotai/kimi-k2-instruct
ORCHESTRATOR_MODEL=google/gemini-2.5-flash-preview-05-20
```

## Requirements

- Python 3.10+
- OpenRouter API key
- Dependencies: `pydantic`, `httpx`, `textual`, `rich`, `pyyaml`, `python-dotenv`, `thefuzz`

## License

MIT
