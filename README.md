# Video Library MCP Server

A local Python MCP server that turns a private Obsidian repo of YouTube video summaries into queryable, synthesizable context — available to both Claude Desktop and Claude Code.

## What it does

Indexes markdown video summaries from a local Obsidian vault into SQLite with full-text search (FTS5) and vector similarity search (sqlite-vec). Exposes the library to any MCP-compatible client via tools, resources, and prompts.

## Architecture

| Concern | Decision |
|---|---|
| Language / SDK | Python 3.11+, FastMCP |
| Transport | stdio (local only) |
| Metadata + keyword search | SQLite + FTS5 |
| Vector store | sqlite-vec |
| Embeddings | `openai/text-embedding-3-small` via OpenRouter |
| Source of truth | Local Obsidian git repo |

## Project structure

```
server.py        # FastMCP server — tools, resources, prompts
indexer.py       # Indexer — git pull, parse, chunk, embed, write to DB
db.py            # SQLite schema and connection helper
embeddings.py    # Embedding client (OpenRouter)
config.py        # Paths and settings (reads from .env)
data/            # SQLite database (gitignored)
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your values:

```
OPENROUTER_API_KEY=your_key_here
OBSIDIAN_REPO_PATH=/path/to/your/obsidian/repo
```

## Usage

**Index your library:**
```bash
python indexer.py
```

**Run the server (for testing):**
```bash
python server.py
```

## MCP Primitives

**Tools** (model-invoked)
- `reindex_library()` — git pull + re-index changed files
- `search_videos(query, semantic, limit)` — FTS + semantic search
- `find_related(video_id, n)` — find similar videos
- `synthesize_across(theme, max_videos)` — fetch content for cross-video synthesis
- `get_video(video_id)` — fetch a full summary
- `list_recent(days)` — recently ingested videos
- `suggest_forgotten(min_age_days)` — surface older videos worth revisiting

**Resources** (host-attached context)
- `video://{id}` — full summary of a specific video
- `library://recent` — recently ingested videos
- `library://forgotten` — older videos worth revisiting

**Prompts** (user-triggered templates)
- `synthesize_theme` — synthesize insights across videos on a theme
- `whats_related` — find and describe library content on a topic
- `revisit_suggestion` — surface forgotten videos interactively
- `cite_from_library` — find supporting evidence for a claim
