from datetime import datetime, timedelta

import pytest

from retcon_engine.models import RetconPackage
from retcon_engine.repository import RetconRepository
from retcon_engine.scheduler import GlobalTickScheduler


@pytest.mark.asyncio
async def test_global_tick_builds_snapshot_and_candidates() -> None:
    repository = RetconRepository()
    scheduler = GlobalTickScheduler(repository, tick_period=timedelta(days=1))

    package = RetconPackage.model_validate(
        {
            "worldId": "world-1",
            "campaignTemplateId": "tpl-1",
            "campaignRunId": "run-1",
            "seasonVersion": "S1",
            "playerImpact": [],
            "worldDeltas": [
                {"entityType": "npc", "entityId": "npc-1", "change": "dead"},
                {"entityType": "npc", "entityId": "npc-1", "change": "dead"},
                {"entityType": "faction", "entityId": "f-1", "change": "lost"},
                {"entityType": "faction", "entityId": "f-1", "change": "lost"},
            ],
            "metaStats": {"choiceA": 3},
            "received_at": datetime.utcnow().isoformat(),
        }
    )
    repository.store_package(package, events=[])

    snapshot = await scheduler.run_tick(now=datetime.utcnow())

    assert snapshot.world_id == "world-1"
    assert snapshot.choice_stats["choiceA"] == 3
    assert any(candidate.target == "npc-1" for candidate in snapshot.candidates)
    assert snapshot.influence.edges
