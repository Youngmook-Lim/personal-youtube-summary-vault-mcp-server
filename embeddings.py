from openai import OpenAI
import config

_client = OpenAI(
    api_key=config.OPENROUTER_API_KEY,
    base_url=config.OPENROUTER_BASE_URL,
)

def embed(texts: list[str]) -> list[list[float]]:
    response = _client.embeddings.create(
        model=config.EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]