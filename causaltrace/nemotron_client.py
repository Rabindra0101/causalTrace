
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("NEBIUS_API_KEY")

if not API_KEY:
    raise RuntimeError("NEBIUS_API_KEY is missing from .env")

MODEL = "nvidia/nemotron-3-super-120b-a12b"

client = OpenAI(
    base_url="https://api.tokenfactory.nebius.com/v1/",
    api_key=API_KEY,
    timeout=30.0,
)


def test_nemotron_connection():
    """Check the Nebius Token Factory connection."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a software debugging assistant.",
            },
            {
                "role": "user",
                "content": (
                    "A Python test expects 80 but receives 120. "
                    "The code changed from price - discount "
                    "to price + discount. Explain the likely bug "
                    "in one sentence."
                ),
            },
        ],
        max_tokens=300,
    )

    print("NEMOTRON RESPONSE:")
    print(response.choices[0].message.content)


def generate_root_cause_hypothesis(test_output: str, git_diff: str) -> str:
    """Generate a root-cause hypothesis from collected evidence."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are CausalTrace, a software regression investigator. "
                    "Analyze the supplied test failure and Git diff. "
                    "Identify the most likely root cause and explain the evidence. "
                    "Treat the diff as a candidate, not a verified cause. "
                    "Do not claim the cause has been experimentally proven. "
                    "Keep the response concise and complete. "
                    "Use the headings: Likely Root Cause, Evidence, "
                    "and Recommended Fix."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"TEST FAILURE:\n{test_output}\n\n"
                    f"CANDIDATE GIT DIFF:\n{git_diff}\n\n"
                    "Explain the likely root cause and why the "
                    "evidence supports it."
                ),
            },
        ],
        max_tokens=1500,
    )

    choice = response.choices[0]
    content = choice.message.content or ""

    if choice.finish_reason == "length":
        print(
            "WARNING: Nemotron reached the output-token limit. "
            "The hypothesis may be incomplete."
        )

    return content


if __name__ == "__main__":
    test_nemotron_connection()
