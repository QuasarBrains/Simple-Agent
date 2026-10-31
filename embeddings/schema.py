# Shared by any application module that persists embedded content.
EMBEDDING_SCHEMA = (
    """CREATE TABLE embedding_profiles (
        id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
        profile_json TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
)
