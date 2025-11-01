from pathlib import Path

from typer.testing import CliRunner

from memory37.cli import app


runner = CliRunner()


def test_cli_ingest_file_dry_run(tmp_path: Path) -> None:
    yaml_content = """
scenes:
  - id: scn_test
    title: Test Scene
    summary: A short description

npcs:
  - id: npc_test
    name: Test NPC
    archetype: scout

art:
  - id: art_test
    prompt: test prompt
"""
    file_path = tmp_path / "knowledge.yaml"
    file_path.write_text(yaml_content, encoding="utf-8")

    result = runner.invoke(app, ["ingest-file", str(file_path), "--dry-run"])

    assert result.exit_code == 0
    assert "Ingested" in result.stdout


def test_cli_ingest_runtime_snapshot_dry_run(tmp_path: Path) -> None:
    scenes_file = tmp_path / "scenes.yaml"
    scenes_file.write_text(
        """
- scene_id: scn_cli
  campaign_id: cmp_cli
  title: CLI Scene
  summary: Example
""",
        encoding="utf-8",
    )

    npcs_file = tmp_path / "npcs.yaml"
    npcs_file.write_text(
        """
- npc_id: npc_cli
  name: CLI NPC
  archetype: bard
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "ingest-runtime-snapshot",
            f"--scenes-file={scenes_file}",
            f"--npcs-file={npcs_file}",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Ingested" in result.stdout


def test_cli_search_dry_run(tmp_path: Path) -> None:
    yaml_content = """
scenes:
  - id: scn_search
    title: Search Scene
    summary: moon ruins encounter
"""
    file_path = tmp_path / "knowledge.yaml"
    file_path.write_text(yaml_content, encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "search",
            "moon",
            f"--knowledge-file={file_path}",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "scene::scn_search" in result.stdout
