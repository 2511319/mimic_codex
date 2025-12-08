"""JSON Schema validation for party_sync events."""

from __future__ import annotations

from jsonschema import Draft7Validator

from .models import BroadcastMessage


SCHEMAS = {
    "system": {
        "type": "object",
        "required": ["eventType", "payload"],
        "properties": {
            "eventType": {"type": "string", "pattern": "^system\\."},
            "payload": {"type": "object"},
        },
    },
    "party": {
        "type": "object",
        "required": ["eventType", "payload"],
        "properties": {
            "eventType": {"type": "string", "pattern": "^party\\."},
            "payload": {
                "type": "object",
                "required": ["partyId"],
                "properties": {
                    "partyId": {"type": ["string", "number"]},
                    "status": {"type": "string"},
                    "memberId": {"type": ["string", "number"]},
                },
            },
        },
    },
    "vote": {
        "type": "object",
        "required": ["eventType", "payload"],
        "properties": {
            "eventType": {"type": "string", "pattern": "^vote\\."},
            "payload": {
                "type": "object",
                "required": ["optionId", "tally"],
                "properties": {
                    "optionId": {"type": ["string", "number"]},
                    "tally": {"type": ["number", "integer"]},
                },
            },
        },
    },
    "action": {
        "type": "object",
        "required": ["eventType", "payload", "actionId"],
        "properties": {
            "eventType": {"type": "string", "pattern": "^action\\."},
            "actionId": {"type": "string", "minLength": 1},
            "payload": {
                "type": "object",
                "required": ["action"],
                "properties": {
                    "action": {"type": "object"},
                    "runId": {"type": "string"},
                    "sceneId": {"type": "string"},
                    "actorId": {"type": ["string", "number"]},
                },
            },
        },
    },
    "scene.update": {
        "type": "object",
        "required": ["eventType", "payload"],
        "properties": {
            "eventType": {"const": "scene.update"},
            "payload": {
                "type": "object",
                "required": ["sceneId", "phase"],
                "properties": {
                    "sceneId": {"type": "string"},
                    "phase": {"type": "string"},
                    "status": {"type": "string"},
                    "outcome": {"type": "object"},
                },
            },
        },
    },
    "combat.update": {
        "type": "object",
        "required": ["eventType", "payload"],
        "properties": {
            "eventType": {"const": "combat.update"},
            "payload": {
                "type": "object",
                "required": ["sceneId", "phase"],
                "properties": {
                    "sceneId": {"type": "string"},
                    "phase": {"type": "string"},
                    "effects": {"type": "array"},
                    "outcome": {"type": "object"},
                },
            },
        },
    },
}

GENERIC_SCHEMA = {
    "type": "object",
    "required": ["eventType", "payload"],
    "properties": {
        "eventType": {"type": "string"},
        "payload": {"type": "object"},
    },
}


def _select_schema(event_type: str) -> dict:
    if event_type.startswith("system."):
        return SCHEMAS["system"]
    if event_type.startswith("party."):
        return SCHEMAS["party"]
    if event_type.startswith("action."):
        return SCHEMAS["action"]
    if event_type.startswith("vote."):
        return SCHEMAS["vote"]
    if event_type == "scene.update":
        return SCHEMAS["scene.update"]
    if event_type == "combat.update":
        return SCHEMAS["combat.update"]
    return GENERIC_SCHEMA


def validate_event_envelope(message: BroadcastMessage) -> None:
    """Validate event envelope with JSON Schema based on event type."""

    schema = _select_schema(message.event_type)
    validator = Draft7Validator(schema)
    instance = message.model_dump(by_alias=True)
    validator.validate(instance)
