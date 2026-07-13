import json
import subprocess
from pathlib import Path

ASO_DIR = Path(__file__).resolve().parents[1]
DELTA_CALC = ASO_DIR / "optimizer" / "delta_calculator.py"


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run_delta(args):
    return subprocess.run(["python3", str(DELTA_CALC), *args], capture_output=True, text=True, check=False)


def test_delta_passes_with_pass_rate_only():
    """Pass rate +1%, token +0% -> improved."""
    baseline = {
        "without_skill": {"pass_rate": {"mean": 0.50}, "time_seconds": {"mean": 1.0}, "tokens": {"mean": 1000}},
        "with_skill": {"pass_rate": {"mean": 0.80}, "time_seconds": {"mean": 1.0}, "tokens": {"mean": 1000}},
    }
    new = {"with_skill": {"pass_rate": {"mean": 0.81}, "time_seconds": {"mean": 1.0}, "tokens": {"mean": 1000}}}
    base_path = ASO_DIR / "state" / "delta_cases" / "delta_pass_only.json"
    new_path = ASO_DIR / "state" / "delta_cases" / "new_pass_only.json"
    _write_json(base_path, baseline)
    _write_json(new_path, new)

    proc = _run_delta(["--compare", "--baseline-file", str(base_path), "--new-result", str(new_path)])
    out = json.loads(proc.stdout)
    assert out["verdict"] == "improved"
    assert abs(out["pass_rate_vs_old"] - 0.01) < 1e-9


def test_delta_fails_token_spike_no_pass_rate_gain():
    """Pass rate 0%, token +21% -> failed."""
    baseline = {
        "without_skill": {"pass_rate": {"mean": 0.50}, "time_seconds": {"mean": 1.0}, "tokens": {"mean": 1000}},
        "with_skill": {"pass_rate": {"mean": 0.80}, "time_seconds": {"mean": 1.0}, "tokens": {"mean": 1000}},
    }
    new = {"with_skill": {"pass_rate": {"mean": 0.80}, "time_seconds": {"mean": 1.0}, "tokens": {"mean": 1221}}}
    base_path = ASO_DIR / "state" / "delta_cases" / "delta_fail.json"
    new_path = ASO_DIR / "state" / "delta_cases" / "new_fail.json"
    _write_json(base_path, baseline)
    _write_json(new_path, new)

    proc = _run_delta(["--compare", "--baseline-file", str(base_path), "--new-result", str(new_path)])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["verdict"] == "failed"


def test_delta_allows_small_token_increase_with_big_pass_rate_gain():
    """Pass rate +5%, token +0.5% -> improved (ASO allows this)."""
    baseline = {
        "without_skill": {"pass_rate": {"mean": 0.50}, "time_seconds": {"mean": 1.0}, "tokens": {"mean": 1000}},
        "with_skill": {"pass_rate": {"mean": 0.80}, "time_seconds": {"mean": 1.0}, "tokens": {"mean": 1000}},
    }
    new = {"with_skill": {"pass_rate": {"mean": 0.85}, "time_seconds": {"mean": 1.1}, "tokens": {"mean": 1005}}}
    base_path = ASO_DIR / "state" / "delta_cases" / "delta_aso_allowed.json"
    new_path = ASO_DIR / "state" / "delta_cases" / "new_aso_allowed.json"
    _write_json(base_path, baseline)
    _write_json(new_path, new)

    proc = _run_delta(["--compare", "--baseline-file", str(base_path), "--new-result", str(new_path)])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["verdict"] == "improved"
    assert abs(out["pass_rate_vs_old"] - 0.05) < 1e-9


def test_delta_init_creates_baseline():
    baseline_path = ASO_DIR / "state" / "delta_cases" / "delta_init.json"
    if baseline_path.exists():
        baseline_path.unlink()
    proc = _run_delta(["--init", "--skill-path", str(ASO_DIR), "--baseline-file", str(baseline_path)])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["status"] == "baseline_initialized"
    assert baseline_path.exists()
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert "with_skill" in data and "without_skill" in data


def test_delta_init_requires_skill_path():
    proc = _run_delta(["--init"])
    assert proc.returncode == 1
    assert "--skill-path" in (proc.stderr + proc.stdout)


def test_delta_compare_requires_new_result():
    proc = _run_delta(["--compare"])
    assert proc.returncode == 1


def test_delta_compare_requires_existing_baseline_file():
    proc = _run_delta(["--compare", "--new-result", "/dev/null", "--baseline-file", "/nonexistent/baseline.json"])
    assert proc.returncode == 1


if __name__ == "__main__":
    test_delta_passes_with_pass_rate_only()
    test_delta_fails_token_spike_no_pass_rate_gain()
    test_delta_allows_small_token_increase_with_big_pass_rate_gain()
    test_delta_init_creates_baseline()
    test_delta_init_requires_skill_path()
    test_delta_compare_requires_new_result()
    test_delta_compare_requires_existing_baseline_file()
    print("delta_calculator tests passed")
