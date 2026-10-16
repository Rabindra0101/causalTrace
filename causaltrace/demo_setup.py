
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_PATH = PROJECT_ROOT / "deployment" / "inventory-demo.bundle"
INVENTORY_REPO = PROJECT_ROOT / "deployment" / "inventory-demo-repo"


def ensure_inventory_demo() -> Path:
    """Restore the trusted inventory demo from its Git bundle if needed."""

    if not BUNDLE_PATH.is_file():
        raise RuntimeError("Inventory demo bundle is missing.")

    if INVENTORY_REPO.exists():
        if not (INVENTORY_REPO / ".git").is_dir():
            raise RuntimeError(
                "Inventory demo destination exists but is not a Git repository."
            )
        return INVENTORY_REPO

    result = subprocess.run(
        [
            "git",
            "clone",
            "--",
            str(BUNDLE_PATH),
            str(INVENTORY_REPO),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Unable to restore inventory demo: {result.stderr}"
        )

    return INVENTORY_REPO
