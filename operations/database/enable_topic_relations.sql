-- Undirected related-topic edges, independent of course directory placements.
CREATE TABLE IF NOT EXISTS topic_relations (
    topic_a_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE CASCADE,
    topic_b_id TEXT NOT NULL REFERENCES curriculum_topics(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'related' CHECK (relation_type = 'related'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (topic_a_id, topic_b_id, relation_type),
    CHECK (topic_a_id < topic_b_id)
);
CREATE INDEX IF NOT EXISTS idx_topic_relations_b ON topic_relations(topic_b_id);
