# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Snapshot Manager for Skill Optimizer

Manages iteration snapshots during optimization.
Creates numbered snapshots of skill state and allows restore.

Usage:
  python snapshot_manager.py create --skill-path ./my-skill --iteration 1
  python snapshot_manager.py list --workspace workspace/
  python snapshot_manager.py restore --iteration 1 --workspace workspace/
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


def create_snapshot(skill_path: str, iteration: int, workspace_dir: str, extra_files: list = None) -> str:
    """
    Create a snapshot of the current skill state.

    Args:
        skill_path: Path to the skill directory (e.g., './travel-planner')
        iteration: Iteration number (1-indexed)
        workspace_dir: Workspace root for snapshots
        extra_files: List of additional files to include (e.g., benchmark.json)

    Returns:
        Path to snapshot directory
    """
    skill_path = Path(skill_path).resolve()
    workspace = Path(workspace_dir).resolve()
    snapshot_dir = workspace / f"iteration-{iteration}"

    if snapshot_dir.exists():
        print(f"Warning: snapshot-{iteration} already exists, overwriting", file=sys.stderr)

    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Copy SKILL.md
    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        shutil.copy2(skill_md, snapshot_dir / "SKILL.md")
    else:
        print(f"Warning: SKILL.md not found in {skill_path}", file=sys.stderr)

    # Copy entire skill directory (excluding large caches)
    for item in skill_path.iterdir():
        if item.name in ["__pycache__", ".pytest_cache", "node_modules"]:
            continue
        dest = snapshot_dir / "skill_src" / item.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    # Copy extra files (e.g., benchmark.json, eval results)
    if extra_files:
        for f in extra_files:
            fp = Path(f)
            if fp.exists():
                shutil.copy2(fp, snapshot_dir / fp.name)

    # Write snapshot metadata
    meta = {
        "iteration": iteration,
        "skill_path": str(skill_path),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "files_included": [p.name for p in snapshot_dir.iterdir()]
    }
    with open(snapshot_dir / "snapshot_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"✅ Snapshot {iteration} created at {snapshot_dir}")
    return str(snapshot_dir)

def list_snapshots(workspace_dir: str) -> list:
    """List all snapshots in workspace."""
    workspace = Path(workspace_dir).resolve()
    snapshots = []
    for d in workspace.iterdir():
        if d.is_dir() and d.name.startswith("iteration-"):
            meta_file = d / "snapshot_meta.json"
            if meta_file.exists():
                with open(meta_file) as f:
                    meta = json.load(f)
                snapshots.append(meta)
    return sorted(snapshots, key=lambda x: x["iteration"])

def restore_snapshot(iteration: int, workspace_dir: str, skill_path: str) -> bool:
    """
    Restore skill state from a snapshot.

    Args:
        iteration: Iteration number to restore
        workspace_dir: Workspace root containing snapshots
        skill_path: Target skill directory to overwrite

    Returns:
        True if restore succeeded
    """
    workspace = Path(workspace_dir).resolve()
    snapshot_dir = workspace / f"iteration-{iteration}"
    skill_path = Path(skill_path).resolve()

    if not snapshot_dir.exists():
        print(f"Error: snapshot-{iteration} not found", file=sys.stderr)
        return False

    # Find the skill source inside snapshot (assuming it's under skill_src/)
    skill_src = snapshot_dir / "skill_src"
    if not skill_src.exists():
        print("Error: no skill_src in snapshot", file=sys.stderr)
        return False

    # Restore SKILL.md and all other files
    for item in skill_src.iterdir():
        dest = skill_path / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    print(f"✅ Restored snapshot {iteration} to {skill_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Snapshot Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create
    create_parser = subparsers.add_parser("create", help="Create a snapshot")
    create_parser.add_argument("--skill-path", required=True, help="Skill directory path")
    create_parser.add_argument("--iteration", required=True, type=int, help="Iteration number")
    create_parser.add_argument("--workspace", default="./workspace", help="Workspace directory")
    create_parser.add_argument("--extra", nargs="*", help="Extra files to include")

    # List
    list_parser = subparsers.add_parser("list", help="List snapshots")
    list_parser.add_argument("--workspace", default="./workspace", help="Workspace directory")

    # Restore
    restore_parser = subparsers.add_parser("restore", help="Restore a snapshot")
    restore_parser.add_argument("--iteration", required=True, type=int, help="Iteration number")
    restore_parser.add_argument("--workspace", default="./workspace", help="Workspace directory")
    restore_parser.add_argument("--skill-path", required=True, help="Target skill directory")

    args = parser.parse_args()

    if args.command == "create":
        create_snapshot(args.skill_path, args.iteration, args.workspace, args.extra or [])
    elif args.command == "list":
        snapshots = list_snapshots(args.workspace)
        for s in snapshots:
            print(f"Iteration {s['iteration']}: {s['created_at']} | {len(s['files_included'])} files")
    elif args.command == "restore":
        restore_snapshot(args.iteration, args.workspace, args.skill_path)

if __name__ == "__main__":
    main()
