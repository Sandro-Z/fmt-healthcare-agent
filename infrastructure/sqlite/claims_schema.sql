CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    knowledge_version TEXT NOT NULL,
    parser_score REAL,
    human_verified INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claim_subject ON claims(subject_id);
CREATE INDEX IF NOT EXISTS idx_claim_object ON claims(object_id);
CREATE INDEX IF NOT EXISTS idx_claim_version ON claims(knowledge_version);

