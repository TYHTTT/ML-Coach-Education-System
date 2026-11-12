CREATE TABLE IF NOT EXISTS administrators (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    session_token_hash TEXT UNIQUE,
    session_expires_at TEXT,
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    CHECK ((session_token_hash IS NULL) = (session_expires_at IS NULL))
);
