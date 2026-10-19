"""Lazy Nebius configuration: importing the API never requires a secret."""
import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, AsyncOpenAI
from causaltrace.analysis_policy import settings, MODEL_USAGE
from causaltrace.investigation_control import ACTIVE_CONTROL, InvestigationStopped

DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"


def configuration():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    return os.getenv("NEBIUS_API_KEY", ""), os.getenv("NEBIUS_MODEL", DEFAULT_MODEL)


def record_usage(response, model):
    ledger = MODEL_USAGE.get()
    usage = response.usage
    if ledger is not None and usage is not None:
        ledger.append({'model':model, 'prompt_tokens':usage.prompt_tokens or 0,
                       'completion_tokens':usage.completion_tokens or 0, 'total_tokens':usage.total_tokens or 0})


async def controlled_completion(control, key, model, messages, max_tokens, options, timeout):
    control.activity = 'ai_request'
    async with AsyncOpenAI(api_key=key, base_url='https://api.tokenfactory.nebius.com/v1/',
                           timeout=timeout, max_retries=0) as client:
        task = asyncio.create_task(client.chat.completions.create(model=model, messages=messages,
                                  max_tokens=max_tokens, **options))
        response = None
        try:
            while True:
                state = control.status()
                if state == 'stopping':
                    raise InvestigationStopped()
                if response is None and task.done():
                    response = task.result()
                    record_usage(response, model)
                if state == 'paused':
                    control.pause_effect = 'provider_not_pausable'
                elif response is not None:
                    return response
                await asyncio.sleep(.05)
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            control.activity = 'between_operations'


def complete(messages, *, structured=False, max_tokens=None):
    from causaltrace.investigation_control import checkpoint
    checkpoint()
    limits = settings()
    max_tokens = max_tokens or limits["response_tokens"]
    key, model = configuration()
    if not key:
        raise RuntimeError("Set NEBIUS_API_KEY in the project .env and restart the backend.")
    options = {"response_format": {"type": "json_object"}} if structured else {}
    control = ACTIVE_CONTROL.get()
    if control is not None:
        response = asyncio.run(controlled_completion(control, key, model, messages, max_tokens, options, limits['timeout']))
    else:
        with OpenAI(api_key=key, base_url="https://api.tokenfactory.nebius.com/v1/",
                    timeout=limits["timeout"], max_retries=0) as client:
            response = client.chat.completions.create(
                model=model, messages=messages, max_tokens=max_tokens, **options,
            )
        record_usage(response, model)
    checkpoint()
    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise ValueError("Nemotron response was truncated. Reduce source context and retry.")
    if not choice.message.content:
        raise ValueError("Nemotron returned an empty response.")
    return choice.message.content, model


if __name__ == "__main__":
    print(complete([{"role": "user", "content": "Reply with: CausalTrace connection ready"}],
                   max_tokens=100)[0])
