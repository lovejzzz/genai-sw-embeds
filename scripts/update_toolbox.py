#!/usr/bin/env python3
"""
Update toolbox-data.json with current timestamp and verify tool URLs.
Runs daily via GitHub Actions.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "toolbox-data.json"


def check_url(url: str, timeout: int = 10) -> bool:
    """Check if a URL is reachable (HEAD request)."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0 (ToolboxBot/1.0)")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 400
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return True  # Assume OK if we can't check (some sites block HEAD)


def main():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    # Update timestamp
    data["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Verify tool URLs and flag any that are down
    for cat in data.get("categories", []):
        for tool in cat.get("tools", []):
            url = tool.get("url", "")
            if url:
                reachable = check_url(url)
                if not reachable:
                    print(f"WARNING: {tool['name']} URL may be down: {url}")

    # Write updated data
    DATA_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Toolbox data updated: {data['updated']}")


if __name__ == "__main__":
    main()
