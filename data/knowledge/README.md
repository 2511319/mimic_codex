# Knowledge YAML format

Single-file campaign pack used by Memory37 ingest (dev/staging). Minimum sections:

- `scenes[]`: `{ id, title, summary, tags[], timeline[] }`
- `npcs[]`: `{ id, name, archetype, summary, voice_tts? }`
- `art[]`: `{ id, prompt, tags[], entities?{ npc?:[], location?:[] } }`
- `lore[]`: `{ id, title, body, tags[], related?{ scene?, npc? } }`

ID conventions used to build `item_id`:

- Scene → `scene::<scene_id>`
- NPC → `npc::<npc_id>`
- Art → `art::<image_id>`
- Lore → `lore::<lore_id>`

Ingestion converts entries to flat `KnowledgeItem` content and string metadata:

- Scenes → `content` includes title, summary, timeline; `metadata.tags` is comma-joined tags.
- NPCs → `content` includes name, archetype, summary; `metadata.voice_tts` when provided.
- Art → `content` includes prompt and flattened entities; `metadata.image_id`, `metadata.tags`.
- Lore → `content = "<title>: <body>"`; `metadata.tags` is comma-joined; optional `metadata.related` as `"scene:<id>,npc:<id>"`.

Dry-run validation:

```
python -m memory37.cli ingest-file data/knowledge/campaigns/ashen_moon_arc.yaml --dry-run
```

