from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from .api import get_repository
from .ingestion import RetconIngestService
from .models import CanonPatchDecision, CanonPatchRequest, RetconPackage
from .scheduler import GlobalTickScheduler

app = typer.Typer(help="Retcon Engine CLI")


@app.command()
def ingest_package(path: Path) -> None:
    """Прочитать RetconPackage из файла и сохранить в хранилище."""

    data = json.loads(path.read_text(encoding="utf-8"))
    package = RetconPackage.model_validate(data)
    repo = get_repository()
    service = RetconIngestService(repo)
    events = service.ingest(package)
    typer.echo(f"Ingested package for world {package.world_id}, events={len(events)}")


@app.command()
def global_tick() -> None:
    """Запустить глобальный тик и вывести агрегированные метрики."""

    repo = get_repository()
    scheduler = GlobalTickScheduler(repo)
    snapshot = asyncio.run(scheduler.run_tick())
    typer.echo(f"Tick complete for world {snapshot.world_id} with {len(snapshot.influence.edges)} edges")
    typer.echo(json.dumps(snapshot.model_dump(mode="json"), indent=2, ensure_ascii=False))


@app.command()
def list_candidates() -> None:
    repo = get_repository()
    candidates = repo.list_candidates()
    if not candidates:
        typer.echo("Нет кандидатов")
        raise typer.Exit(code=0)
    for candidate in candidates:
        typer.echo(f"{candidate.candidate_id}: {candidate.target} -> {candidate.change} ({candidate.score})")


@app.command()
def apply_patch(candidate_id: str, applied_by: str, decision: CanonPatchDecision = CanonPatchDecision.ACCEPT) -> None:
    repo = get_repository()
    request = CanonPatchRequest(candidate_id=candidate_id, decision=decision, applied_by=applied_by)
    patch = repo.apply_patch(
        candidate_id=request.candidate_id,
        decision=request.decision,
        applied_by=request.applied_by,
    )
    typer.echo(json.dumps(patch.model_dump(mode="json"), indent=2, ensure_ascii=False))


def main() -> None:  # pragma: no cover - CLI entry
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
