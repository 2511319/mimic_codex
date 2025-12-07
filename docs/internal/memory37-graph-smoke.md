# Memory37 GraphRAG — smoke с Neo4j

1. Поднимите Neo4j (пример docker-compose в `packages/memory37-graph/README.md`).
2. Экспортируйте переменные:
   ```
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=password
   ```
3. Запустите скрипт:
   ```
   python packages/memory37-graph/examples/neo4j_smoke.py
   ```
   Ожидаемый вывод: summary вида `X nodes, Y relations...`, `Degraded: False`.
4. Для очистки TTL добавьте в Neo4j APOC-джобы (см. README TTL-раздел).
5. Для gateway: выставьте NEO4J_* и вызовите `/v1/graph/scene?scene_id=quest::moon` — должно вернуть nodes/relations из графа.
