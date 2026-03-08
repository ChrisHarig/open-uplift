"""Rich formatting utilities for CLI output."""

import json
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
console = Console()


def status_markers(has_survey: bool, has_compaction: bool, has_judge: bool, judge_stale: bool = False) -> str:
    """Return status markers like [S][C][J] or [ ][ ][ ]. Stale judge shows [J!]."""
    s = "[S]" if has_survey else "[ ]"
    c = "[C]" if has_compaction else "[ ]"
    if has_judge and judge_stale:
        j = "[J!]"
    elif has_judge:
        j = "[J]"
    else:
        j = "[ ]"
    return f"{s}{c}{j}"


def format_session_table(rows: list[dict], title: str = "Sessions") -> Table:
    """Build a rich Table for a list of session rows."""
    table = Table(title=title, show_lines=False, pad_edge=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("ID", style="dim", width=8)
    table.add_column("Date", style="cyan", width=10)
    table.add_column("Project", style="green", max_width=15)
    table.add_column("Model", style="dim", max_width=12)
    table.add_column("Msgs", justify="right", width=4)
    table.add_column("Uplift", justify="right", width=6)
    table.add_column("Status", width=11, no_wrap=True)

    for i, r in enumerate(rows, 1):
        sid = r.get("session_id", "")[:8]
        date_str = r.get("started_at", "")[:10]  # just YYYY-MM-DD
        project = r.get("project_name") or "unknown"
        model = r.get("model_primary") or ""
        # Shorten model names for table display
        model = model.replace("claude-", "").replace("gpt-", "gpt")
        msgs = str(r.get("message_count", 0))
        uplift = r.get("uplift_factor")
        uplift_str = f"[green]{uplift:.1f}x[/green]" if uplift else "[dim]—[/dim]"
        markers = status_markers(
            bool(r.get("has_survey")),
            bool(r.get("has_compaction")),
            bool(r.get("has_judge")),
            bool(r.get("judge_stale")),
        )
        table.add_row(str(i), sid, date_str, project, model, msgs, uplift_str, markers)

    return table


def format_session_detail(session: dict, time_data: dict | None = None) -> Panel:
    """Build a rich Panel for session metadata + summary."""
    lines = []
    lines.append(f"[bold]Session:[/bold] {session.get('session_id', 'N/A')}")
    lines.append(f"[bold]Project:[/bold] {session.get('project_name') or 'unknown'}")
    lines.append(f"[bold]Path:[/bold] {session.get('project_path') or 'N/A'}")
    lines.append(f"[bold]Branch:[/bold] {session.get('git_branch') or 'N/A'}")

    started = session.get("started_at", "")
    ended = session.get("ended_at", "")
    lines.append(f"[bold]Started:[/bold] {started}")
    lines.append(f"[bold]Ended:[/bold] {ended or 'N/A'}")

    # Duration
    if started and ended:
        try:
            s = datetime.fromisoformat(started.replace("Z", "+00:00"))
            e = datetime.fromisoformat(ended.replace("Z", "+00:00"))
            dur = (e - s).total_seconds()
            mins = int(dur // 60)
            secs = int(dur % 60)
            lines.append(f"[bold]Duration:[/bold] {mins}m {secs}s")
        except (ValueError, TypeError):
            pass

    lines.append("")
    lines.append(f"[bold]Messages:[/bold] {session.get('message_count', 0)}")
    lines.append(f"[bold]Tool calls:[/bold] {session.get('tool_call_count', 0)}")
    lines.append(f"[bold]Model:[/bold] {session.get('model_primary') or 'N/A'}")
    lines.append(f"[bold]Cost:[/bold] ${session.get('total_cost_usd', 0):.4f}")

    if time_data and time_data.get("active_minutes"):
        lines.append(f"[bold]Active time:[/bold] {time_data['active_minutes']}m ({time_data['active_windows']} active windows)")

    markers = status_markers(
        bool(session.get("has_survey")),
        bool(session.get("has_compaction")),
        bool(session.get("has_judge")),
        bool(session.get("judge_stale")),
    )
    lines.append(f"[bold]Status:[/bold] {markers}  (S=Survey C=Compaction J=Judge J!=Stale)")

    return Panel("\n".join(lines), title="Session Detail", border_style="blue")


def format_telemetry(session: dict, messages: list[dict] | None = None) -> Panel:
    """Build a token/cost breakdown Panel."""
    lines = []
    lines.append(f"[bold]Total input tokens:[/bold]  {session.get('total_input_tokens', 0):,}")
    lines.append(f"[bold]Total output tokens:[/bold] {session.get('total_output_tokens', 0):,}")
    lines.append(f"[bold]Cache read tokens:[/bold]   {session.get('total_cache_read_tokens', 0):,}")
    lines.append(f"[bold]Cache create tokens:[/bold] {session.get('total_cache_create_tokens', 0):,}")
    lines.append(f"[bold]Total cost:[/bold]           ${session.get('total_cost_usd', 0):.4f}")

    if messages:
        lines.append("")
        table = Table(show_header=True, show_lines=False, pad_edge=False)
        table.add_column("Time", style="dim", width=10)
        table.add_column("Role", width=10)
        table.add_column("Model", width=28)
        table.add_column("In", justify="right", width=7)
        table.add_column("Out", justify="right", width=7)
        table.add_column("Cost", justify="right", width=8)
        table.add_column("Tools", style="dim")

        for msg in messages:
            ts = (msg.get("timestamp") or "")
            # Show just the time portion
            if "T" in ts:
                ts = ts.split("T")[1][:8]
            table.add_row(
                ts,
                msg.get("role", ""),
                msg.get("model") or "",
                str(msg.get("input_tokens", 0)),
                str(msg.get("output_tokens", 0)),
                f"${msg.get('cost_usd', 0):.4f}",
                msg.get("tool_names") or "",
            )

        return Panel.fit(table, title="Telemetry", border_style="yellow")

    return Panel("\n".join(lines), title="Telemetry", border_style="yellow")


def format_survey_results(response: dict, outputs: list[dict]) -> Panel:
    """Build a Panel with survey answers and uplift factors."""
    lines = []
    lines.append(f"[bold]Survey:[/bold] {response.get('survey_id', 'N/A')}")
    lines.append(f"[bold]Submitted:[/bold] {response.get('timestamp', 'N/A')}")

    answers = response.get("answers", {})
    if isinstance(answers, str):
        try:
            answers = json.loads(answers)
        except json.JSONDecodeError:
            answers = {}

    if answers:
        lines.append("")
        lines.append("[bold]Answers:[/bold]")
        for k, v in answers.items():
            lines.append(f"  {k}: {v}")

    if response.get("notes"):
        lines.append(f"[bold]Notes:[/bold] {response['notes']}")

    if outputs:
        lines.append("")
        table = Table(show_header=True, show_lines=False, pad_edge=False)
        table.add_column("Output", style="green")
        table.add_column("Uplift Factor", justify="right", style="bold")
        for out in outputs:
            table.add_row(
                out.get("output_id", ""),
                f"{out.get('uplift_factor', 0):.2f}x",
            )
        # We can't nest a Table in a Panel with other text easily,
        # so render the output info as text
        lines.append("[bold]Uplift Outputs:[/bold]")
        for out in outputs:
            lines.append(f"  {out.get('output_id', '')}: {out.get('uplift_factor', 0):.2f}x")

    return Panel("\n".join(lines), title="Survey Results", border_style="green")


def format_transcript(text: str, compacted: bool = False) -> Panel:
    """Syntax-highlighted transcript display."""
    title = "Compacted Transcript" if compacted else "Transcript"
    syntax = Syntax(text, "markdown", theme="monokai", word_wrap=True)
    return Panel(syntax, title=title, border_style="magenta")


def format_judge_results(result: dict, time_data: dict | None = None) -> Panel:
    """Format LLM judge results as a table of tasks."""
    lines = []
    success = result.get("success", False)
    lines.append(f"[bold]Overall success:[/bold] {'Yes' if success else 'No'}")
    lines.append(f"[bold]Confidence:[/bold] {result.get('confidence', 'N/A')}")

    mins_without = result.get("total_minutes_without_ai")
    lines.append(f"[bold]Total minutes without AI:[/bold] {mins_without if mins_without is not None else 'N/A'}")

    # Show uplift calculation if we have active time data
    if mins_without and time_data and time_data.get("active_minutes"):
        active = time_data["active_minutes"]
        uplift = mins_without / active if active > 0 else 0
        lines.append(f"[bold green]Uplift:[/bold green] [green]{mins_without}m / {active}m = {uplift:.1f}x[/green]")

    if result.get("reasoning"):
        lines.append(f"[bold]Reasoning:[/bold] {result['reasoning']}")

    tasks = result.get("tasks", [])
    if tasks:
        lines.append("")
        lines.append("[bold]Tasks:[/bold]")
        for i, task in enumerate(tasks, 1):
            status = "[green]OK[/green]" if task.get("succeeded") else "[red]FAIL[/red]"
            mins = task.get("estimated_minutes_without_ai", "?")
            lines.append(f"  {i}. {status} {task.get('description', 'Unknown')} — {mins} min")

    if result.get("model"):
        lines.append("")
        lines.append(f"[dim]Model: {result['model']} | Cost: ${result.get('cost_usd', 0):.4f}[/dim]")

    return Panel("\n".join(lines), title="LLM Judge Results", border_style="red")


def format_script_result(result: dict) -> Panel:
    """Format a generic script result."""
    script_id = result.get("script_id", "unknown")
    status = result.get("status", "unknown")
    style = "green" if status == "completed" else "red"

    lines = []
    lines.append(f"[bold]Script:[/bold] {script_id}")
    lines.append(f"[bold]Status:[/bold] [{style}]{status}[/{style}]")

    if result.get("error"):
        lines.append(f"[bold red]Error:[/bold red] {result['error']}")

    if result.get("started_at"):
        lines.append(f"[bold]Started:[/bold] {result['started_at']}")
    if result.get("completed_at"):
        lines.append(f"[bold]Completed:[/bold] {result['completed_at']}")

    tokens_in = result.get("input_tokens", 0)
    tokens_out = result.get("output_tokens", 0)
    cost = result.get("cost_usd", 0)
    if tokens_in or tokens_out:
        lines.append(f"[bold]Tokens:[/bold] {tokens_in:,} in / {tokens_out:,} out")
        lines.append(f"[bold]Cost:[/bold] ${cost:.4f}")

    return Panel("\n".join(lines), title=f"Script: {script_id}", border_style="cyan")
