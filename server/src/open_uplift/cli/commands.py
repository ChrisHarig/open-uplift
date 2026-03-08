import json

import click

from open_uplift.config import DEFAULT_PORT
from open_uplift.db import init_db


@click.group()
def cli():
    """Open Uplift — engineering productivity measurement."""
    pass


@cli.command()
@click.option("--port", default=None, type=int, help="Port to serve on")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
def serve(port: int | None, host: str):
    """Start the dashboard server."""
    init_db()

    if port is None:
        port = DEFAULT_PORT

    from open_uplift.ingest import sync_all

    click.echo("Syncing session data...")
    stats = sync_all()
    click.echo(
        f"  {stats['sessions_new']} new sessions, "
        f"{stats['sessions_updated']} updated, "
        f"{stats['messages_added']} messages"
    )

    from open_uplift.api import create_app

    app = create_app()
    if host not in ("127.0.0.1", "localhost"):
        click.echo(
            f"\n  WARNING: Binding to {host} exposes the API to your network.\n"
            f"  The API has no authentication — all sessions, transcripts, and\n"
            f"  organization data will be accessible to anyone who can reach this host.\n"
            f"  Use 127.0.0.1 (default) unless you understand the risks.\n"
        )
    click.echo(f"Dashboard: http://{host}:{port}")
    app.run(host=host, port=port, debug=False)


@cli.command()
def sync():
    """Sync Claude Code session data into the local database."""
    init_db()

    from open_uplift.ingest import sync_all

    click.echo("Syncing...")
    stats = sync_all()
    click.echo(
        f"Done: {stats['sessions_new']} new sessions, "
        f"{stats['sessions_updated']} updated, "
        f"{stats['messages_added']} messages added"
    )


@cli.command()
def explain():
    """Learn how Open Uplift measures engineering productivity."""
    from rich.panel import Panel
    from rich.tree import Tree
    from rich.rule import Rule

    from open_uplift.cli.formatting import console

    console.print()
    console.print(Panel(
        "Open Uplift measures how much faster you work with AI coding assistants. "
        "It compares the time tasks actually took with an LLM estimate of how long "
        "they'd take without AI, giving you a concrete uplift factor.",
        title="What is Open Uplift?",
        border_style="blue",
    ))

    console.print(Rule("Setup Guide"))

    console.print(Panel(
        "[bold]Developer Profile[/bold]\n"
        "Tell the judge about your experience level so time estimates are calibrated "
        "to you. A sentence or two about your stack and years of experience is enough.\n"
        "  [cyan]open-uplift serve[/cyan] → Settings → Developer Profile",
        border_style="yellow",
    ))

    console.print(Panel(
        "[bold]Import Sessions[/bold]\n"
        "Open Uplift reads your Claude Code session transcripts automatically when you "
        "sync. Run the command below or hit Sync in Settings to pull in your history.\n"
        "  [cyan]open-uplift sync[/cyan]",
        border_style="yellow",
    ))

    console.print(Panel(
        "[bold]Compaction & Judging[/bold]\n"
        "Each session goes through two LLM passes: compaction summarizes what happened, "
        "then a judge estimates how long it would have taken without AI.\n"
        "  [cyan]open-uplift sessions judge --all[/cyan]\n"
        "  Or use the Judge page in the dashboard.",
        border_style="yellow",
    ))

    console.print(Panel(
        "[bold]Organizations[/bold]\n"
        "Create an org to group sessions by team or project. Add folders to an org to "
        "assign sessions automatically. Share aggregate metrics with your team via a hub server.\n"
        "  [cyan]open-uplift orgs create 'My Org' --member-name admin[/cyan]\n"
        "  [cyan]open-uplift serve[/cyan]  (starts dashboard server)\n"
        "  Team members join with: [cyan]open-uplift orgs join http://hub:7070 --code <invite>[/cyan]",
        border_style="yellow",
    ))

    console.print(Panel(
        "[bold]Sync Settings[/bold]\n"
        "Configure how often Open Uplift syncs your local sessions and pushes/pulls org "
        "data. Set up batch processing to auto-run compaction and judging on new sessions.\n"
        "  [cyan]open-uplift serve[/cyan] → Settings → Sync & Batch Processing",
        border_style="yellow",
    ))

    console.print(Rule("Command Tree"))
    tree = Tree("[bold]open-uplift[/bold]")
    tree.add("[cyan]serve[/cyan]        — Start the dashboard server")
    tree.add("[cyan]sync[/cyan]         — Import session data")
    tree.add("[cyan]explain[/cyan]      — This help page")
    sess = tree.add("[cyan]sessions[/cyan]     — Browse and manage sessions")
    sess.add("[cyan]export[/cyan]     — Export sessions to CSV or JSON")
    sess.add("[cyan]judge[/cyan]      — Run LLM judge on a session")
    sess.add("[cyan]survey[/cyan]     — Record self-reported time estimates")
    sess.add("[cyan]run[/cyan]        — Run compaction or judge scripts individually")
    sess.add("[cyan]show[/cyan]       — View session detail, transcript, telemetry")
    orgs = tree.add("[cyan]orgs[/cyan]         — Manage organizations")
    orgs.add("[cyan]create[/cyan]     — Create a new org (generates invite code)")
    orgs.add("[cyan]join[/cyan]       — Join an org via hub URL + invite code")
    orgs.add("[cyan]sync[/cyan]       — Push/pull org data")
    orgs.add("[cyan]members[/cyan]    — List org members")
    orgs.add("[cyan]invite[/cyan]     — Generate invite code")
    orgs.add("[cyan]update-config[/cyan] — Update sharing config")
    cfg = tree.add("[cyan]config[/cyan]       — Configuration")
    cfg.add("[cyan]scripts[/cyan]    — LLM provider and prompt settings")
    cfg.add("[cyan]surveys[/cyan]    — Survey management")
    cfg.add("[cyan]questions[/cyan]  — Survey question management")
    cfg.add("[cyan]batch-sync[/cyan] — Scheduled processing")
    console.print(tree)
    console.print()


# --- Sessions group ---


@cli.group("sessions", invoke_without_command=True)
@click.pass_context
def sessions_group(ctx):
    """Browse and manage sessions."""
    if ctx.invoked_subcommand is None:
        init_db()
        from open_uplift.cli.session_picker import pick_session
        from open_uplift.db import get_db

        with get_db() as db:
            total = db.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()["cnt"]
            if total == 0:
                click.echo("No sessions found. Run `open-uplift sync` first.")
                return
            session_id = pick_session(db)
            if session_id:
                ctx.invoke(show_cmd, session_id=session_id)


@sessions_group.command("list")
@click.option("--project", default=None, help="Filter by project name")
@click.option("--search", default=None, help="Search by project name or session ID")
@click.option("--limit", default=20, help="Maximum number of sessions to show")
@click.option("--all", "show_all", is_flag=True, help="Show all sessions (no limit)")
def sessions_list(project: str | None, search: str | None, limit: int, show_all: bool):
    """List and search sessions."""
    init_db()

    from open_uplift.cli.formatting import console, format_session_table
    from open_uplift.cli.session_picker import _SESSION_STATUS_SQL, search_sessions
    from open_uplift.db import get_db

    with get_db() as db:
        if search:
            rows = search_sessions(db, search, limit=0 if show_all else limit)
        elif project:
            pattern = f"%{project}%"
            rows = db.execute(
                _SESSION_STATUS_SQL + " WHERE s.project_name LIKE ? ORDER BY s.started_at DESC LIMIT ?",
                (pattern, 0 if show_all else limit),
            ).fetchall()
            rows = [dict(r) for r in rows]
        elif show_all:
            rows = db.execute(
                _SESSION_STATUS_SQL + " ORDER BY s.started_at DESC",
            ).fetchall()
            rows = [dict(r) for r in rows]
        else:
            # Default: show recent sessions with limit
            rows = db.execute(
                _SESSION_STATUS_SQL + " ORDER BY s.started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            rows = [dict(r) for r in rows]

        if not rows:
            click.echo("No sessions found.")
            return

        title = f"Sessions ({len(rows)} shown)"
        if search:
            title = f"Search: '{search}' ({len(rows)} results)"
        elif project:
            title = f"Project: '{project}' ({len(rows)} results)"

        table = format_session_table(rows, title=title)
        console.print(table)
        console.print("[dim]Status: [S]=Survey [C]=Compaction [J]=Judge [J!]=Stale[/dim]")


@sessions_group.command("show")
@click.argument("session_id")
@click.option("--telemetry", is_flag=True, help="Show per-message token breakdown")
@click.option("--survey", "show_survey", is_flag=True, help="Show survey responses and uplift outputs")
@click.option("--transcript", is_flag=True, help="Show raw or compacted transcript")
@click.option("--compact", is_flag=True, help="Show compacted transcript (with --transcript)")
@click.option("--judge", is_flag=True, help="Show LLM judge results")
@click.option("--all", "show_all", is_flag=True, help="Show everything")
def show_cmd(session_id: str, telemetry: bool, show_survey: bool, transcript: bool, compact: bool, judge: bool, show_all: bool):
    """Show detailed session information.

    By default shows session detail, survey, and judge results.
    Use flags to select specific sections, or --all for everything.
    """
    init_db()

    from open_uplift.cli.formatting import (
        console,
        format_judge_results,
        format_script_result,
        format_session_detail,
        format_survey_results,
        format_telemetry,
        format_transcript,
    )
    from open_uplift.cli.session_picker import _SESSION_STATUS_SQL
    from open_uplift.db import get_db
    from open_uplift.time_measurement import compute_time_with_ai

    # If no specific flags are set, show survey + judge by default
    no_flags = not any([telemetry, show_survey, transcript, compact, judge, show_all])
    if no_flags:
        show_survey = True
        judge = True

    with get_db() as db:
        # Get session with status markers — support prefix matching
        row = db.execute(
            _SESSION_STATUS_SQL + " WHERE s.session_id = ?",
            (session_id,),
        ).fetchone()

        if not row and len(session_id) < 36:
            # Try prefix match
            matches = db.execute(
                _SESSION_STATUS_SQL + " WHERE s.session_id LIKE ?",
                (session_id + "%",),
            ).fetchall()
            if len(matches) == 1:
                row = matches[0]
            elif len(matches) > 1:
                click.echo(f"Ambiguous session ID prefix '{session_id}' — matches {len(matches)} sessions. Use more characters.")
                return

        if not row:
            click.echo(f"Session not found: {session_id}")
            return

        session = dict(row)
        session_id = session["session_id"]  # resolve prefix to full ID

        # Always show the detail panel
        time_data = compute_time_with_ai(db, session_id)
        console.print(format_session_detail(session, time_data))

        # Telemetry
        if telemetry or show_all:
            messages = db.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            messages = [dict(m) for m in messages]
            console.print(format_telemetry(session, messages))

        # Survey
        if show_survey or show_all:
            resp = db.execute(
                "SELECT * FROM survey_responses WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if resp:
                resp = dict(resp)
                outputs = db.execute(
                    "SELECT * FROM uplift_outputs WHERE survey_response_id = ?",
                    (resp["id"],),
                ).fetchall()
                outputs = [dict(o) for o in outputs]
                console.print(format_survey_results(resp, outputs))
            else:
                console.print("[dim]No survey response for this session.[/dim]")

        # Transcript
        if transcript or show_all:
            if compact or show_all:
                # Try compacted transcript first
                comp = db.execute(
                    "SELECT result FROM script_results WHERE session_id = ? AND script_id = 'transcript-compact' AND status = 'completed'",
                    (session_id,),
                ).fetchone()
                if comp and comp["result"]:
                    import json
                    result_data = json.loads(comp["result"])
                    text = result_data.get("compacted_transcript", "")
                    if text:
                        console.print(format_transcript(text, compacted=True))

            if not compact or show_all:
                # Show raw transcript
                from open_uplift.scripts import _get_transcript_path, _preprocess_transcript
                from open_uplift.transcript import parse_transcript
                path = _get_transcript_path(db, session_id)
                if path:
                    transcript_data = parse_transcript(path)
                    preprocessed = _preprocess_transcript(transcript_data)
                    if preprocessed:
                        console.print(format_transcript(preprocessed, compacted=False))
                elif show_all:
                    console.print("[dim]Transcript file not found.[/dim]")

        # Judge — show with --judge, --transcript, or --all
        if judge or transcript or show_all:
            import json
            judge_row = db.execute(
                "SELECT * FROM script_results WHERE session_id = ? AND script_id = 'llm-time-estimate'",
                (session_id,),
            ).fetchone()
            if judge_row:
                judge_data = dict(judge_row)
                if judge_data.get("status") == "completed" and judge_data.get("result"):
                    result_data = json.loads(judge_data["result"])
                    console.print(format_judge_results(result_data, time_data))
                else:
                    console.print(format_script_result(judge_data))
            elif judge or show_all:
                console.print("[dim]No LLM judge results for this session.[/dim]")

        # Show compaction script result if judge or show_all
        if show_all:
            comp_row = db.execute(
                "SELECT * FROM script_results WHERE session_id = ? AND script_id = 'transcript-compact'",
                (session_id,),
            ).fetchone()
            if comp_row:
                console.print(format_script_result(dict(comp_row)))


@sessions_group.command("export")
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default="csv", help="Output format")
@click.option("-o", "--output", "output_file", default=None, type=click.Path(), help="Output file (default: stdout)")
@click.option("--project", default=None, help="Filter by project name")
@click.option("--search", default=None, help="Search by project name or session ID")
@click.option("--limit", default=0, type=int, help="Maximum sessions to export (0 = all)")
@click.option("--include-transcript", is_flag=True, help="Include compacted transcript")
@click.option("--include-judge", is_flag=True, help="Include LLM judge results")
@click.option("--include-survey", is_flag=True, help="Include survey responses")
@click.option("--include-telemetry", is_flag=True, help="Include per-message telemetry")
@click.option("--include-all", is_flag=True, help="Include all optional data")
def export_cmd(fmt, output_file, project, search, limit, include_transcript,
               include_judge, include_survey, include_telemetry, include_all):
    """Export sessions to CSV or JSON."""
    init_db()

    from open_uplift.cli.export import build_export_rows, format_csv, format_json
    from open_uplift.cli.session_picker import search_sessions
    from open_uplift.db import get_db

    if include_all:
        include_transcript = include_judge = include_survey = include_telemetry = True

    with get_db() as db:
        # Determine which session IDs to export
        session_ids = None
        conditions: list[str] = []
        params: list = []

        if search:
            found = search_sessions(db, search, limit=limit or 0)
            session_ids = [r["session_id"] for r in found]
            if not session_ids:
                click.echo("No sessions found.", err=True)
                return
        elif project:
            pattern = f"%{project}%"
            found = db.execute(
                "SELECT session_id FROM sessions WHERE project_name LIKE ? ORDER BY started_at DESC",
                (pattern,),
            ).fetchall()
            session_ids = [r["session_id"] for r in found]
            if not session_ids:
                click.echo("No sessions found.", err=True)
                return

        rows = build_export_rows(
            db,
            session_ids=session_ids,
            include_transcript=include_transcript,
            include_judge=include_judge,
            include_survey=include_survey,
            include_telemetry=include_telemetry,
            conditions=conditions if not session_ids else None,
            params=params if not session_ids else None,
            limit=limit,
        )

        if not rows:
            click.echo("No sessions found.", err=True)
            return

        if fmt == "csv":
            output = format_csv(rows)
        else:
            output = format_json(rows)

        if output_file:
            with open(output_file, "w") as f:
                f.write(output)
            click.echo(f"Exported {len(rows)} sessions to {output_file}", err=True)
        else:
            click.echo(output, nl=False)


@sessions_group.command("survey")
@click.option("--session-id", default=None, help="Claude Code session ID (prompts to pick if omitted)")
@click.option("--force", is_flag=True, help="Override existing survey response without prompting")
def survey_cmd(session_id: str | None, force: bool):
    """Run the post-session self-report survey."""
    init_db()

    if session_id is None:
        session_id = _pick_session()
        if session_id is None:
            click.echo("No session selected.")
            return

    from open_uplift.cli.survey import run_survey

    run_survey(session_id, force=force)


@sessions_group.command("run")
@click.argument("script_id", type=click.Choice(["transcript-compact", "llm-time-estimate"]))
@click.option("--session-id", default=None, help="Session ID to run on")
@click.option("--all", "run_all", is_flag=True, help="Run on all sessions missing results")
@click.option("--dry-run", is_flag=True, help="Show what would run without executing")
def run_cmd(script_id: str, session_id: str | None, run_all: bool, dry_run: bool):
    """Run a script (transcript-compact or llm-time-estimate) on sessions."""
    init_db()

    from open_uplift.cli.formatting import console, format_judge_results, format_transcript
    from open_uplift.db import get_db
    from open_uplift.scripts import run_script

    if not session_id and not run_all:
        session_id = _pick_session()
        if not session_id:
            click.echo("No session selected.")
            return

    with get_db() as db:
        if run_all:
            rows = db.execute(
                """SELECT s.session_id, s.project_name FROM sessions s
                   LEFT JOIN script_results sr
                       ON s.session_id = sr.session_id AND sr.script_id = ?
                   WHERE sr.id IS NULL OR sr.status = 'error'
                   ORDER BY s.started_at DESC""",
                (script_id,),
            ).fetchall()
            session_ids = [(r["session_id"], r["project_name"]) for r in rows]

            if dry_run:
                console.print(f"[bold]Dry run:[/bold] would run {script_id} on {len(session_ids)} sessions:")
                for sid, proj in session_ids:
                    console.print(f"  {sid[:12]}... ({proj or 'unknown'})")
                return

            from rich.progress import Progress
            console.print(f"Running [bold]{script_id}[/bold] on {len(session_ids)} sessions...")
            with Progress(console=console) as progress:
                task = progress.add_task(f"Running {script_id}...", total=len(session_ids))
                ok, errors = 0, 0
                for sid, proj in session_ids:
                    progress.update(task, description=f"{sid[:12]}...")
                    result = run_script(db, script_id, sid)
                    if "error" in result:
                        errors += 1
                    else:
                        ok += 1
                    progress.advance(task)
            console.print(f"[bold green]{ok} succeeded[/bold green], [bold red]{errors} errors[/bold red]")
        else:
            if dry_run:
                console.print(f"[bold]Dry run:[/bold] would run {script_id} on {session_id[:12]}...")
                return

            console.print(f"Running [bold]{script_id}[/bold] on {session_id[:12]}...")
            result = run_script(db, script_id, session_id)
            if "error" in result:
                console.print(f"[bold red]Error:[/bold red] {result['error']}")
            else:
                # Rich output for results
                if script_id == "transcript-compact" and result.get("compacted_transcript"):
                    console.print(format_transcript(result["compacted_transcript"], compacted=True))
                    console.print(f"[dim]Tokens: {result.get('input_tokens', 0):,} in / {result.get('output_tokens', 0):,} out | Cost: ${result.get('cost_usd', 0):.4f}[/dim]")
                elif script_id == "llm-time-estimate" and result.get("tasks"):
                    console.print(format_judge_results(result))
                else:
                    console.print(f"[bold green]Done.[/bold green] Result: {json.dumps(result, indent=2)}")


# --- Sessions judge (LLM-only judgement pipeline) ---


@sessions_group.command("judge")
@click.option("--session-id", default=None, help="Session ID to judge")
@click.option("--all", "run_all", is_flag=True, help="Judge all sessions (compact + judge pipeline)")
@click.option("--stale", is_flag=True, help="Re-judge sessions updated since last judgement")
@click.option("--dry-run", is_flag=True, help="Show what would run without executing")
def judge_cmd(session_id: str | None, run_all: bool, stale: bool, dry_run: bool):
    """Run LLM judge pipeline (compact + judge) on sessions.

    This is the primary evaluation flow — surveys are optional side effects.
    Automatically compacts transcripts before judging.
    """
    init_db()

    from open_uplift.cli.formatting import console, format_judge_results
    from open_uplift.db import get_db
    from open_uplift.scripts import run_script

    if not session_id and not run_all and not stale:
        session_id = _pick_session()
        if not session_id:
            click.echo("No session selected.")
            return

    with get_db() as db:
        # Check for API keys before doing any work
        from open_uplift.scripts import _get_script_config
        from open_uplift.keystore import get_api_key
        script_cfg = _get_script_config(db)
        for role in ("compaction", "judge"):
            provider = script_cfg.get(role, {}).get("provider", "anthropic")
            if not get_api_key(db, provider):
                console.print(
                    f"[bold red]Error:[/bold red] No API key configured for [bold]{provider}[/bold].\n"
                    f"Add one with: [cyan]open-uplift serve[/cyan] → Settings → API Keys\n"
                    f"Or set the environment variable (e.g. ANTHROPIC_API_KEY)."
                )
                return
        if run_all or stale:
            if stale:
                # Find sessions where message_count > script_results.session_message_count
                rows = db.execute(
                    """SELECT s.session_id, s.project_name FROM sessions s
                       LEFT JOIN script_results sr
                           ON s.session_id = sr.session_id AND sr.script_id = 'llm-time-estimate'
                       WHERE sr.id IS NULL
                          OR sr.status = 'error'
                          OR (sr.session_message_count IS NOT NULL AND sr.session_message_count < s.message_count)
                       ORDER BY s.started_at DESC""",
                ).fetchall()
            else:
                rows = db.execute(
                    """SELECT s.session_id, s.project_name FROM sessions s
                       LEFT JOIN script_results sr
                           ON s.session_id = sr.session_id AND sr.script_id = 'llm-time-estimate'
                       WHERE sr.id IS NULL OR sr.status = 'error'
                       ORDER BY s.started_at DESC""",
                ).fetchall()
            session_ids = [(r["session_id"], r["project_name"]) for r in rows]

            if dry_run:
                label = "stale/unjudged" if stale else "unjudged"
                console.print(f"[bold]Dry run:[/bold] would judge {len(session_ids)} {label} sessions:")
                for sid, proj in session_ids:
                    console.print(f"  {sid[:12]}... ({proj or 'unknown'})")
                return

            if not session_ids:
                console.print("All sessions are up to date.")
                return

            from rich.progress import Progress
            label = "Judging (stale)" if stale else "Judging"
            console.print(f"[bold]{label}[/bold] {len(session_ids)} sessions (compact + judge)...")
            with Progress(console=console) as progress:
                task = progress.add_task(f"{label}...", total=len(session_ids))
                ok, errors = 0, 0
                last_error = None
                for sid, proj in session_ids:
                    progress.update(task, description=f"{sid[:12]}...")
                    # Run compact first, then judge
                    for script_id in ("transcript-compact", "llm-time-estimate"):
                        result = run_script(db, script_id, sid)
                        if "error" in result:
                            last_error = result["error"]
                            if script_id == "llm-time-estimate":
                                errors += 1
                            break
                    else:
                        ok += 1
                    progress.advance(task)
            console.print(f"[bold green]{ok} succeeded[/bold green], [bold red]{errors} errors[/bold red]")
            if last_error and errors > 0:
                console.print(f"[red]Last error: {last_error}[/red]")
        else:
            if dry_run:
                console.print(f"[bold]Dry run:[/bold] would judge {session_id[:12]}...")
                return

            console.print(f"Judging {session_id[:12]}... (compact + judge)")
            for script_id in ("transcript-compact", "llm-time-estimate"):
                console.print(f"  Running [bold]{script_id}[/bold]...")
                result = run_script(db, script_id, session_id)
                if "error" in result:
                    console.print(f"  [bold red]Error:[/bold red] {result['error']}")
                    return
                if script_id == "llm-time-estimate" and result.get("tasks"):
                    console.print(format_judge_results(result))


# --- Organizations group ---


@cli.group("orgs", invoke_without_command=True)
@click.pass_context
def orgs_group(ctx):
    """Manage organizations."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(orgs_list)
        click.echo()
        click.echo("Commands: list | create | show | delete | add-folders | remove-folders | join | sync | members | invite | update-config")
        click.echo("Run `open-uplift orgs <command> --help` for details.")


@orgs_group.command("list")
def orgs_list():
    """List all organizations."""
    init_db()
    from open_uplift.cli.formatting import console
    from open_uplift.db import get_db
    from rich.table import Table

    with get_db() as db:
        rows = db.execute(
            """SELECT o.*, COUNT(of2.id) as folder_count
               FROM organizations o
               LEFT JOIN org_folders of2 ON o.org_id = of2.org_id
               GROUP BY o.org_id
               ORDER BY o.name"""
        ).fetchall()

    if not rows:
        click.echo("No organizations found. Create one with `open-uplift orgs create`.")
        return

    table = Table(title="Organizations")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Folders", justify="right", width=7)
    table.add_column("Verified", justify="center", width=8)

    for r in rows:
        verified = "Yes" if r["is_verified"] else ""
        table.add_row(r["org_id"], r["name"], r["description"] or "", str(r["folder_count"]), verified)

    console.print(table)


@orgs_group.command("create")
@click.argument("name")
@click.option("--description", "desc", default="", help="Organization description")
@click.option("--member-name", default=None, help="Admin display name")
def orgs_create(name: str, desc: str, member_name: str | None):
    """Create a new organization."""
    init_db()
    import secrets
    from datetime import datetime, timezone

    from open_uplift.config import DEFAULT_SHARING_CONFIG
    from open_uplift.db import get_db
    from open_uplift.surveys import slugify

    org_id = slugify(name)
    if not org_id:
        click.echo("Error: name must contain at least one alphanumeric character.")
        return

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        existing = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
        if existing:
            click.echo(f"Error: Organization '{name}' already exists.")
            return

        # Create org in DB
        db.execute(
            "INSERT INTO organizations (org_id, name, description, is_verified, created_at, sharing_config, org_mode) VALUES (?, ?, ?, 0, ?, ?, ?)",
            (org_id, name, desc, now, json.dumps(DEFAULT_SHARING_CONFIG), "hub"),
        )

        admin_name = member_name or "admin"
        api_key = secrets.token_urlsafe(32)
        db.execute(
            """INSERT INTO hub_members (org_id, member_name, api_key, role, joined_at)
               VALUES (?, ?, ?, 'admin', ?)""",
            (org_id, admin_name, api_key, now),
        )

        invite_code = secrets.token_urlsafe(16)
        db.execute(
            "INSERT INTO hub_invites (invite_code, org_id, created_by, created_at) VALUES (?, ?, ?, ?)",
            (invite_code, org_id, admin_name, now),
        )

        # Store local admin membership
        db.execute(
            """INSERT INTO org_memberships
               (org_id, org_name, member_name, role, sharing_config, api_key, joined_at)
               VALUES (?, ?, ?, 'admin', ?, ?, ?)""",
            (org_id, name, admin_name, json.dumps(DEFAULT_SHARING_CONFIG), api_key, now),
        )

    click.echo(f"Organization '{name}' created (ID: {org_id}, mode: hub)")
    click.echo(f"  Admin: {admin_name}")
    click.echo(f"  API key: {api_key}")
    click.echo(f"  Invite code: {invite_code}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Start the server: open-uplift serve")
    click.echo("  2. Share the invite code with team members")
    click.echo(f"  3. They join with: open-uplift orgs join http://<hub-host>:7070 --code {invite_code} --name 'Their Name'")


@orgs_group.command("show")
@click.argument("org_id")
def orgs_show(org_id: str):
    """Show organization details and stats."""
    init_db()
    from open_uplift.cli.formatting import console
    from open_uplift.db import get_db
    from rich.panel import Panel
    from rich.table import Table

    with get_db() as db:
        org = db.execute("SELECT * FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
        if not org:
            click.echo(f"Organization not found: {org_id}")
            return

        folders = db.execute(
            "SELECT folder_path, added_at FROM org_folders WHERE org_id = ? ORDER BY folder_path",
            (org_id,),
        ).fetchall()

        folder_paths = [f["folder_path"] for f in folders]
        if folder_paths:
            path_conditions = " OR ".join(
                ["(project_path = ? OR project_path LIKE ? || '/%')"] * len(folder_paths)
            )
            path_params = []
            for fp in folder_paths:
                path_params.extend([fp, fp])
            stats = db.execute(
                f"""SELECT
                     COUNT(*) as total_sessions,
                     COALESCE(SUM(total_input_tokens + total_output_tokens), 0) as total_tokens,
                     COALESCE(SUM(total_cost_usd), 0) as total_cost
                   FROM sessions
                   WHERE {path_conditions}""",
                path_params,
            ).fetchone()
            stats = dict(stats)

            # Uplift average
            uplift_row = db.execute(
                f"""SELECT ROUND(AVG(uo.uplift_factor), 2) as avg_uplift, COUNT(*) as count
                   FROM uplift_outputs uo
                   JOIN sessions s ON s.session_id = uo.session_id
                   WHERE uo.output_id = 'llm-judge' AND ({path_conditions})""",
                path_params,
            ).fetchone()
        else:
            stats = {"total_sessions": 0, "total_tokens": 0, "total_cost": 0}
            uplift_row = None

        lines = []
        lines.append(f"[bold]Organization:[/bold] {org['name']}")
        lines.append(f"[bold]ID:[/bold] {org['org_id']}")
        if org["description"]:
            lines.append(f"[bold]Description:[/bold] {org['description']}")
        lines.append(f"[bold]Verified:[/bold] {'Yes' if org['is_verified'] else 'No'}")
        lines.append(f"[bold]Created:[/bold] {org['created_at'][:16]}")
        lines.append("")
        lines.append(f"[bold]Sessions:[/bold] {stats['total_sessions']}")
        lines.append(f"[bold]Total tokens:[/bold] {stats['total_tokens']:,}")
        lines.append(f"[bold]Total cost:[/bold] ${stats['total_cost']:.2f}")
        if uplift_row and uplift_row["count"] > 0:
            lines.append(f"[bold]Avg uplift:[/bold] {uplift_row['avg_uplift']:.2f}x ({uplift_row['count']} sessions)")

        console.print(Panel("\n".join(lines), title="Organization Detail", border_style="blue"))

        if folders:
            table = Table(title="Folders")
            table.add_column("Path", style="green")
            table.add_column("Added", style="dim")
            for f in folders:
                table.add_row(f["folder_path"], f["added_at"][:16])
            console.print(table)
        else:
            console.print("[dim]No folders assigned.[/dim]")


@orgs_group.command("delete")
@click.argument("org_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def orgs_delete(org_id: str, yes: bool):
    """Delete an organization."""
    init_db()
    from open_uplift.db import get_db

    with get_db() as db:
        org = db.execute("SELECT name, org_mode FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
        if not org:
            click.echo(f"Organization not found: {org_id}")
            return

        if not yes:
            if not click.confirm(f"Delete organization '{org['name']}'?"):
                click.echo("Cancelled.")
                return

        mode = org["org_mode"] or "hub"
        if mode == "hub":
            db.execute("DELETE FROM hub_members WHERE org_id = ?", (org_id,))
            db.execute("DELETE FROM hub_invites WHERE org_id = ?", (org_id,))
            db.execute("DELETE FROM hub_sessions WHERE org_id = ?", (org_id,))
            db.execute("DELETE FROM hub_aggregates WHERE org_id = ?", (org_id,))
        elif mode == "member":
            db.execute("DELETE FROM org_memberships WHERE org_id = ?", (org_id,))
        db.execute("DELETE FROM organizations WHERE org_id = ?", (org_id,))
    click.echo(f"Organization '{org['name']}' deleted.")


@orgs_group.command("join")
@click.argument("hub_url")
@click.option("--code", "invite_code", prompt="Invite code", help="Invite code from the org admin")
@click.option("--name", prompt="Your display name", help="Your display name in the org")
def orgs_join(hub_url: str, invite_code: str, name: str):
    """Join an organization via a hub server."""
    init_db()
    from open_uplift.db import get_db
    from open_uplift.sync import join_org

    with get_db() as db:
        try:
            result = join_org(db, hub_url, invite_code, name)
        except Exception as e:
            click.echo(f"Error: {e}")
            return

    click.echo(f"Joined '{result['org_name']}' (org_id: {result['org_id']})")
    sharing = result.get("sharing_config", {})
    level = sharing.get("level", 1)
    stats = sharing.get("stats", {})
    enabled = [k for k, v in stats.items() if v]
    click.echo(f"  Sharing level: {level} ({'aggregates + sessions' if level >= 2 else 'aggregates only'})")
    click.echo(f"  Shared stats: {', '.join(enabled)}")
    click.echo()
    click.echo("Run `open-uplift orgs sync` to push your data.")


@orgs_group.command("sync")
@click.argument("org_id", required=False)
@click.option("--all", "sync_all", is_flag=True, help="Sync all org memberships")
def orgs_sync(org_id: str | None, sync_all: bool):
    """Sync data with an organization hub."""
    init_db()
    from open_uplift.db import get_db

    if sync_all or not org_id:
        from open_uplift.sync import sync_all_orgs
        results = sync_all_orgs()
        if not results:
            click.echo("No org memberships found. Join one first with `open-uplift orgs join`.")
            return
        for r in results:
            if "error" in r:
                click.echo(f"  {r['org_id']}: Error — {r['error']}")
            else:
                click.echo(f"  {r['org_id']}: Synced")
    else:
        from open_uplift.sync import sync_org
        with get_db() as db:
            membership = db.execute(
                "SELECT * FROM org_memberships WHERE org_id = ?", (org_id,)
            ).fetchone()
            if not membership:
                click.echo(f"No membership found for org: {org_id}")
                return
            result = sync_org(db, dict(membership))

        push = result.get("push", {})
        pull = result.get("pull", {})
        if "error" in push:
            click.echo(f"Push error: {push['error']}")
        else:
            click.echo(f"Push: OK (sessions sent: {push.get('received_sessions', 0)})")
        if "error" in pull:
            click.echo(f"Pull error: {pull['error']}")
        else:
            click.echo(f"Pull: OK (org: {pull.get('org_name', org_id)})")


@orgs_group.command("members")
@click.argument("org_id")
def orgs_members(org_id: str):
    """List members of an organization."""
    init_db()
    from open_uplift.cli.formatting import console
    from open_uplift.db import get_db
    from rich.table import Table

    with get_db() as db:
        membership = db.execute(
            "SELECT * FROM org_memberships WHERE org_id = ?", (org_id,)
        ).fetchone()

        # Try local hub_members first
        members = db.execute(
            "SELECT member_name, role, joined_at, last_push_at FROM hub_members WHERE org_id = ?",
            (org_id,),
        ).fetchall()

        if not members and membership and membership["hub_url"] and membership["api_key"]:
            # Query remote hub
            import requests
            try:
                resp = requests.get(
                    f"{membership['hub_url']}/hub/members",
                    headers={"Authorization": f"Bearer {membership['api_key']}"},
                    timeout=30,
                )
                if resp.status_code == 200:
                    members = resp.json()
            except Exception as e:
                click.echo(f"Error querying hub: {e}")
                return

    if not members:
        click.echo(f"No members found for org: {org_id}.")
        return

    table = Table(title="Organization Members")
    table.add_column("Name", style="green")
    table.add_column("Role")
    table.add_column("Joined", style="dim")
    table.add_column("Last Push", style="dim")

    for m in members:
        m_dict = dict(m) if hasattr(m, "keys") else m
        table.add_row(
            m_dict.get("member_name", "unknown"),
            m_dict.get("role", "member"),
            (m_dict.get("joined_at") or "")[:16],
            (m_dict.get("last_push_at") or "")[:16],
        )
    console.print(table)


@orgs_group.command("invite")
@click.argument("org_id")
def orgs_invite(org_id: str):
    """Generate a reusable invite code for an organization."""
    init_db()
    import secrets
    from datetime import datetime, timezone

    from open_uplift.db import get_db

    with get_db() as db:
        org = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
        if not org:
            click.echo(f"Organization not found: {org_id}")
            return

        invite_code = secrets.token_urlsafe(16)
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO hub_invites (invite_code, org_id, created_at) VALUES (?, ?, ?)",
            (invite_code, org_id, now),
        )
    click.echo(f"Invite code: {invite_code}")
    click.echo("Share this with team members to join the org.")


@orgs_group.command("add-folders")
@click.argument("org_id")
@click.argument("folder_paths", nargs=-1, required=True)
def orgs_add_folders(org_id: str, folder_paths: tuple[str, ...]):
    """Add folder paths to an organization."""
    init_db()
    from datetime import datetime, timezone

    from open_uplift.db import get_db

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        org = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
        if not org:
            click.echo(f"Organization not found: {org_id}")
            return

        added = 0
        for fp in folder_paths:
            conflict = db.execute(
                """SELECT of2.org_id FROM org_folders of2
                   WHERE of2.folder_path = ?
                      OR of2.folder_path LIKE ? || '/%'
                      OR ? LIKE of2.folder_path || '/%'""",
                (fp, fp, fp),
            ).fetchone()
            if conflict and conflict["org_id"] != org_id:
                click.echo(f"Warning: '{fp}' conflicts with org '{conflict['org_id']}', skipping.")
                continue
            db.execute(
                "INSERT OR IGNORE INTO org_folders (org_id, folder_path, added_at) VALUES (?, ?, ?)",
                (org_id, fp, now),
            )
            added += 1
    click.echo(f"Added {added} folder(s) to '{org_id}'.")


@orgs_group.command("remove-folders")
@click.argument("org_id")
@click.argument("folder_paths", nargs=-1, required=True)
def orgs_remove_folders(org_id: str, folder_paths: tuple[str, ...]):
    """Remove folder paths from an organization."""
    init_db()
    from open_uplift.db import get_db

    with get_db() as db:
        removed = 0
        for fp in folder_paths:
            cursor = db.execute(
                "DELETE FROM org_folders WHERE org_id = ? AND folder_path = ?",
                (org_id, fp),
            )
            removed += cursor.rowcount
    click.echo(f"Removed {removed} folder(s) from '{org_id}'.")




@orgs_group.command("update-config")
@click.argument("org_id")
@click.option("--level", type=int, help="Sharing level (1=aggregates, 2=aggregates+sessions)")
@click.option("--enable", multiple=True, help="Enable a stat (tokens, cost, messages, tool_calls, uplift, compacted_transcripts)")
@click.option("--disable", multiple=True, help="Disable a stat")
def orgs_update_config(org_id: str, level: int | None, enable: tuple, disable: tuple):
    """Update the sharing config for an organization."""
    init_db()
    from open_uplift.config import DEFAULT_SHARING_CONFIG
    from open_uplift.db import get_db

    with get_db() as db:
        membership = db.execute(
            "SELECT * FROM org_memberships WHERE org_id = ?", (org_id,)
        ).fetchone()

        # Try local DB first
        org = db.execute("SELECT sharing_config FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
        if org and org["sharing_config"]:
            sharing = json.loads(org["sharing_config"])
        else:
            sharing = dict(DEFAULT_SHARING_CONFIG)

        if level is not None:
            sharing["level"] = level
        stats = sharing.get("stats", {})
        for stat in enable:
            stats[stat] = True
        for stat in disable:
            stats[stat] = False
        sharing["stats"] = stats

        if org:
            # Update locally
            db.execute(
                "UPDATE organizations SET sharing_config = ? WHERE org_id = ?",
                (json.dumps(sharing), org_id),
            )
            click.echo("Config updated locally.")
        elif membership and membership["hub_url"] and membership["api_key"]:
            # Update via remote hub
            import requests
            try:
                resp = requests.put(
                    f"{membership['hub_url']}/hub/config",
                    json={"sharing_config": sharing},
                    headers={"Authorization": f"Bearer {membership['api_key']}"},
                    timeout=30,
                )
                if resp.status_code != 200:
                    click.echo(f"Error: {resp.json().get('error', resp.text)}")
                    return
                click.echo("Config updated on hub.")
            except Exception as e:
                click.echo(f"Error: {e}")
                return
        else:
            click.echo(f"Organization not found: {org_id}")
            return

    click.echo(f"  Level: {sharing.get('level', 1)}")
    enabled_stats = [k for k, v in stats.items() if v]
    click.echo(f"  Enabled stats: {', '.join(enabled_stats)}")


# --- Config commands ---


@cli.group("config")
def config_group():
    """Manage surveys, questions, scripts, API keys, profile, and batch sync."""
    pass


# --- Surveys sub-group ---


@config_group.group("surveys")
def surveys_subgroup():
    """Manage survey definitions."""
    pass


@surveys_subgroup.command("show-active")
def config_show_active():
    """Show the currently active survey."""
    init_db()
    from open_uplift.db import get_db
    from open_uplift.surveys import get_active_survey

    with get_db() as db:
        survey = get_active_survey(db)
    click.echo(f"Active survey: {survey['id']} — {survey['name']}")
    click.echo(f"  Description: {survey['description']}")
    click.echo(f"  Questions: {', '.join(q['id'] for q in survey['questions'])}")
    click.echo(f"  Outputs: {', '.join(o['id'] for o in survey['outputs'])}")
    if survey.get("scripts"):
        click.echo(f"  Scripts: {', '.join(s['id'] for s in survey['scripts'])}")


@surveys_subgroup.command("set-active")
@click.argument("survey_id")
def config_set_active(survey_id: str):
    """Set the active survey by ID."""
    init_db()
    from open_uplift.db import get_db
    from open_uplift.surveys import set_active_survey

    try:
        with get_db() as db:
            set_active_survey(db, survey_id)
    except ValueError as e:
        click.echo(f"Error: {e}")
        return
    click.echo(f"Active survey set to: {survey_id}")


@surveys_subgroup.command("list")
def config_list_surveys():
    """List all available surveys."""
    init_db()
    from open_uplift.db import get_db
    from open_uplift.surveys import get_active_survey_id, get_surveys

    with get_db() as db:
        surveys = get_surveys(db)
        active_id = get_active_survey_id(db)
    for sid, s in surveys.items():
        marker = " [active]" if sid == active_id else ""
        click.echo(f"  {sid}: {s['name']}{marker}")
        click.echo(f"    {s['description']}")


@surveys_subgroup.command("add")
@click.option("--name", default=None, help="Survey name/ID")
@click.option("--description", "desc", default=None, help="Survey description")
@click.option("--questions", "question_list", default=None, help="Comma-separated question IDs")
def config_add_survey(name, desc, question_list):
    """Add a new survey definition."""
    init_db()
    import questionary

    from open_uplift.db import get_db
    from open_uplift.surveys import add_survey, get_questions, slugify

    with get_db() as db:
        available = get_questions(db)

    if not available:
        click.echo("No questions defined. Add questions first with `config questions add`.")
        return

    if not name:
        name = questionary.text("Survey name:").ask()
        if not name:
            click.echo("Cancelled.")
            return
    if not desc:
        desc = questionary.text("Description:").ask() or ""

    survey_id = slugify(name)

    if question_list:
        selected_ids = [q.strip() for q in question_list.split(",")]
    else:
        choices = [questionary.Choice(title=f"{qid}: {q['label']}", value=qid) for qid, q in available.items()]
        selected_ids = questionary.checkbox("Select questions:", choices=choices).ask()
        if not selected_ids:
            click.echo("Cancelled.")
            return

    # Validate question IDs
    for qid in selected_ids:
        if qid not in available:
            click.echo(f"Unknown question: {qid}")
            return

    survey = {
        "id": survey_id,
        "name": name,
        "description": desc,
        "questions": selected_ids,
        "scripts": [],
        "outputs": [{"id": qid, "name": qid, "description": ""} for qid in selected_ids],
    }

    with get_db() as db:
        add_survey(db, survey)
    click.echo(f"Survey '{survey_id}' added with {len(selected_ids)} question(s).")


# --- Questions sub-group ---


@config_group.group("questions")
def questions_subgroup():
    """Manage question definitions."""
    pass


@questions_subgroup.command("list")
def config_list_questions():
    """List all available questions."""
    init_db()
    from open_uplift.db import get_db
    from open_uplift.surveys import get_questions

    with get_db() as db:
        questions = get_questions(db)
    for qid, q in questions.items():
        click.echo(f"  {qid}: {q['label']}")
        if q.get("description"):
            click.echo(f"    {q['description']}")


@questions_subgroup.command("add")
@click.option("--id", "question_id", default=None, help="Question ID (slug)")
@click.option("--label", default=None, help="Question label")
@click.option("--type", "qtype", default=None, type=click.Choice(["number", "select"]), help="Question type")
@click.option("--min", "qmin", default=None, type=float, help="Minimum value (number type)")
@click.option("--max", "qmax", default=None, type=float, help="Maximum value (number type)")
@click.option("--description", "desc", default=None, help="Question description")
def config_add_question(question_id, label, qtype, qmin, qmax, desc):
    """Add a new question definition."""
    init_db()
    import questionary

    from open_uplift.db import get_db
    from open_uplift.surveys import add_question, slugify

    # Interactive mode if flags not provided
    if not label:
        label = questionary.text("Question label:").ask()
        if not label:
            click.echo("Cancelled.")
            return
    if not question_id:
        default_id = slugify(label)
        question_id = questionary.text("Question ID:", default=default_id).ask()
        if not question_id:
            click.echo("Cancelled.")
            return
    if not qtype:
        qtype = questionary.select("Question type:", choices=["number", "select"]).ask()
        if not qtype:
            click.echo("Cancelled.")
            return
    if not desc:
        desc = questionary.text("Description (optional):").ask() or ""

    question = {
        "id": question_id,
        "label": label,
        "type": qtype,
        "description": desc,
        "required": True,
    }

    if qtype == "number":
        if qmin is None:
            qmin = float(questionary.text("Min value:", default="0.1").ask() or "0.1")
        if qmax is None:
            qmax = float(questionary.text("Max value:", default="10000").ask() or "10000")
        question["validation"] = {"min": qmin, "max": qmax, "type": "number", "max_decimals": 2}

    with get_db() as db:
        add_question(db, question)
    click.echo(f"Question '{question_id}' added.")


# --- Scripts sub-group ---


@config_group.group("scripts")
def scripts_subgroup():
    """Manage script (compaction, judge) configuration."""
    pass


@scripts_subgroup.command("show")
@click.argument("name", required=False, default=None, type=click.Choice(["compaction", "judge"]))
def config_scripts_show(name):
    """Show current script model and provider settings.

    Optionally pass a script NAME (compaction or judge) to see full details
    including the prompt text.
    """
    init_db()
    from open_uplift.cli.formatting import console
    from open_uplift.db import get_db
    from open_uplift.scripts import _get_script_config

    with get_db() as db:
        config = _get_script_config(db)

        if name:
            from rich.panel import Panel
            s = config.get(name, {})
            provider = s.get("provider", "anthropic")
            model = s.get("model", "")
            prompt_id = s.get("prompt_id", "")
            lines = [
                f"[cyan]Provider:[/cyan] {provider}",
                f"[cyan]Model:[/cyan]    {model}",
                f"[cyan]Prompt:[/cyan]   {prompt_id}",
            ]
            if name == "judge":
                profile = "on" if s.get("include_profile", True) else "off"
                lines.append(f"[cyan]Profile:[/cyan]  {profile}")
            console.print(Panel("\n".join(lines), title=f"[bold]{name}[/bold] script config"))

            # Look up the prompt text
            if prompt_id:
                row = db.execute("SELECT * FROM prompts WHERE prompt_id = ?", (prompt_id,)).fetchone()
            else:
                row = db.execute("SELECT * FROM prompts WHERE category = ? AND is_default = 1", (name,)).fetchone()
            if row:
                console.print(f"\n[bold]Prompt:[/bold] {row['name']} ({row['prompt_id']})")
                console.print(row["system_prompt"])
            else:
                console.print("\n[dim]No prompt found.[/dim]")
            return

    from rich.table import Table
    table = Table(title="Script Configuration")
    table.add_column("Script", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("Model", style="green")
    table.add_column("Prompt", style="green")
    table.add_column("Extra", style="dim")

    for script_name in ("compaction", "judge"):
        s = config.get(script_name, {})
        extra = ""
        if script_name == "judge":
            profile = "profile=on" if s.get("include_profile", True) else "profile=off"
            extra = profile
        table.add_row(
            script_name,
            s.get("provider", "anthropic"),
            s.get("model", ""),
            s.get("prompt_id", ""),
            extra,
        )

    console.print(table)


@scripts_subgroup.command("set")
@click.option("--judge-model", default=None, help="Model for judge script")
@click.option("--judge-provider", default=None, type=click.Choice(["anthropic", "openai", "openrouter", "other"]), help="Provider for judge")
@click.option("--judge-prompt", default=None, help="Prompt ID for judge")
@click.option("--compaction-model", default=None, help="Model for compaction script")
@click.option("--compaction-provider", default=None, type=click.Choice(["anthropic", "openai", "openrouter", "other"]), help="Provider for compaction")
@click.option("--compaction-prompt", default=None, help="Prompt ID for compaction")
def config_scripts_set(judge_model, judge_provider, judge_prompt, compaction_model, compaction_provider, compaction_prompt):
    """Update script configuration settings."""
    if all(v is None for v in (judge_model, judge_provider, judge_prompt, compaction_model, compaction_provider, compaction_prompt)):
        click.echo("No options specified. Use --help to see available options.")
        return
    init_db()
    from open_uplift.db import get_db
    from open_uplift.scripts import _get_script_config
    from open_uplift.surveys import _set_config

    with get_db() as db:
        config = _get_script_config(db)

        if judge_model:
            config.setdefault("judge", {})["model"] = judge_model
        if judge_provider:
            config.setdefault("judge", {})["provider"] = judge_provider
        if judge_prompt:
            config.setdefault("judge", {})["prompt_id"] = judge_prompt
        if compaction_model:
            config.setdefault("compaction", {})["model"] = compaction_model
        if compaction_provider:
            config.setdefault("compaction", {})["provider"] = compaction_provider
        if compaction_prompt:
            config.setdefault("compaction", {})["prompt_id"] = compaction_prompt

        _set_config(db, "script_config", config)

    click.echo("Script configuration updated.")


@scripts_subgroup.command("list-prompts")
@click.argument("prompt_id", required=False, default=None)
def config_list_prompts(prompt_id):
    """List judge and compaction prompts.

    Optionally pass a PROMPT_ID to see full details including the prompt text.
    """
    init_db()

    from open_uplift.cli.formatting import console
    from open_uplift.db import get_db

    with get_db() as db:
        if prompt_id:
            row = db.execute("SELECT * FROM prompts WHERE prompt_id = ?", (prompt_id,)).fetchone()
            if not row:
                click.echo(f"Prompt '{prompt_id}' not found.")
                return

            from rich.panel import Panel
            is_default = "Yes" if row["is_default"] else "No"
            lines = [
                f"[cyan]ID:[/cyan]          {row['prompt_id']}",
                f"[cyan]Category:[/cyan]    {row['category']}",
                f"[cyan]Name:[/cyan]        {row['name']}",
                f"[cyan]Default:[/cyan]     {is_default}",
                f"[cyan]Description:[/cyan] {row['description'] or ''}",
            ]
            console.print(Panel("\n".join(lines), title=f"[bold]{row['prompt_id']}[/bold]"))
            console.print("\n[bold]System Prompt:[/bold]")
            console.print(row["system_prompt"])

            if row["output_schema"]:
                schema = json.loads(row["output_schema"])
                console.print("\n[bold]Output Schema:[/bold]")
                for field in schema:
                    req = "required" if field.get("required") else "optional"
                    console.print(f"  [cyan]{field['name']}[/cyan] ({field['type']}, {req}): {field.get('description', '')}")
            return

        rows = db.execute("SELECT * FROM prompts ORDER BY category, prompt_id").fetchall()

    if not rows:
        click.echo("No prompts found.")
        return

    from rich.table import Table
    table = Table(title="Prompts")
    table.add_column("ID", style="cyan")
    table.add_column("Category", style="green")
    table.add_column("Name")
    table.add_column("Default", justify="center", width=7)
    table.add_column("Schema", justify="center", width=7)

    for r in rows:
        is_default = "Yes" if r["is_default"] else ""
        has_schema = "Yes" if r["output_schema"] else ""
        table.add_row(r["prompt_id"], r["category"], r["name"], is_default, has_schema)

    console.print(table)


@scripts_subgroup.command("edit-prompt")
@click.argument("prompt_id")
def config_edit_prompt(prompt_id):
    """Edit a prompt in $EDITOR (or inline if no editor)."""
    import os
    import subprocess
    import tempfile

    init_db()
    from open_uplift.db import get_db

    with get_db() as db:
        row = db.execute("SELECT * FROM prompts WHERE prompt_id = ?", (prompt_id,)).fetchone()

    if not row:
        click.echo(f"Prompt '{prompt_id}' not found.")
        return

    current_text = row["system_prompt"]
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")

    if editor:
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(current_text)
            tmp_path = f.name

        try:
            subprocess.run([editor, tmp_path], check=True)
            with open(tmp_path) as f:
                new_text = f.read()
        finally:
            os.unlink(tmp_path)
    else:
        import questionary
        click.echo(f"No $EDITOR set. Editing inline for prompt: {prompt_id}")
        click.echo(f"Current text ({len(current_text)} chars):")
        click.echo(current_text[:500])
        if len(current_text) > 500:
            click.echo("... (truncated)")
        new_text = questionary.text("New prompt text (or press Enter to keep current):").ask()
        if not new_text:
            click.echo("Kept existing prompt.")
            return

    if new_text.strip() == current_text.strip():
        click.echo("No changes made.")
        return

    with get_db() as db:
        db.execute("UPDATE prompts SET system_prompt = ? WHERE prompt_id = ?", (new_text.strip(), prompt_id))
    click.echo(f"Prompt '{prompt_id}' updated.")


# --- Keys sub-group ---


@config_group.group("keys")
def keys_subgroup():
    """Manage API keys."""
    pass


@keys_subgroup.command("add")
@click.argument("provider", type=click.Choice(["anthropic", "openai"]))
@click.option("--name", default="default", help="Key name (e.g. 'default', 'work')")
def set_api_key_cmd(provider: str, name: str):
    """Store an API key for the given provider."""
    import getpass

    init_db()
    api_key = getpass.getpass(f"Enter your {provider} API key: ")
    if not api_key.strip():
        click.echo("No key entered.")
        return

    from open_uplift.db import get_db
    from open_uplift.keystore import store_api_key

    with get_db() as db:
        store_api_key(db, provider, name, api_key.strip())
    click.echo(f"API key stored for {provider}/{name}")


@keys_subgroup.command("list")
def keys_list_cmd():
    """List stored API keys (providers and names, not values)."""
    init_db()
    from open_uplift.cli.formatting import console
    from open_uplift.db import get_db
    from open_uplift.keystore import list_api_keys
    from rich.table import Table

    with get_db() as db:
        keys = list_api_keys(db)

    if not keys:
        click.echo("No API keys stored. Add one with `open-uplift config keys add anthropic`.")
        return

    table = Table(title="API Keys")
    table.add_column("Provider", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Created", style="dim")
    for k in keys:
        table.add_row(k["provider"], k["key_name"], (k.get("created_at") or "")[:16])
    console.print(table)


# --- Profile sub-group ---


@config_group.group("profile")
def profile_subgroup():
    """Manage developer profile used by the LLM judge."""
    pass


@profile_subgroup.command("show")
def profile_show():
    """Show current developer profile."""
    init_db()
    from open_uplift.db import get_db
    from open_uplift.surveys import _get_config

    with get_db() as db:
        profile = _get_config(db, "user_profile")
        script_config = db.execute("SELECT value FROM config WHERE key = 'script_config'").fetchone()

    if not profile or not profile.get("experience_description"):
        click.echo("No developer profile set.")
        click.echo("Set one with: open-uplift config profile set \"Your description here\"")
    else:
        click.echo(f"Developer profile: {profile['experience_description']}")

    # Show include_profile toggle status
    include = True
    if script_config:
        import json
        cfg = json.loads(script_config["value"])
        include = cfg.get("judge", {}).get("include_profile", True)
    click.echo(f"Include in judge prompt: {'Yes' if include else 'No'}")


@profile_subgroup.command("set")
@click.argument("description")
def profile_set(description: str):
    """Set your developer profile description (used in judge prompts)."""
    init_db()
    from open_uplift.db import get_db
    from open_uplift.surveys import _set_config

    with get_db() as db:
        _set_config(db, "user_profile", {"experience_description": description})
    click.echo("Developer profile updated.")


@profile_subgroup.command("toggle")
def profile_toggle():
    """Toggle whether the developer profile is included in judge prompts."""
    init_db()
    from open_uplift.db import get_db
    from open_uplift.scripts import _get_script_config
    from open_uplift.surveys import _set_config

    with get_db() as db:
        config = _get_script_config(db)
        current = config.get("judge", {}).get("include_profile", True)
        config.setdefault("judge", {})["include_profile"] = not current
        _set_config(db, "script_config", config)

    state = "disabled" if current else "enabled"
    click.echo(f"Developer profile in judge prompt: {state}")


# --- Batch Sync sub-group ---


@config_group.group("batch-sync", invoke_without_command=True)
@click.pass_context
def batch_sync_subgroup(ctx):
    """Manage scheduled batch sync configuration."""
    if ctx.invoked_subcommand is None:
        _show_batch_sync_config()


def _show_batch_sync_config():
    """Show current batch sync configuration as a Rich panel."""
    init_db()
    from open_uplift.cli.formatting import console
    from open_uplift.db import get_db
    from open_uplift.job_queue import _get_run_mode_config
    from rich.panel import Panel

    with get_db() as db:
        config = _get_run_mode_config(db)

    enabled = config.get("enabled", False)
    start_hour = config.get("start_hour", 2)
    frequency_hours = config.get("frequency_hours", 24.0)

    lines = []
    lines.append(f"[bold]Status:[/bold] {'[green]Enabled[/green]' if enabled else '[dim]Disabled[/dim]'}")
    lines.append(f"[bold]Start hour:[/bold] {start_hour:02d}:00")
    lines.append(f"[bold]Frequency:[/bold] Every {frequency_hours}h")
    if enabled:
        lines.append("")
        lines.append(f"[dim]Syncs and runs compaction + judge every {frequency_hours}h, starting at {start_hour:02d}:00[/dim]")
    lines.append("")
    lines.append("[dim]Commands: set --start-hour N --frequency N | set --off[/dim]")

    console.print(Panel("\n".join(lines), title="Batch Sync Configuration", border_style="cyan"))


@batch_sync_subgroup.command("show")
def batch_sync_show():
    """Show current batch sync configuration."""
    _show_batch_sync_config()


@batch_sync_subgroup.command("set")
@click.option("--start-hour", type=click.IntRange(0, 23), default=None, help="Hour of day (0-23) for first run")
@click.option("--frequency", type=float, default=None, help="Hours between runs (e.g. 24, 12, 0.5)")
@click.option("--off", "turn_off", is_flag=True, default=False, help="Disable batch sync")
def batch_sync_set(start_hour, frequency, turn_off):
    """Update batch sync configuration."""
    init_db()
    from open_uplift.db import get_db
    from open_uplift.job_queue import _get_run_mode_config, _set_run_mode_config, update_scheduler_config

    if turn_off:
        with get_db() as db:
            config = _get_run_mode_config(db)
            config["enabled"] = False
            _set_run_mode_config(db, config)
        update_scheduler_config()
        click.echo("Batch sync disabled.")
        return

    if start_hour is None and frequency is None:
        click.echo("Nothing to update. Use --start-hour, --frequency, or --off.")
        return

    with get_db() as db:
        config = _get_run_mode_config(db)
        if start_hour is not None:
            config["start_hour"] = start_hour
        if frequency is not None:
            config["frequency_hours"] = frequency
        config["enabled"] = True
        _set_run_mode_config(db, config)

    update_scheduler_config()
    click.echo(
        f"Batch sync enabled: every {config['frequency_hours']}h starting at {config['start_hour']:02d}:00"
    )


# Hidden backward-compat alias: `config run-modes` → shows batch-sync config
@config_group.command("run-modes", hidden=True)
def compat_run_modes():
    """(Deprecated) Use 'config batch-sync' instead."""
    _show_batch_sync_config()


# --- Hidden backward-compat aliases on config_group ---


@config_group.command("show-active", hidden=True)
@click.pass_context
def compat_show_active(ctx):
    """(Deprecated) Use 'config surveys show-active' instead."""
    ctx.invoke(config_show_active)


@config_group.command("set-active", hidden=True)
@click.argument("survey_id")
@click.pass_context
def compat_set_active(ctx, survey_id):
    """(Deprecated) Use 'config surveys set-active' instead."""
    ctx.invoke(config_set_active, survey_id=survey_id)


@config_group.command("list-surveys", hidden=True)
@click.pass_context
def compat_list_surveys(ctx):
    """(Deprecated) Use 'config surveys list' instead."""
    ctx.invoke(config_list_surveys)


@config_group.command("add-survey", hidden=True)
@click.option("--name", default=None)
@click.option("--description", "desc", default=None)
@click.option("--questions", "question_list", default=None)
@click.pass_context
def compat_add_survey(ctx, name, desc, question_list):
    """(Deprecated) Use 'config surveys add' instead."""
    ctx.invoke(config_add_survey, name=name, desc=desc, question_list=question_list)


@config_group.command("list-questions", hidden=True)
@click.pass_context
def compat_list_questions(ctx):
    """(Deprecated) Use 'config questions list' instead."""
    ctx.invoke(config_list_questions)


@config_group.command("add-question", hidden=True)
@click.option("--id", "question_id", default=None)
@click.option("--label", default=None)
@click.option("--type", "qtype", default=None, type=click.Choice(["number", "select"]))
@click.option("--min", "qmin", default=None, type=float)
@click.option("--max", "qmax", default=None, type=float)
@click.option("--description", "desc", default=None)
@click.pass_context
def compat_add_question(ctx, question_id, label, qtype, qmin, qmax, desc):
    """(Deprecated) Use 'config questions add' instead."""
    ctx.invoke(config_add_question, question_id=question_id, label=label, qtype=qtype, qmin=qmin, qmax=qmax, desc=desc)


@config_group.command("show-prompts", hidden=True)
@click.pass_context
def compat_show_prompts(ctx):
    """(Deprecated) Use 'config scripts list-prompts' instead."""
    ctx.invoke(config_list_prompts)


@config_group.command("edit-prompt", hidden=True)
@click.argument("prompt_id")
@click.pass_context
def compat_edit_prompt(ctx, prompt_id):
    """(Deprecated) Use 'config scripts edit-prompt' instead."""
    ctx.invoke(config_edit_prompt, prompt_id=prompt_id)


@config_group.command("show-llm-config", hidden=True)
@click.pass_context
def compat_show_llm_config(ctx):
    """(Deprecated) Use 'config scripts show' instead."""
    ctx.invoke(config_scripts_show)


@config_group.command("set-llm-config", hidden=True)
@click.option("--judge-model", default=None)
@click.option("--judge-provider", default=None, type=click.Choice(["anthropic", "openai", "openrouter", "other"]))
@click.option("--judge-prompt", default=None)
@click.option("--compaction-model", default=None)
@click.option("--compaction-provider", default=None, type=click.Choice(["anthropic", "openai", "openrouter", "other"]))
@click.option("--compaction-prompt", default=None)
@click.pass_context
def compat_set_llm_config(ctx, judge_model, judge_provider, judge_prompt, compaction_model, compaction_provider, compaction_prompt):
    """(Deprecated) Use 'config scripts set' instead."""
    ctx.invoke(config_scripts_set, judge_model=judge_model, judge_provider=judge_provider, judge_prompt=judge_prompt,
               compaction_model=compaction_model, compaction_provider=compaction_provider, compaction_prompt=compaction_prompt)


@config_group.command("set-api-key", hidden=True)
@click.argument("provider", type=click.Choice(["anthropic", "openai"]))
@click.option("--name", default="default")
@click.pass_context
def compat_set_api_key(ctx, provider, name):
    """(Deprecated) Use 'config keys add' instead."""
    ctx.invoke(set_api_key_cmd, provider=provider, name=name)


# --- Backward-compat aliases ---


@cli.command("show", hidden=True)
@click.argument("session_id")
@click.option("--telemetry", is_flag=True, help="Show per-message token breakdown")
@click.option("--survey", "show_survey", is_flag=True, help="Show survey responses and uplift outputs")
@click.option("--transcript", is_flag=True, help="Show raw or compacted transcript")
@click.option("--compact", is_flag=True, help="Show compacted transcript (with --transcript)")
@click.option("--judge", is_flag=True, help="Show LLM judge results")
@click.option("--all", "show_all", is_flag=True, help="Show everything")
@click.pass_context
def show_compat(ctx, **kwargs):
    """(Deprecated) Use 'sessions show' instead."""
    ctx.invoke(show_cmd, **kwargs)


@cli.command("survey", hidden=True)
@click.option("--session-id", default=None, help="Claude Code session ID (prompts to pick if omitted)")
@click.option("--force", is_flag=True, help="Override existing survey response without prompting")
@click.pass_context
def survey_compat(ctx, **kwargs):
    """(Deprecated) Use 'sessions survey' instead."""
    ctx.invoke(survey_cmd, **kwargs)


@cli.command("set-api-key", hidden=True)
@click.argument("provider", type=click.Choice(["anthropic", "openai"]))
@click.option("--name", default="default", help="Key name (e.g. 'default', 'work')")
@click.pass_context
def set_api_key_compat(ctx, **kwargs):
    """(Deprecated) Use 'config set-api-key' instead."""
    ctx.invoke(set_api_key_cmd, **kwargs)


@cli.command("run-script", hidden=True)
@click.argument("script_id", type=click.Choice(["transcript-compact", "llm-time-estimate"]))
@click.option("--session-id", default=None, help="Session ID to run on")
@click.option("--all", "run_all", is_flag=True, help="Run on all sessions missing results")
@click.option("--dry-run", is_flag=True, help="Show what would run without executing")
@click.pass_context
def run_script_compat(ctx, **kwargs):
    """(Deprecated) Use 'sessions run' instead."""
    ctx.invoke(run_cmd, **kwargs)


def _pick_session() -> str | None:
    """Show recent sessions and let the user pick one."""
    from open_uplift.cli.session_picker import pick_session
    from open_uplift.db import get_db

    with get_db() as db:
        total = db.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()["cnt"]
        if total == 0:
            click.echo("No sessions found. Run `open-uplift sync` first.")
            return None
        return pick_session(db)
