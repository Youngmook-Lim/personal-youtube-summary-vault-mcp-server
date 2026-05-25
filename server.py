import struct
from datetime import datetime, timezone, timedelta

from mcp.server.fastmcp import FastMCP

import config
import embeddings
import indexer as _indexer
from db import get_connection

mcp = FastMCP("Video Library")

def _serialize(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


# TOOLS
@mcp.tool()
def reindex_library() -> str:
    """Pull latest commits and re-index new or changed video summaries."""
    counts = _indexer.reindex_library()
    return f"Done. Added: {counts['added']}, Updated: {counts['updated']}, Skipped: {counts['skipped']}"


@mcp.tool()
def get_video(video_id: int) -> str:
    """Get the full summary for a specific video by its ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    if not row:
        return f"No video found with id {video_id}."
    return (
        f"# {row['title']}\n\n"
        f"**Channel:** {row['channel']}\n"
        f"**URL:** {row['url']}\n"
        f"**Published:** {row['published_at']}\n\n"
        f"{row['summary_md']}"
    )


@mcp.tool()
def list_recent(days: int = 14) -> str:
    """List videos ingested in the last N days."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, title, channel, published_at
        FROM videos
        WHERE ingested_at >= datetime('now', ?)
        ORDER BY ingested_at DESC
    """, (f"-{days} days",)).fetchall()
    conn.close()
    if not rows:
        return f"No videos ingested in the last {days} days."
    lines = [f"- [{r['id']}] **{r['title']}** — {r['channel']} ({r['published_at']})" for r in rows]
    return "\n".join(lines)


@mcp.tool()
def suggest_forgotten(min_age_days: int = 30) -> str:
    """Suggest videos that were ingested a while ago — good for revisiting."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, title, channel, published_at
        FROM videos
        WHERE ingested_at <= datetime('now', ?)
        ORDER BY RANDOM()
        LIMIT 5
    """, (f"-{min_age_days} days",)).fetchall()
    conn.close()
    if not rows:
        return "No forgotten videos found."
    lines = [f"- [{r['id']}] **{r['title']}** — {r['channel']}" for r in rows]
    return "Videos you haven't revisited in a while:\n" + "\n".join(lines)


@mcp.tool()
def search_videos(query: str, semantic: bool = True, limit: int = 5) -> str:
    """Search video summaries by keyword or semantic similarity."""
    conn = get_connection()
    seen_ids = set()
    results = []

    if semantic:
        query_vector = embeddings.embed([query])[0]
        rows = conn.execute("""
            SELECT vc.chunk_id, vc.distance, c.video_id
            FROM vec_chunks vc
            JOIN chunks c ON vc.chunk_id = c.id
            WHERE vc.embedding MATCH ?
            ORDER BY vc.distance
            LIMIT ?
        """, (_serialize(query_vector), limit * 3)).fetchall()

        for row in rows:
            if row["video_id"] not in seen_ids:
                seen_ids.add(row["video_id"])
                video = conn.execute(
                    "SELECT id, title, channel, url FROM videos WHERE id = ?",
                    (row["video_id"],)
                ).fetchone()
                results.append(video)
                if len(results) >= limit:
                    break

    fts_rows = conn.execute("""
        SELECT DISTINCT v.id, v.title, v.channel, v.url
        FROM fts_content f
        JOIN videos v ON f.video_id = v.id
        WHERE fts_content MATCH ?
        LIMIT ?
    """, (query, limit)).fetchall()

    for row in fts_rows:
        if row["id"] not in seen_ids:
            seen_ids.add(row["id"])
            results.append(row)

    conn.close()
    if not results:
        return "No videos found."
    lines = [f"- [{v['id']}] **{v['title']}** — {v['channel']}\n  {v['url']}" for v in results]
    return "\n".join(lines)


@mcp.tool()
def find_related(video_id: int, n: int = 5) -> str:
    """Find videos most semantically similar to a given video."""
    conn = get_connection()
    anchor = conn.execute(
        "SELECT content FROM chunks WHERE video_id = ? LIMIT 1", (video_id,)
    ).fetchone()
    if not anchor:
        return f"No chunks found for video {video_id}."

    query_vector = embeddings.embed([anchor["content"]])[0]
    rows = conn.execute("""
        SELECT vc.distance, c.video_id
        FROM vec_chunks vc
        JOIN chunks c ON vc.chunk_id = c.id
        WHERE vc.embedding MATCH ?
        AND c.video_id != ?
        ORDER BY vc.distance
        LIMIT ?
    """, (_serialize(query_vector), video_id, n * 3)).fetchall()

    seen_ids = set()
    related = []
    for row in rows:
        if row["video_id"] not in seen_ids:
            seen_ids.add(row["video_id"])
            video = conn.execute(
                "SELECT id, title, channel FROM videos WHERE id = ?",
                (row["video_id"],)
            ).fetchone()
            related.append(video)
            if len(related) >= n:
                break

    conn.close()
    if not related:
        return "No related videos found."
    lines = [f"- [{v['id']}] **{v['title']}** — {v['channel']}" for v in related]
    return "\n".join(lines)


@mcp.tool()
def synthesize_across(theme: str, max_videos: int = 10) -> str:
    """Retrieve video summaries related to a theme so you can synthesize insights across them."""
    conn = get_connection()
    query_vector = embeddings.embed([theme])[0]
    rows = conn.execute("""
        SELECT vc.distance, c.video_id
        FROM vec_chunks vc
        JOIN chunks c ON vc.chunk_id = c.id
        WHERE vc.embedding MATCH ?
        ORDER BY vc.distance
        LIMIT ?
    """, (_serialize(query_vector), max_videos * 3)).fetchall()

    seen_ids = set()
    video_ids = []
    for row in rows:
        if row["video_id"] not in seen_ids:
            seen_ids.add(row["video_id"])
            video_ids.append(row["video_id"])
            if len(video_ids) >= max_videos:
                break

    conn.close()

    if not video_ids:
        return "No relevant videos found."

    sections = []
    conn = get_connection()
    for vid_id in video_ids:
        v = conn.execute("SELECT title, channel, summary_md FROM videos WHERE id = ?", (vid_id,)).fetchone()
        sections.append(f"## {v['title']} ({v['channel']})\n\n{v['summary_md']}")
    conn.close()

    return f"# Videos related to: {theme}\n\n" + "\n\n---\n\n".join(sections)


# RESOURCES
@mcp.resource("video://{video_id}")
def video_resource(video_id: str) -> str:
    """Full summary of a specific video, for attaching as context."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    if not row:
        return f"No video found with id {video_id}."
    return (
        f"# {row['title']}\n\n"
        f"**Channel:** {row['channel']} | **URL:** {row['url']} | **Published:** {row['published_at']}\n\n"
        f"{row['summary_md']}"
    )


@mcp.resource("library://recent")
def recent_resource() -> str:
    """The 10 most recently ingested videos."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, title, channel, published_at
        FROM videos ORDER BY ingested_at DESC LIMIT 10
    """).fetchall()
    conn.close()
    lines = [f"- [{r['id']}] {r['title']} — {r['channel']} ({r['published_at']})" for r in rows]
    return "# Recently Ingested Videos\n\n" + "\n".join(lines)


@mcp.resource("library://forgotten")
def forgotten_resource() -> str:
    """Videos ingested more than 30 days ago — candidates for revisiting."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, title, channel
        FROM videos
        WHERE ingested_at <= datetime('now', '-30 days')
        ORDER BY RANDOM() LIMIT 10
    """).fetchall()
    conn.close()
    lines = [f"- [{r['id']}] {r['title']} — {r['channel']}" for r in rows]
    return "# Forgotten Videos\n\n" + "\n".join(lines)


@mcp.prompt()
def synthesize_theme(theme: str) -> str:
    """Build a prompt that synthesizes insights across all videos related to a theme."""
    return (
        f"Use the `synthesize_across` tool with theme='{theme}' to retrieve relevant video summaries. "
        f"Then write a cohesive synthesis that:\n"
        f"1. Identifies the key ideas across all videos\n"
        f"2. Notes where speakers agree or contradict each other\n"
        f"3. Ends with 3 actionable takeaways\n\n"
        f"Cite each video by title when referencing it."
    )


# PROMPTS
@mcp.prompt()
def whats_related(topic: str) -> str:
    """Find and summarize what's in the library on a given topic."""
    return (
        f"Use `search_videos` with query='{topic}' to find relevant videos. "
        f"Then briefly describe what each video covers and how they relate to '{topic}'."
    )


@mcp.prompt()
def revisit_suggestion() -> str:
    """Suggest forgotten videos and ask the user which to revisit."""
    return (
        "Use `suggest_forgotten` to find videos worth revisiting. "
        "Present them to the user and ask which one they'd like to review in depth. "
        "Once they choose, use `get_video` to fetch the full summary and discuss it."
    )


@mcp.prompt()
def cite_from_library(topic: str) -> str:
    """Find supporting evidence in the library for a given claim or topic."""
    return (
        f"Search the video library for content related to '{topic}' using `search_videos`. "
        f"For each relevant result, quote the most pertinent passage from the summary "
        f"and explain how it relates to '{topic}'."
    )


if __name__ == "__main__":
    mcp.run()