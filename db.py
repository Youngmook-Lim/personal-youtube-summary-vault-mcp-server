import sqlite3
import sqlite_vec
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "library.db"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS videos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path       TEXT NOT NULL UNIQUE,
            file_hash       TEXT NOT NULL,
            title           TEXT,
            channel         TEXT,
            url             TEXT,
            ingested_at     TEXT NOT NULL,
            frontmatter_json TEXT,
            summary_md      TEXT
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id        INTEGER NOT NULL REFERENCES videos(id),
            chunk_index     INTEGER NOT NULL,
            content         TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tags (
            video_id        INTEGER NOT NULL REFERENCES videos(id),
            tag             TEXT NOT NULL,
            PRIMARY KEY (video_id, tag)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS fts_content USING fts5(
            content,
            video_id UNINDEXED,
            chunk_id UNINDEXED,
            content_type UNINDEXED
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
            chunk_id INTEGER PRIMARY KEY,
            embedding FLOAT[1536]
        );
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")