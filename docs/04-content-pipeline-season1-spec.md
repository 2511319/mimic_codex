# RPG-Bot — Контент и лор первого сезона  
## 04. Content Pipeline: Season 1

## 1. Цель

Определить формат контент-паков и пайплайн, по которому:

- креативная команда создаёт/редактирует лор и кампании;
- данные попадают в репозиторий (`content/`);
- CLI-инструмент импортирует их в БД и Memory37;
- Campaign Engine и Retcon Engine опираются на эти данные.

## 2. Директория и организация контента

Базовый корень: `content/`

Структура Season 1:

- `content/worlds/<world_id>/world.yaml`
- `content/worlds/<world_id>/regions/*.yaml`
- `content/worlds/<world_id>/cities/*.yaml`
- `content/factions/*.yaml`
- `content/npcs/*.yaml`
- `content/bestiary/*.yaml`
- `content/items/*.yaml`
- `content/campaigns/<campaign_id>/*.yaml`
- `content/scenes_templates/*.yaml` (опционально — блоки сцен)

`<world_id>` и `<campaign_id>` — стабильные строковые id.

## 3. Примеры YAML-структур (high-level)

### 3.1. World

```yaml
id: world_ashen_moon
title: "Мир Под Блеклой Луной"
season_version: "S1-v0.1"
description: |
  Краткое описание мира...
factions:
  - ref: faction_empire
  - ref: faction_rebels
regions:
  - ref: region_north
  - ref: region_south
3.2. NPC
yaml
Копировать код
id: npc_uniq_mystic_zora
world_id: world_ashen_moon
name: "Мадам Зора"
role: "fortune_teller"
factions:
  - faction_independent
tags:
  - "mystic"
  - "oracle"
base_profile:
  personality: ...
  appearance: ...
  motivations: ...
3.3. Monster (Bestiary)
yaml
Копировать код
id: monster_blood_wolf
world_id: world_ashen_moon
name: "Кровавый волк"
cr: 2
stats:
  hp: 32
  ac: 14
  attack_bonus: +4
  damage: "1d8+2"
behaviour_tags:
  - "pack_hunter"
  - "bloodthirsty"
lore_snippet: |
  Слухи о кровавых волках...
3.4. Item
yaml
Копировать код
id: item_cursed_amulet
world_id: world_ashen_moon
name: "Проклятый амулет"
rarity: "rare"
slot: "neck"
effects:
  - type: "buff"
    stat: "wisdom"
    value: +1
  - type: "curse"
    description: "Периодические видения ужаса"
3.5. Campaign
yaml
Копировать код
id: campaign_ashen_moon_prologue
world_id: world_ashen_moon
title: "Пролог Блеклой Луны"
season_version: "S1-v0.1"
episodes:
  - ref: episode_01_city_intro
  - ref: episode_02_catacombs
  - ref: episode_03_finale
Каждый episode_*.yaml описывает:

стартовые условия,

ключевые сцены (явно или через ссылку на scene-template),

важные флаги и условия переходов.

4. CLI-импортёр rpg-content
4.1. Задача
Инструмент командной строки, который:

валидирует YAML-файлы по схемам;

импортирует данные в:

Postgres (таблицы worlds, regions, cities, factions, npcs, monsters, items, campaign_templates, episodes, и др.);

Memory37 (lore_canon домен).

4.2. Команды
rpg-content validate
— проверить все YAML на соответствие схемам.

rpg-content import worlds
— импортировать content/worlds/**.

rpg-content import bestiary
— импортировать content/bestiary/**.

rpg-content import items
— импортировать content/items/**.

rpg-content import campaigns --id <campaign_id>
— импортировать только указанную кампанию.

4.3. Поведение при ошибках
При валидации:

показывать конкретные ошибки по файлам/полям;

При импорте:

не частично ломать мир — либо “всё ок по кампании”, либо откат;

логировать версии импортов.

5. Версионирование контента
Каждый YAML-файл имеет поле season_version.

Импортёр не должен безусловно перетирать данные:

хранить историю версий (минимум — timestamp версии);

связывать world_version в L0 с импортированными версиями.

Для OBT достаточно:

жёстко закрепить Season 1 как S1-v0.1;

предусмотреть флаг “breaking change” для последующих обновлений.

6. Интеграция с Campaign Engine и Retcon Engine
Campaign Engine использует импортированные кампании/эпизоды как основу:

какие NPC и локации вовлечены;

какие флаги возможны.

Retcon Engine опирается на id-шники из контент-паков при построении:

InfluenceGraph (узлы и связи),

кандидатов в изменения канона.

7. Definition of Done
В репозитории есть content/ с демо-структурой Season 1.

Определены YAML-схемы и реализован CLI-инструмент rpg-content.

Импортёр валидирует и импортирует лор в Postgres и Memory37.

Campaign Engine может создать CampaignRun на основе импортированного шаблона.

Есть базовый набор тестов контент-импорта.