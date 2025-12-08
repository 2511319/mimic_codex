"""Упрощённый Campaign Engine для OBT-1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, Protocol

import yaml

from rpg_gateway_api.data import (
    AdventureSummaryRecord,
    CampaignRunRecord,
    CampaignTemplateRecord,
    DataStoreProtocol,
    EpisodeRecord,
    NotFoundError,
    SceneStateRecord,
)
from rpg_gateway_api.generation import GenerationService


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class SceneSpec:
    id: str
    title: str
    summary: str
    timeline: List[str] = field(default_factory=list)
    scene_type: str = "story"


@dataclass
class TemplateSpec:
    record: CampaignTemplateRecord
    episode: EpisodeRecord
    scenes: List[SceneSpec]

class Notifier(Protocol):
    def broadcast(self, campaign_id: str, event_type: str, payload: dict[str, Any], trace_id: str | None = None) -> None: ...


class CampaignEngine:
    """Минимальная реализация стейт-машины кампании под Wave OBT-1."""

    def __init__(
        self,
        store: DataStoreProtocol,
        generation_service: GenerationService | None = None,
        templates_path: Path | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self._store = store
        self._generation = generation_service
        self._templates = self._load_templates(templates_path or Path("data/knowledge/campaigns"))
        self._phase_init = "INIT"
        self._phase_scene = "SCENE"
        self._phase_resolve = "RESOLVE"
        self._phase_apply = "APPLY_EFFECTS"
        self._phase_completed = "COMPLETED"
        self._notifier = notifier
        self._allowed_action_statuses = {self._phase_scene, "IN_PROGRESS"}

    class InvalidPhaseError(Exception):
        """Действие не разрешено в текущей фазе."""

    def _load_templates(self, path: Path) -> dict[str, TemplateSpec]:
        templates: dict[str, TemplateSpec] = {}
        if not path.exists():
            return templates
        for file_path in path.glob("*.yaml"):
            with file_path.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            template_id = file_path.stem
            scenes = []
            for idx, raw_scene in enumerate(raw.get("scenes", []), start=1):
                tags = raw_scene.get("tags") or []
                scene_type = self._infer_scene_type(tags=tags, is_last=False)
                scenes.append(
                    SceneSpec(
                        id=raw_scene.get("id") or f"{template_id}_scene_{idx}",
                        title=raw_scene.get("title") or f"Scene {idx}",
                        summary=raw_scene.get("summary") or "",
                        timeline=raw_scene.get("timeline", []),
                        scene_type=scene_type,
                    )
                )
            description = raw.get("description") or (scenes[0].summary if scenes else "")
            template_record = CampaignTemplateRecord(
                id=template_id,
                title=raw.get("title") or template_id.replace("_", " ").title(),
                description=description,
                season_version=raw.get("season_version") or "S1-v0.1",
                metadata={"source": str(file_path)},
            )
            episode = EpisodeRecord(
                id=f"{template_id}-episode-main",
                campaign_template_id=template_id,
                order=1,
                type="main",
                metadata={"scene_count": len(scenes)},
            )
            self._store.upsert_campaign_template(template_record)
            self._store.upsert_episode(episode)
            # Обновляем тип последней сцены как epilogue при отсутствии явного признака
            if scenes:
                last_scene = scenes[-1]
                if last_scene.scene_type == "story":
                    last_scene.scene_type = "epilogue"
            templates[template_id] = TemplateSpec(record=template_record, episode=episode, scenes=scenes)
        return templates

    def _infer_scene_type(self, *, tags: list[str], is_last: bool) -> str:
        lowered = [t.lower() for t in tags]
        if "combat" in lowered:
            return "combat"
        if "social" in lowered or "dialogue" in lowered or "intrigue" in lowered or "heist" in lowered:
            return "social"
        if "epilogue" in lowered or is_last:
            return "epilogue"
        return "story"

    def list_templates(self) -> List[CampaignTemplateRecord]:
        try:
            return self._store.list_campaign_templates()  # type: ignore[call-arg]
        except AttributeError:
            return list(self._store.campaign_templates.values())  # type: ignore[attr-defined]

    def start_run(self, *, template_id: str, party_id: int, character_ids: List[int]) -> Tuple[CampaignRunRecord, SceneStateRecord]:
        template = self._templates.get(template_id)
        if not template:
            raise NotFoundError(f"CampaignTemplate {template_id} not found")
        run = self._store.start_campaign_run(
            campaign_template_id=template_id,
            party_id=party_id,
            current_episode_id=template.episode.id,
            status=self._phase_init,
        )
        for character_id in character_ids:
            self._store.add_character_to_run(character_id=character_id, run_id=run.id, role="MAIN")
        first_scene = self._create_scene_state(run, template, order=1)
        self._store.update_campaign_run(
            run.id,
            current_scene_id=first_scene.id,
            status=self._phase_scene,
        )
        self._notify(
            run.id,
            "campaign.scene_started",
            {"sceneId": first_scene.id, "phase": self._phase_scene, "status": self._phase_scene},
        )
        return run, first_scene

    def get_state(self, run_id: str) -> Tuple[CampaignRunRecord, SceneStateRecord | None]:
        run = self._store.get_campaign_run(run_id)
        current_scene = None
        if run.current_scene_id:
            try:
                current_scene = self._store.get_scene_state(run.current_scene_id)  # type: ignore[attr-defined]
            except Exception:
                current_scene = None
        return run, current_scene

    def apply_action(self, *, run_id: str, action: dict[str, Any]) -> Tuple[CampaignRunRecord, SceneStateRecord | None]:
        run = self._store.get_campaign_run(run_id)
        if run.status not in self._allowed_action_statuses:
            raise self.InvalidPhaseError(f"Run {run_id} not in actionable phase: {run.status}")
        template = self._templates.get(run.campaign_template_id)
        if not template:
            raise NotFoundError(f"CampaignTemplate {run.campaign_template_id} not found")
        current_scene = None
        if run.current_scene_id:
            try:
                current_scene = self._store.get_scene_state(run.current_scene_id)  # type: ignore[attr-defined]
            except Exception:
                current_scene = None
        if not current_scene:
            raise NotFoundError("No active scene")

        participants = self._list_participants(run.id)
        outcome = self._resolve_outcome(current_scene.scene_type, action, participants)
        flags = {
            "action": action,
            "sceneType": current_scene.scene_type,
            "phase": self._phase_resolve,
            "outcome": outcome,
            "effects": outcome.get("effects", []),
        }
        self._store.update_campaign_run(run.id, status=self._phase_resolve)
        self._store.resolve_scene(current_scene.id, flags)
        self._store.add_flag(
            campaign_run_id=run.id,
            key=f"scene_{current_scene.scene_order}_action",
            value=action,
            source_scene_id=current_scene.id,
        )
        self._record_character_events(
            run.id,
            action,
            importance=self._importance_for_scene(current_scene.scene_type),
            result_flags=flags,
        )
        self._store.update_campaign_run(run.id, status=self._phase_apply)
        self._apply_effects(run.id, outcome)
        self._notify(
            run.id,
            "campaign.phase_applied",
            {"sceneId": current_scene.id, "phase": self._phase_apply, "outcome": outcome},
            status=self._phase_apply,
        )

        next_order = current_scene.scene_order + 1
        if next_order > len(template.scenes):
            self._store.update_campaign_run(
                run.id,
                status=self._phase_completed,
                current_scene_id=None,
                finished_at=_utcnow(),
            )
            summary = self._build_summary(run, template)
            self._store.store_adventure_summary(
                campaign_run_id=run.id,
                summary=summary,
                retcon_package=self._build_retcon_package(run, template, summary),
            )
            self._record_character_events(
                run.id,
                {"type": "campaign_completed"},
                importance="MACRO",
                result_flags={"phase": self._phase_completed},
            )
            self._notify(run.id, "campaign.completed", {"summary": summary}, status=self._phase_completed)
            return self._store.get_campaign_run(run.id), None

        next_scene = self._create_scene_state(run, template, order=next_order)
        self._store.update_campaign_run(run.id, current_scene_id=next_scene.id, status=self._phase_scene)
        self._notify(
            run.id,
            "campaign.scene_started",
            {"sceneId": next_scene.id, "phase": self._phase_scene},
            status=self._phase_scene,
        )
        return self._store.get_campaign_run(run.id), next_scene

    def _create_scene_state(self, run: CampaignRunRecord, template: TemplateSpec, order: int) -> SceneStateRecord:
        try:
            scene_spec = template.scenes[order - 1]
        except IndexError as exc:
            raise NotFoundError(f"Scene order {order} not found for template {template.record.id}") from exc
        payload = self._generate_scene_payload(scene_spec, run)
        return self._store.record_scene_state(
            campaign_run_id=run.id,
            episode_id=template.episode.id,
            scene_order=order,
            scene_type=scene_spec.scene_type,
            profile="scene.v1",
            input_context={"templateId": template.record.id, "order": order},
            generated_payload=payload,
            resolved=False,
            result_flags={},
        )

    def _generate_scene_payload(self, scene_spec: SceneSpec, run: CampaignRunRecord) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": scene_spec.title,
            "summary": scene_spec.summary,
            "timeline": scene_spec.timeline,
            "sceneType": scene_spec.scene_type,
            "campaignRunId": run.id,
            "phase": self._phase_scene,
        }
        if self._generation and self._generation.available:
            prompt = f"Campaign {run.campaign_template_id} scene seed: {scene_spec.title}. {scene_spec.summary}"
            try:
                payload["generated"] = self._generation.generate("scene.v1", prompt)
            except Exception:
                payload["generated"] = {}
        # базовый auto-resolution для combat/social пока заглушка
        if scene_spec.scene_type == "combat":
            payload.setdefault("autoResolution", {"result": "victory", "notes": "auto-resolved", "checks": [{"type": "attack", "roll": 15, "dc": 10}]})
        elif scene_spec.scene_type == "social":
            payload.setdefault("autoResolution", {"result": "agreement", "notes": "auto-resolved", "checks": [{"type": "persuasion", "roll": 14, "dc": 12}]})
        return payload

    def _build_summary(self, run: CampaignRunRecord, template: TemplateSpec) -> dict[str, Any]:
        scenes = sorted(self._store.list_scenes_for_run(run.id), key=lambda s: s.scene_order)
        timeline = []
        for scene in scenes:
            entry = {
                "sceneId": scene.id,
                "order": scene.scene_order,
                "title": scene.generated_payload.get("title"),
                "summary": scene.generated_payload.get("summary"),
                "resultFlags": scene.result_flags,
                "sceneType": scene.scene_type,
                "phase": scene.result_flags.get("phase", self._phase_scene),
                "outcome": scene.result_flags.get("outcome"),
                "effects": scene.result_flags.get("effects"),
                "checks": scene.result_flags.get("outcome", {}).get("checks"),
            }
            timeline.append(entry)
        return {
            "campaignRunId": run.id,
            "campaignTemplateId": run.campaign_template_id,
            "partyId": run.party_id,
            "timeline": timeline,
            "rewards": [],
            "worldLocalEffects": [],
        }

    def _build_retcon_package(
        self,
        run: CampaignRunRecord,
        template: TemplateSpec,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "worldId": template.record.metadata.get("world_id") or "default-world",
            "campaignTemplateId": template.record.id,
            "campaignRunId": run.id,
            "seasonVersion": template.record.season_version,
            "worldDeltas": [],
            "playerImpact": summary.get("timeline", []),
            "metaStats": {},
        }

    def get_summary(self, run_id: str) -> AdventureSummaryRecord:
        return self._store.get_adventure_summary(run_id)

    def _record_character_events(self, run_id: str, action: dict[str, Any], importance: str, result_flags: dict[str, Any] | None = None) -> None:
        try:
            participants = self._store.list_characters_in_run(run_id)  # type: ignore[attr-defined]
        except Exception:
            participants = []
        payload = {
            "action": action,
            "outcome": (result_flags or {}).get("outcome") or action.get("outcome"),
            "effects": (result_flags or {}).get("effects"),
            "phase": (result_flags or {}).get("phase"),
            "checks": ((result_flags or {}).get("outcome") or {}).get("checks"),
        }
        for participant in participants:
            self._store.record_event(
                character_id=participant.character_id,
                party_id=None,
                campaign_run_id=run_id,
                world_event_type=action.get("type", "ACTION"),
                importance=importance,
                payload=payload,
            )

    def _importance_for_scene(self, scene_type: str) -> str:
        scene_type = (scene_type or "").lower()
        if scene_type in {"combat", "social"}:
            return "MESO"
        if scene_type == "epilogue":
            return "MACRO"
        return "MICRO"

    def _resolve_outcome(self, scene_type: str, action: dict[str, Any], participants: list) -> dict[str, Any]:
        scene_type = (scene_type or "").lower()
        if scene_type == "combat":
            effects = [
                {"hpDelta": -2, "targetCharacterId": p.character_id, "statChanges": {"hp": -2}}
                for p in participants
            ] or [{"hpDelta": -2, "statChanges": {"hp": -2}}]
            return {
                "result": "success",
                "checks": [{"type": "attack", "roll": 15, "dc": 10}],
                "effects": effects,
            }
        if scene_type == "social":
            effects = [
                {"relationDelta": 1, "targetCharacterId": p.character_id, "statChanges": {"relation": 1}}
                for p in participants
            ] or [{"relationDelta": 1, "statChanges": {"relation": 1}}]
            return {
                "result": "agreement",
                "checks": [{"type": "persuasion", "roll": 14, "dc": 12}],
                "effects": effects,
            }
        if scene_type == "epilogue":
            return {"result": "epilogue", "summary": "run completed"}
        effects = [
            {"hpDelta": -1, "targetCharacterId": p.character_id, "statChanges": {"hp": -1}}
            for p in participants
        ] or [{"hpDelta": -1, "statChanges": {"hp": -1}}]
        return {
            "result": "ok",
            "notes": "auto-resolve",
            "effects": effects,
            "checks": action.get("checks") or [],
        }

    def _apply_effects(self, run_id: str, outcome: dict[str, Any]) -> None:
        effects = outcome.get("effects") or []
        if not effects:
            return
        participants = self._list_participants(run_id)
        targets = {p.character_id: p for p in participants}
        for effect in effects:
            target_id = effect.get("targetCharacterId")
            hp_delta = effect.get("hpDelta")
            relation_delta = effect.get("relationDelta")
            if hp_delta is not None:
                target_ids = [target_id] if target_id else list(targets.keys()) or []
                for tid in target_ids:
                    try:
                        char = self._store.get_character(tid)  # type: ignore[attr-defined]
                    except Exception:
                        continue
                    stats = dict(char.core_stats)
                    hp_current = int(stats.get("hp", 10))
                    stats["hp"] = max(0, hp_current + hp_delta)
                    self._store.update_character(tid, core_stats=stats)  # type: ignore[attr-defined]
            stat_changes = effect.get("statChanges") or {}
            if relation_delta is not None:
                stat_changes = {**stat_changes, "relation": stat_changes.get("relation", 0) + relation_delta}
            if stat_changes and target_id:
                try:
                    char = self._store.get_character(target_id)  # type: ignore[attr-defined]
                except Exception:
                    continue
                stats = dict(char.core_stats)
                for key, delta in stat_changes.items():
                    try:
                        current = float(stats.get(key, 0))
                    except Exception:
                        current = 0
                    try:
                        stats[key] = current + delta
                    except Exception:
                        stats[key] = delta
                self._store.update_character(target_id, core_stats=stats)  # type: ignore[attr-defined]

    def _notify(
        self,
        campaign_id: str,
        event_type: str,
        payload: dict[str, Any],
        status: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        if not self._notifier:
            return
        enriched = {"campaignId": campaign_id, **payload}
        if status:
            enriched.setdefault("status", status)
        try:
            self._notifier.broadcast(campaign_id, event_type, enriched, trace_id=trace_id)
        except Exception:
            # best-effort, без падения основной логики
            return

    def _list_participants(self, run_id: str):
        try:
            return self._store.list_characters_in_run(run_id)  # type: ignore[attr-defined]
        except Exception:
            return []
