import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OBSIDIAN_REPO_PATH = Path(os.environ["OBSIDIAN_REPO_PATH"])
VIDEOS_FOLDERS = [
    OBSIDIAN_REPO_PATH / "+",
    OBSIDIAN_REPO_PATH / "Atlas" / "Youtube Guides",
]

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50