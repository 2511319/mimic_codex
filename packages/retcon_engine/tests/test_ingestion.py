from datetime import datetime

from retcon_engine.ingestion import RetconIngestService
from retcon_engine.models import RetconPackage
from retcon_engine.repository import RetconRepository


def build_package() -> RetconPackage:
    return RetconPackage.model_validate(
        {
            "worldId": "world-1",
            "campaignTemplateId": "tpl-1",
            "campaignRunId": "run-1",
            "seasonVersion": "S1",
            "playerImpact": [
                {
                    "type": "KILL_NPC",
                    "npcId": "npc-1",
                    "partyId": "party-1",
                    "sceneType": "combat",
                    "outcome": "success",
                    "timestamp": datetime.utcnow().isoformat(),
                },
                {
                    "type": "HELP_FACTION",
                    "factionId": "faction-2",
                    "partyId": "party-1",
                    "sceneType": "social",
                    "result": "agreement",
                },
            ],
            "worldDeltas": [],
            "metaStats": {},
        }
    )


def test_ingestion_converts_player_impact_to_world_events() -> None:
    repository = RetconRepository()
    service = RetconIngestService(repository)

    package = build_package()
    events = service.ingest(package)

    assert len(events) == 2
    assert repository.stats(package.world_id)["packages"] == 1
    assert repository.stats(package.world_id)["events"] == 2
    assert any(event.type.value == "KILL_NPC" for event in events)
    assert any(event.targets for event in events)
