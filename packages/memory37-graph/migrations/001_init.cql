// Constraints and basic indexes
CREATE CONSTRAINT IF NOT EXISTS FOR (n:KnowledgeRoot) REQUIRE n.version_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Location) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:NPC) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Faction) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Quest) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Item) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Event) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Concept) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Episode) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Party) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE;
