"""Lazy Nebius configuration: importing the API never requires a secret."""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"


def configuration():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    return os.getenv("NEBIUS_API_KEY", ""), os.getenv("NEBIUS_MODEL", DEFAULT_MODEL)


def complete(messages, *, structured=False, max_tokens=4000):
    key, model = configuration()
    if not key:
        raise RuntimeError("Set NEBIUS_API_KEY in the project .env and restart the backend.")
    options = {"response_format": {"type": "json_object"}} if structured else {}
    with OpenAI(api_key=key, base_url="https://api.tokenfactory.nebius.com/v1/",
                timeout=60, max_retries=0) as client:
        response = client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, **options,
        )
    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise ValueError("Nemotron response was truncated. Reduce source context and retry.")
    if not choice.message.content:
        raise ValueError("Nemotron returned an empty response.")
    return choice.message.content, model


if __name__ == "__main__":
    print(complete([{"role": "user", "content": "Reply with: CausalTrace connection ready"}],
                   max_tokens=100)[0])
