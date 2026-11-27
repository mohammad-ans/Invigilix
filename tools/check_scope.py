"""Validate a PR against the ownership manifest from its protected base revision."""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

def owns(rule, path):
    return path.startswith(rule) if rule.endswith("/") else path == rule

def check_scope(manifest, branch, paths):
    lane = manifest.get(branch)
    if not lane and branch.startswith("foundation/") and len(branch) > len("foundation/"):
        lane = manifest["foundation/*"]
    if not lane:
        raise ValueError(f"Unassigned branch {branch!r}. See collaboration/ownership.json.")
    if not paths:
        raise ValueError("No changed paths to validate.")
    denied = sorted(path for path in set(paths) if not any(owns(rule, path) for rule in lane["paths"]))
    if denied:
        raise ValueError("Outside the assigned scope:\n" + "\n".join(repr(p) for p in denied))

def read_pr():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event["pull_request"]
    total = pr["changed_files"]
    if not 0 < total <= 3000:
        raise ValueError("Split this PR so GitHub can report its complete file list.")
    endpoint = f'{os.environ["GITHUB_API_URL"]}/repos/{os.environ["GITHUB_REPOSITORY"]}/pulls/{pr["number"]}'
    headers = {"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json"}
    def get(url):
        with urlopen(Request(url, headers=headers), timeout=20) as response:
            return json.load(response)
    def verify_revision():
        current = get(endpoint)
        if any(current[side]["sha"] != pr[side]["sha"] for side in ("base", "head")):
            raise ValueError("PR revision changed during the check. Use the run for the new revision.")
    verify_revision()
    files = []
    for page in range(1, (total + 99) // 100 + 1):
        files.extend(get(f"{endpoint}/files?per_page=100&page={page}"))
    verify_revision()
    if len(files) != total or len({f["filename"] for f in files}) != total:
        raise ValueError("Incomplete PR file list.")
    paths = [f[key] for f in files for key in ("filename", "previous_filename") if key in f]
    return pr["head"]["ref"], paths

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", help="Local check with repo-relative file paths")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    try:
        branch, changed = (args.branch, args.paths) if args.branch else read_pr()
        check_scope(json.loads((ROOT / "collaboration/ownership.json").read_text()), branch, changed)
    except ValueError as error:
        sys.exit(str(error))
    print(f"Scope verified for {branch} ({len(set(changed))} paths)")
