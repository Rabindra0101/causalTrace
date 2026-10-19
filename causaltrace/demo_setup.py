"""Create small, real Git histories from shipped demo source recipes."""
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from causaltrace.build_doctor import demos

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_setup_lock = threading.Lock()


def recipes():
    result = {demo["id"]: demo for demo in demos()}
    result["calculator"] = {
        "name": "Calculator regression",
        "files": [
            {"path": "calculator.py", "content": "def calculate_discount(price, percent):\n    return price + price * percent / 100\n"},
            {"path": "test_calculator.py", "content": "from calculator import calculate_discount\n\ndef test_discount():\n    assert calculate_discount(100, 20) == 80\n"},
        ],
    }
    result["inventory"] = {
        "name": "Inventory returns regression",
        "files": [
            {"path": "inventory.py", "content": "def calculate_stock(initial, sold, returned):\n    return initial - sold - returned\n"},
            {"path": "test_inventory.py", "content": "from inventory import calculate_stock\n\ndef test_returns():\n    assert calculate_stock(100, 30, 10) == 80\n"},
        ],
    }
    result["negative_reversal"] = {
        "name": "Unrelated latest commit (control)",
        "files": [
            {"path": "calculator.py", "content": "def add(a, b):\n    return a - b\n"},
            {"path": "test_calculator.py", "content": "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"},
        ],
    }
    return result


DEMO_IDS = ("config", "imports", "api", "negative_reversal", "calculator", "inventory")


def demo_catalog():
    catalog = recipes()
    from causaltrace.public_demos import catalog as public_catalog
    return [{"id": key, "name": catalog[key]["name"]} for key in DEMO_IDS] + public_catalog()


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-10-18T12:00:00+00:00",
               GIT_COMMITTER_DATE="2026-10-18T12:00:00+00:00")
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false",
         "-c", "user.name=CausalTrace Demo", "-c", "user.email=demo@causaltrace.local", *args],
        cwd=repo, env=env, check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    ).stdout.strip()


def ensure_demo(repository_id: str) -> Path:
    from causaltrace.public_demos import PUBLIC_IDS
    from causaltrace.upstream_projects import ensure_upstream
    if repository_id in PUBLIC_IDS:
        return ensure_upstream(repository_id)
    if repository_id not in DEMO_IDS:
        raise ValueError("Repository is not configured.")
    root = PROJECT_ROOT / ".causaltrace" / "demos"
    target = root / repository_id
    with _setup_lock:
        if target.exists():
            if not (target / ".git").is_dir():
                raise RuntimeError(f"Demo folder is incomplete: {target}. Move it aside and retry.")
            return target
        root.mkdir(parents=True, exist_ok=True)
        recipe = recipes()[repository_id]
        broken = recipe["files"][0]["content"]
        good = {
            "imports": lambda s: s.replace("normalize_username", "normalize_user"),
            "config": lambda s: s.replace("os.getenv('APP_PORT', '8000')", "int(os.getenv('APP_PORT', '8000'))"),
            "api": lambda s: s.replace("    if not items:\n        return {'error': 'not found'}, 404\n", ""),
            "calculator": lambda s: s.replace("price +", "price -"),
            "inventory": lambda s: s.replace("- returned", "+ returned"),
            "negative_reversal": lambda s: s.replace("a - b", "a + b"),
        }[repository_id](broken)
        with tempfile.TemporaryDirectory(prefix="setup-", dir=root) as folder:
            repo = Path(folder) / "repo"
            repo.mkdir()
            git(repo, "init", "-q", "--template=", "--initial-branch=main")
            for index, file in enumerate(recipe["files"]):
                (repo / file["path"]).write_text(good if index == 0 else file["content"], encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "Add passing baseline and tests")
            (repo / recipe["files"][0]["path"]).write_text(broken, encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", f"Introduce {repository_id} regression")
            (repo / "notes.txt").write_text("Unrelated documentation change.\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "Document the demo (unrelated change)")
            repo.rename(target)
    return target
