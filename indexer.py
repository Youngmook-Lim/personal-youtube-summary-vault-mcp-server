import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import struct

import frontmatter
import git
import tiktoken

import config
import embeddings
from db import get_connection, init_db

def pull_repo() -> None:
    repo = git.Repo(config.OBSIDIAN_REPO_PATH)
    repo.remotes.origin.pull()
    print("Pulled latest commits.")


def parse_file(file_path: Path) -> dict:
    raw = file_path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)

    file_hash = hashlib.sha256(raw.encode()).hexdigest()

    title_match = re.search(r"^# (.+)$", post.content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else file_path.stem

    return {
        "file_path": str(file_path.relative_to(config.OBSIDIAN_REPO_PATH)),
        "file_hash": file_hash,
        "title": title,
        "channel": post.metadata.get("author"),
        "url": post.metadata.get("source"),
        "published_at": str(post.metadata.get("date", "")),
        "frontmatter_json": json.dumps(post.metadata, default=str),
        "summary_md": post.content,
        "tags": post.metadata.get("tags", []),
    }

def chunk_text(text: str) -> list[str]:
    enc = tiktoken.get_encoding("cl100k_base")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = len(enc.encode(para))

        if current_tokens + para_tokens > config.CHUNK_SIZE_TOKENS and current:
            chunks.append("\n\n".join(current))
            current = current[-1:]
            current_tokens = len(enc.encode(current[0])) if current else 0

        current.append(para)
        current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def ingest_file(conn, parsed: dict) -> str:
    now = datetime.now(timezone.utc).isoformat()

    existing = conn.execute(
        "SELECT id, file_hash FROM videos WHERE file_path = ?",
        (parsed["file_path"],)
    ).fetchone()

    if existing and existing["file_hash"] == parsed["file_hash"]:
        return "skipped"

    if existing:
        video_id = existing["id"]
        conn.execute("DELETE FROM chunks WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM tags WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM fts_content WHERE video_id = ?", (video_id,))
        conn.execute("UPDATE videos SET file_hash=?, title=?, channel=?, url=?, published_at=?, ingested_at=?, frontmatter_json=?, summary_md=? WHERE id=?",
            (parsed["file_hash"], parsed["title"], parsed["channel"], parsed["url"],
             parsed["published_at"], now, parsed["frontmatter_json"], parsed["summary_md"], video_id))
        status = "updated"
    else:
        cursor = conn.execute(
            "INSERT INTO videos (file_path, file_hash, title, channel, url, published_at, ingested_at, frontmatter_json, summary_md) VALUES (?,?,?,?,?,?,?,?,?)",
            (parsed["file_path"], parsed["file_hash"], parsed["title"], parsed["channel"],
             parsed["url"], parsed["published_at"], now, parsed["frontmatter_json"], parsed["summary_md"])
        )
        video_id = cursor.lastrowid
        status = "added"

    for tag in parsed["tags"]:
        conn.execute("INSERT OR IGNORE INTO tags (video_id, tag) VALUES (?,?)", (video_id, tag))

    chunks = chunk_text(parsed["summary_md"])
    vectors = embeddings.embed(chunks)

    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        cursor = conn.execute(
            "INSERT INTO chunks (video_id, chunk_index, content) VALUES (?,?,?)",
            (video_id, i, chunk)
        )
        chunk_id = cursor.lastrowid

        conn.execute(
            "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?,?)",
            (chunk_id, _serialize(vector))
        )
        conn.execute(
            "INSERT INTO fts_content (content, video_id, chunk_id, content_type) VALUES (?,?,?,?)",
            (chunk, video_id, chunk_id, "chunk")
        )

    return status


def _serialize(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def reindex_library() -> dict:
    pull_repo()
    init_db()
    conn = get_connection()

    md_files = []
    for folder in config.VIDEOS_FOLDERS:
        md_files.extend(folder.rglob("*.md"))

    counts = {"added": 0, "updated": 0, "skipped": 0}

    for file_path in md_files:
        try:
            parsed = parse_file(file_path)
            conn.execute("SAVEPOINT ingest")
            status = ingest_file(conn, parsed)
            conn.execute("RELEASE SAVEPOINT ingest")
            counts[status] += 1
            print(f"[{status}] {parsed['title']}")
        except Exception as e:
            conn.execute("ROLLBACK TO SAVEPOINT ingest")
            print(f"[error] {file_path.name}: {e}")

    conn.commit()
    conn.close()
    print(f"\nDone. {counts}")
    return counts


if __name__ == "__main__":
    reindex_library()