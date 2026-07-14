#!/usr/bin/env python3
"""
End-to-end integration test for the OpenClaw evolve skill.
Tests all ported modules: observe -> diagnose -> gate -> report -> etc.
Run: python3 tests/test_integration.py
"""

import importlib.util
import os
import sys
from importlib.machinery import SourceFileLoader

EVOLVE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, EVOLVE_DIR)
sys.path.insert(0, os.path.join(EVOLVE_DIR, "generator"))
sys.path.insert(0, os.path.join(EVOLVE_DIR, "_lib"))

passed = 0
failed = 0
errors = []


def _assert(condition, name, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} — {detail}")


def load_skill(name):
    """Load a .skill file as a module."""
    skill_path = os.path.join(EVOLVE_DIR, f"{name}.skill")
    if not os.path.exists(skill_path):
        return None
    spec = importlib.util.spec_from_file_location(
        name, skill_path,
        loader=SourceFileLoader(name, skill_path)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_mock_trace():
    """Create a mock trace for testing."""
    return {
        "task_id": "test-001",
        "timestamp": "2026-07-07T10:00:00Z",
        "source": "test",
        "total_tokens": 3000,
        "total_duration_ms": 500,
        "agent": {"id": "planner", "version": "v1", "success": True, "latency_ms": 200},
        "skills": [
            {"id": "Read", "version": "v1", "duration_ms": 50, "tokens": 100, "success": True, "retry_count": 0, "error": None},
            {"id": "Read", "version": "v1", "duration_ms": 30, "tokens": 80, "success": True, "retry_count": 0, "error": None},
            {"id": "Bash", "version": "v1", "duration_ms": 100, "tokens": 200, "success": False, "retry_count": 1, "error": "timeout"},
        ],
        "memory": {"hit_rate": 0.6, "latency_ms": 15},
    }


def test_lib_time_utils():
    """Test 1: time_utils provides UTC time with Z suffix."""
    print("\n[1] Testing lib/time_utils...")
    from _lib.time_utils import utcnow_iso
    result = utcnow_iso()
    _assert("Z" in result, "utcnow_iso returns UTC with Z suffix", f"got {result}")
    _assert("T" in result, "utcnow_iso returns ISO format", f"got {result}")


def test_lib_lock_utils():
    """Test 2: lock_utils provides file locking."""
    import tempfile
    print("\n[2] Testing lib/lock_utils...")
    from _lib.lock_utils import file_lock, get_lock_backend
    lock_file = os.path.join(tempfile.gettempdir(), "test_lock.tmp")
    with file_lock(lock_file, timeout=5) as fd:
        _assert(fd is not None, "file_lock acquires lock", f"fd={fd}")
    print(f"  lock backend: {get_lock_backend()}")


def test_lib_path_utils():
    """Test 3: path_utils provides correct paths."""
    print("\n[3] Testing lib/path_utils...")
    from _lib.path_utils import EVOLVE_DIR, STATE_DIR
    _assert(EVOLVE_DIR.exists(), "EVOLVE_DIR exists", str(EVOLVE_DIR))
    _assert(EVOLVE_DIR.name == "evolve", "EVOLVE_DIR is evolve dir", EVOLVE_DIR.name)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _assert(STATE_DIR.exists(), "STATE_DIR created")


def test_lib_manifest_utils():
    """Test 4: manifest_utils CRUD operations."""
    print("\n[4] Testing lib/manifest_utils...")
    from _lib.manifest_utils import load_all_manifests, load_manifest, store_manifest
    _assert(load_all_manifests() == [], "load_all returns empty list")
    result = store_manifest("test-001", {"manifest_id": "test-001", "target": "planner", "status": "pending_review"})
    _assert(result, "store_manifest succeeds")
    manifests = load_all_manifests()
    _assert(len(manifests) > 0, "load_all returns stored manifests")
    found = load_manifest("test-001")
    _assert(found is not None, "load_manifest finds by id")
    if found:
        _assert(found["target"] == "planner", "manifest data correct")


def test_observe():
    """Test 5: observe produces traces."""
    print("\n[5] Testing observe...")
    mod = load_skill("observe")
    _assert(mod is not None, "observe module loaded")
    if not mod:
        return
    traces = mod.observe(count=10)
    _assert(isinstance(traces, list), "observe returns list")

    # Store and retrieve a trace
    trace = make_mock_trace()
    result = mod.store_trace(trace)
    _assert(result, "store_trace succeeds")

    traces2 = mod.observe(count=10)
    _assert(len(traces2) > 0, "observe returns stored trace", f"got {len(traces2)}")

    if traces2:
        t = traces2[0]
        _assert("task_id" in t, "trace has task_id")
        _assert("timestamp" in t, "trace has timestamp")
        _assert("total_tokens" in t, "trace has total_tokens")
        _assert("skills" in t, "trace has skills")
        _assert("agent" in t, "trace has agent")


def test_diagnose():
    """Test 6: diagnose produces meaningful scores."""
    print("\n[6] Testing diagnose...")
    mod = load_skill("diagnose")
    _assert(mod is not None, "diagnose module loaded")
    if not mod:
        return

    traces = [make_mock_trace()] * 10
    report = mod.diagnose(traces)

    _assert("tool_efficiency" in report, "report has tool_efficiency")
    _assert("task_quality" in report, "report has task_quality")
    _assert("skill_success" in report, "report has skill_success")
    _assert("context_utilization" in report, "report has context_utilization")
    _assert("priority" in report, "report has priority")

    # Scores should not all be zero
    scores = [
        report["tool_efficiency"]["score"],
        report["task_quality"]["score"],
        report["skill_success"]["score"],
        report["context_utilization"]["score"],
    ]
    non_zero = sum(1 for s in scores if s > 0)
    _assert(non_zero > 0, "not all scores are zero", f"scores={scores}")

    # Priority should be 4 dimensions
    _assert(len(report["priority"]) == 4, "priority has 4 dimensions", f"got {len(report['priority'])}")


def test_gate():
    """Test 7: gate validates candidates."""
    print("\n[7] Testing gate...")
    mod = load_skill("gate")
    _assert(mod is not None, "gate module loaded")
    if not mod:
        return

    # Valid candidate
    candidate = {
        "type": "skill",
        "mechanism": "tabu_search",
        "changes": [
            {"action": "integrate_mechanism", "mechanism": "tabu_search", "target_module": "planner", "description": "test", "interface": {}, "integration": {}},
        ],
        "risk": "low",
        "description": "A test candidate",
        "expected_improvement": "test improvement",
    }
    result = mod.verify(candidate=candidate, target="planner")
    _assert("passed" in result, "gate returns passed field")
    _assert("checks" in result, "gate returns checks list")
    _assert(result["passed"], "valid candidate passes", f"failed={result.get('failed_count')}/{result.get('total')}")

    # Candidate with path traversal
    bad_candidate = {
        "type": "skill",
        "mechanism": "test",
        "changes": [
            {"action": "modify_skill_file", "skill_name": "test", "file_path": "../../secret.json", "new_content": "{}", "operation": "replace"},
        ],
        "risk": "low",
        "description": "test",
        "expected_improvement": "test",
    }
    mod.verify(candidate=bad_candidate, target="planner")
    # Gate doesn't block path traversal — deploy does. Just check it parses.
    _assert(True, "gate handles bad candidate")


def test_report():
    """Test 8: report produces valid proposal."""
    print("\n[8] Testing report...")
    mod = load_skill("report")
    _assert(mod is not None, "report module loaded")
    if not mod:
        return

    traces = [make_mock_trace()] * 3
    report = {
        "tool_efficiency": {"score": 0.5, "trend": "stable", "confidence": 0.5},
        "task_quality": {"score": 0.8, "trend": "stable", "confidence": 0.5},
        "skill_success": {"score": 0.9, "trend": "stable", "confidence": 0.5},
        "context_utilization": {"score": 0.6, "trend": "stable", "confidence": 0.5},
        "priority": ["tool_efficiency", "context_utilization", "task_quality", "skill_success"],
        "trace_count": 3,
        "analysis_confidence": 0.6,
    }
    candidate = {
        "type": "skill", "strategy": "bilevel", "generator": "bilevel",
        "mechanism": "tabu_search", "description": "test", "changes": [],
        "risk": "low", "expected_improvement": "test",
    }
    sandbox_result = {"baseline_score": 50.0, "candidate_score": 55.0, "delta": 5.0, "verdict": "improved", "reliability": 0.9, "runs": 3, "budget_used": {}}

    proposal = mod.build_proposal(target="planner", strategy="bilevel", traces=traces, report=report, candidate=candidate, sandbox_result=sandbox_result)
    _assert("proposal_version" in proposal, "proposal has version")
    _assert("diagnosis" in proposal, "proposal has diagnosis")
    _assert(proposal["valid"], "proposal is valid", f"errors={proposal.get('validation_errors', [])}")
    diag = proposal["diagnosis"]
    _assert("tool_efficiency" in diag, "diagnosis has tool_efficiency")
    _assert("task_quality" in diag, "diagnosis has task_quality")
    _assert("skill_success" in diag, "diagnosis has skill_success")
    _assert("context_utilization" in diag, "diagnosis has context_utilization")
    _assert("Z" in proposal.get("timestamp", ""), "timestamp is UTC formatted")


def test_benchmark():
    """Test 9: benchmark produces scores from trace data."""
    print("\n[9] Testing benchmark...")
    mod = load_skill("benchmark")
    _assert(mod is not None, "benchmark module loaded")
    if not mod:
        return

    traces = [make_mock_trace()] * 5
    result = mod.run_suite(target="planner", traces=traces, runs=2)
    _assert("score" in result, "benchmark returns score")
    _assert("stability" in result, "benchmark returns stability")
    _assert("runs" in result, "benchmark returns runs")
    _assert(result["score"] > 0, "score is positive", f"score={result['score']}")
    _assert(result["stability"] > 0, "stability is positive")

    # Test compare
    baseline = mod.run_suite(target="planner", traces=traces, runs=2)
    comparison = mod.compare(baseline, result)
    _assert("delta" in comparison, "compare returns delta")
    _assert("verdict" in comparison, "compare returns verdict")


def test_bilevel_generator():
    """Test 10: bilevel generator fallback produces valid candidate."""
    print("\n[10] Testing bilevel generator...")
    sys.path.insert(0, os.path.join(EVOLVE_DIR, "generator"))
    from generator.registry import get_registry
    reg = get_registry()
    gen = reg.get("bilevel")
    _assert(gen is not None, "bilevel generator registered")
    if not gen:
        return
    _assert(gen.name == "bilevel", "generator name correct")

    report = {
        "tool_efficiency": {"score": 0.5, "trend": "stable", "confidence": 0.5},
        "task_quality": {"score": 0.8, "trend": "stable", "confidence": 0.5},
        "skill_success": {"score": 0.9, "trend": "stable", "confidence": 0.5},
        "context_utilization": {"score": 0.6, "trend": "stable", "confidence": 0.5},
        "priority": ["tool_efficiency", "context_utilization", "task_quality", "skill_success"],
        "trace_count": 10,
        "analysis_confidence": 0.6,
    }
    candidate = gen.generate("planner", report)
    _assert("type" in candidate, "candidate has type")
    _assert("mechanism" in candidate, "candidate has mechanism")
    _assert("risk" in candidate, "candidate has risk")
    _assert("changes" in candidate, "candidate has changes")
    _assert(len(candidate.get("changes", [])) > 0, "candidate has at least 1 change")


def test_sandbox():
    """Test 11: sandbox snapshot and rollback."""
    print("\n[11] Testing sandbox...")
    mod = load_skill("sandbox")
    _assert(mod is not None, "sandbox module loaded")
    if not mod:
        return

    snap = mod._snapshot(EVOLVE_DIR)
    _assert(snap["success"], "snapshot succeeds", snap.get("error", ""))

    backed_up = snap.get("backed_up_files", [])
    _assert(len(backed_up) > 0, "snapshot backs up files", f"backed_up={backed_up}")

    has_skill = any(f.endswith((".skill", ".py")) for f in backed_up)
    _assert(has_skill, "snapshot backs up code files", f"files={backed_up[:3]}")

    rollback_result = mod._rollback(snap)
    _assert(rollback_result["success"], "rollback succeeds", rollback_result.get("error", ""))


def test_deploy():
    """Test 12: deploy validation and basic operations."""
    print("\n[12] Testing deploy...")
    mod = load_skill("deploy")
    _assert(mod is not None, "deploy module loaded")
    if not mod:
        return

    # Path validation
    safe = mod._validate_file_path("SKILL.md", "evolve")
    _assert(safe == "SKILL.md", "valid path passes", f"got {safe}")

    blocked = mod._validate_file_path("../../secret.json", "evolve")
    _assert(blocked is None, "path traversal blocked", f"got {blocked}")

    blocked2 = mod._validate_file_path("/etc/passwd", "evolve")
    _assert(blocked2 is None, "absolute path blocked", f"got {blocked2}")

    blocked3 = mod._validate_file_path("../../../openclaw.json", "evolve")
    _assert(blocked3 is None, "deep traversal blocked", f"got {blocked3}")


def test_rollback():
    """Test 13: rollback module loads."""
    print("\n[13] Testing rollback...")
    mod = load_skill("rollback")
    _assert(mod is not None, "rollback module loaded")
    if not mod:
        return
    _assert(hasattr(mod, "rollback"), "has rollback function")
    _assert(hasattr(mod, "rollback_latest"), "has rollback_latest function")


def test_orchestrate():
    """Test 14: orchestrate module loads with pipeline structure."""
    print("\n[14] Testing orchestrate...")
    mod = load_skill("orchestrate")
    _assert(mod is not None, "orchestrate module loaded")
    if not mod:
        return
    _assert(hasattr(mod, "run"), "orchestrate has run function")
    _assert(hasattr(mod, "PipelineBudgetExceeded"), "orchestrate has budget exception")
    _assert("max_tokens" in mod.DEFAULT_BUDGET, "orchestrate has DEFAULT_BUDGET")


def test_timestamp_no_utcnow():
    """Test 15: No bare utcnow() calls (except time_utils)."""
    print("\n[15] Testing no bare utcnow()...")
    import re
    utcnow_files = []
    for fname in os.listdir(EVOLVE_DIR):
        fpath = os.path.join(EVOLVE_DIR, fname)
        if os.path.isfile(fpath) and fname.endswith((".skill", ".py")):
            with open(fpath, encoding="utf-8") as f:
                for i, line in enumerate(f.read().splitlines(), 1):
                    if line.strip().startswith("#"):
                        continue
                    if re.search(r'\butcnow\(\)', line) and "utcnow_iso" not in line:
                        utcnow_files.append(f"{fname}:{i}")

    for subdir in ["_lib", "generator"]:
        sub_path = os.path.join(EVOLVE_DIR, subdir)
        if os.path.isdir(sub_path):
            for fname in os.listdir(sub_path):
                if not fname.endswith(".py"):
                    continue
                if fname == "time_utils.py":
                    continue
                fpath = os.path.join(sub_path, fname)
                with open(fpath, encoding="utf-8") as f:
                    for i, line in enumerate(f.read().splitlines(), 1):
                        if line.strip().startswith("#"):
                            continue
                        if re.search(r'\butcnow\(\)', line) and "utcnow_iso" not in line:
                            utcnow_files.append(f"{subdir}/{fname}:{i}")

    _assert(len(utcnow_files) == 0, "no bare utcnow() calls", f"found in: {utcnow_files}")


def test_path_traversal_protection():
    """Test 16: Both deploy and sandbox have path traversal protection."""
    print("\n[16] Testing path traversal protection...")
    deploy_mod = load_skill("deploy")
    if deploy_mod and hasattr(deploy_mod, "_validate_file_path"):
        blocked = deploy_mod._validate_file_path("../../../models.json", "evolve")
        _assert(blocked is None, "deploy blocks path traversal")
    else:
        _assert(False, "deploy has _validate_file_path")

    sandbox_mod = load_skill("sandbox")
    if sandbox_mod:
        # Check sandbox code mentions path traversal protection
        sandbox_path = os.path.join(EVOLVE_DIR, "sandbox.skill")
        with open(sandbox_path) as f:
            content = f.read()
        has_protection = "os.path.isabs" in content and "normpath" in content
        _assert(has_protection, "sandbox has path validation", "no path validation found")


def test_all_modules_importable():
    """Test 17: All .skill files are importable."""
    print("\n[17] Testing all modules importable...")
    skill_files = [
        f.replace(".skill", "") for f in os.listdir(EVOLVE_DIR)
        if f.endswith(".skill") and f != "__init__.py"
    ]
    expected = {"observe", "diagnose", "gate", "report", "benchmark",
                 "sandbox", "deploy", "rollback", "orchestrate"}
    present = set(skill_files)
    missing = expected - present
    _assert(len(missing) == 0, "all expected .skill files exist", f"missing: {missing}")

    errors_import = []
    for name in sorted(skill_files):
        mod = load_skill(name)
        if mod is None:
            errors_import.append(name)
        else:
            pass  # already verified above
    _assert(len(errors_import) == 0, "all modules importable", f"failed: {errors_import}")


def test_atomic_writes():
    """Test 18: deploy uses atomic writes (.tmp + rename)."""
    print("\n[18] Testing atomic writes...")
    deploy_path = os.path.join(EVOLVE_DIR, "deploy.skill")
    with open(deploy_path) as f:
        content = f.read()
    has_tmp_rename = ".tmp" in content and "rename" in content
    _assert(has_tmp_rename, "deploy uses atomic writes", "no .tmp/rename pattern found")

    rollback_path = os.path.join(EVOLVE_DIR, "rollback.skill")
    with open(rollback_path) as f:
        rb_content = f.read()
    has_atomic = ".tmp" in rb_content and "rename" in rb_content
    _assert(has_atomic, "rollback uses atomic writes", "no .tmp/rename pattern found")


if __name__ == "__main__":
    print("=" * 60)
    print("OpenClaw Evolve Skill Integration Test Suite")
    print("=" * 60)

    test_lib_time_utils()
    test_lib_lock_utils()
    test_lib_path_utils()
    test_lib_manifest_utils()
    test_observe()
    test_diagnose()
    test_gate()
    test_report()
    test_benchmark()
    test_bilevel_generator()
    test_sandbox()
    test_deploy()
    test_rollback()
    test_orchestrate()
    test_timestamp_no_utcnow()
    test_path_traversal_protection()
    test_all_modules_importable()
    test_atomic_writes()

    # Summary
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if errors:
        print("\nFailures:")
        for e in errors:
            print(f"  - {e}")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
