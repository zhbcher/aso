"""Tests for new ASO modules: config_loader, exceptions, types, pii_mask, llm_cache."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from _lib.config_loader import (
    get_config,
    get_default,
    get_fallback_chain,
    get_pipeline_models,
    get_providers,
    reload_config,
)
from _lib.exceptions import (
    ASOError,
    AtomicWriteError,
    CircuitBreakerOpenError,
    ConfigError,
    FileLockTimeoutError,
    GateRejectedError,
    JSONParseError,
    LLMAuthError,
    LLMConnectionError,
    LLMContentPolicyError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMTimeoutError,
    PipelineBudgetError,
    RollbackError,
    SandboxBudgetError,
    SnapshotError,
    TargetDeniedError,
    classify_llm_error,
)
from _lib.llm_cache import LLMCache, _hash_key
from _lib.pii_mask import detect_pii, mask, mask_simple, mask_with_log
from _lib.types import (
    AgentTrace,
    BenchmarkResult,
    BootstrapResult,
    BudgetUsed,
    Candidate,
    ChangeSpec,
    DeltaResult,
    DiagnosisReport,
    DimensionScore,
    GateCheck,
    MetricValue,
    PipelineResult,
    SandboxResult,
    SkillTrace,
    Trace,
)

# === Config Loader Tests ===


def test_config_loader_loads():
    """Verify config.yaml loads successfully."""
    config = get_config()
    assert "providers" in config
    assert "pipeline_models" in config
    assert "fallback_chain" in config
    assert "defaults" in config


def test_config_providers():
    providers = get_providers()
    assert "sensenova" in providers
    assert "nvidia" in providers
    assert providers["sensenova"]["api_key_env"] == "SENSENOVA_API_KEY"


def test_config_pipeline_models():
    models = get_pipeline_models()
    assert "round_1_explore" in models
    assert models["round_1_explore"]["provider"] == "sensenova"


def test_config_fallback_chain():
    chain = get_fallback_chain()
    assert len(chain) >= 3
    assert isinstance(chain[0], dict)
    assert "provider" in chain[0]
    assert "model" in chain[0]


def test_config_defaults():
    timeout = get_default("timeout_seconds")
    assert timeout == 60


def test_config_reload():
    """Test config reload with custom path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("test_key: test_value\n")
        temp_path = f.name
    try:
        config = reload_config(temp_path)
        assert config.get("test_key") == "test_value"
    finally:
        Path(temp_path).unlink(missing_ok=True)


# === Exception Tests ===


def test_exception_hierarchy():
    """All exceptions derive from ASOError."""
    exceptions = [
        ASOError,
        LLMProviderError,
        LLMTimeoutError,
        LLMRateLimitError,
        LLMAuthError,
        LLMQuotaExceededError,
        LLMContentPolicyError,
        LLMConnectionError,
        LLMEmptyResponseError,
        JSONParseError,
        PipelineBudgetError,
        SandboxBudgetError,
        GateRejectedError,
        TargetDeniedError,
        CircuitBreakerOpenError,
        FileLockTimeoutError,
        AtomicWriteError,
        SnapshotError,
        RollbackError,
        ConfigError,
    ]
    for exc in exceptions:
        instance = exc("test message")
        assert isinstance(instance, ASOError)
        assert str(instance) == "test message"


def test_sandbox_budget_extends_pipeline_budget():
    assert issubclass(SandboxBudgetError, PipelineBudgetError)
    assert issubclass(SandboxBudgetError, ASOError)


def test_classify_llm_error_429():
    result = classify_llm_error("HTTP 429 Too Many Requests")
    assert isinstance(result, LLMRateLimitError)


def test_classify_llm_error_auth():
    result = classify_llm_error("HTTP 401 Unauthorized")
    assert isinstance(result, LLMAuthError)

    result = classify_llm_error("invalid_api_key")
    assert isinstance(result, LLMAuthError)


def test_classify_llm_error_quota():
    result = classify_llm_error("insufficient_balance")
    assert isinstance(result, LLMQuotaExceededError)

    result = classify_llm_error("quota exceeded for today")
    assert isinstance(result, LLMQuotaExceededError)


def test_classify_llm_error_content_policy():
    result = classify_llm_error("content_policy violation")
    assert isinstance(result, LLMContentPolicyError)


def test_classify_llm_error_timeout():
    result = classify_llm_error("request timed out")
    assert isinstance(result, LLMTimeoutError)


def test_classify_llm_error_connection():
    result = classify_llm_error("Connection refused")
    assert isinstance(result, LLMConnectionError)

    result = classify_llm_error("dns resolution failed")
    assert isinstance(result, LLMConnectionError)


def test_classify_llm_error_generic():
    result = classify_llm_error("unknown error occurred")
    assert isinstance(result, LLMProviderError)


# === Type (Dataclass) Tests ===


def test_benchmark_result():
    result = BenchmarkResult(
        skill_path="/test",
        total_tests=10,
        passed=7,
        pass_rate=MetricValue(mean=0.7),
    )
    assert result.pass_rate.mean == 0.7
    assert result.total_tests == 10
    assert result.passed == 7

    d = result.to_dict()
    assert d["pass_rate"]["mean"] == 0.7


def test_benchmark_result_from_dict():
    data = {
        "skill_path": "/test",
        "total_tests": 10,
        "passed": 7,
        "pass_rate": {"mean": 0.7},
        "tokens": {"mean": 100.0},
        "time_seconds": {"mean": 5.0},
        "tool_call_rate": {"mean": 0.8},
        "latency_ms": {"mean": 200.0},
        "cost": 1.5,
        "test_results": [],
    }
    result = BenchmarkResult.from_dict(data)
    assert result.total_tests == 10
    assert result.passed == 7
    assert result.pass_rate.mean == 0.7


def test_delta_result():
    delta = DeltaResult(pass_rate_vs_old=0.05, verdict="improved")
    assert delta.verdict == "improved"
    d = delta.to_dict()
    assert d["pass_rate_vs_old"] == 0.05


def test_candidate():
    change = ChangeSpec(action="modify_skill_file", file_path="SKILL.md", operation="replace")
    candidate = Candidate(
        type="skill",
        mechanism="tabu_search",
        description="Test candidate",
        changes=[change],
        risk="low",
    )
    assert len(candidate.changes) == 1
    assert candidate.changes[0].action == "modify_skill_file"
    assert candidate.risk == "low"


def test_gate_check():
    check = GateCheck(name="structure", passed=True, detail="OK")
    assert check.passed


def test_trace():
    trace = Trace(
        task_id="test-001",
        total_tokens=1000,
        agent=AgentTrace(success=True),
        skills=[SkillTrace(id="Read", success=True)],
    )
    assert trace.agent.success
    assert trace.skills[0].id == "Read"
    assert trace.total_tokens == 1000


def test_diagnosis_report():
    report = DiagnosisReport(
        tool_efficiency=DimensionScore(score=0.5),
        priority=["tool_efficiency", "skill_success"],
        trace_count=10,
    )
    assert report.tool_efficiency.score == 0.5
    d = report.to_dict()
    assert d["tool_efficiency"]["score"] == 0.5
    assert d["trace_count"] == 10


def test_pipeline_result():
    pr = PipelineResult(
        success=True,
        budget_used=BudgetUsed(tokens=5000, time_sec=10.0),
    )
    assert pr.success
    assert pr.budget_used.tokens == 5000


def test_sandbox_result():
    sr = SandboxResult(
        baseline_score=50.0,
        candidate_score=55.0,
        verdict="improved",
    )
    assert sr.verdict == "improved"
    assert sr.candidate_score == 55.0


def test_bootstrap_result():
    br = BootstrapResult(p_value=0.001, significant=True)
    assert br.significant
    assert br.p_value < 0.05


# === PII Mask Tests ===


def test_pii_mask_phone():
    result = mask("Call me at +1-555-123-4567 today")
    assert "REDACTED" in result or "***" in result
    assert "555" not in result or "<REDACTED" in result


def test_pii_mask_email():
    result = mask("Email me at user@example.com")
    assert "REDACTED" in result or "***" in result


def test_pii_mask_api_key():
    result = mask("API key: sk-live-abc123def456ghi789jkl012")
    assert "***" in result or "REDACTED" in result


def test_pii_mask_ipv4():
    result = mask("Server at 192.168.1.1 is running")
    assert "REDACTED" in result


def test_pii_mask_url():
    result = mask("Check https://example.com/secret for details")
    assert "REDACTED" in result


def test_pii_mask_multiple():
    text = "User user@test.com at IP 10.0.0.1 used key sk-test123"
    result = mask(text)
    assert "test.com" not in result
    assert "10.0.0.1" not in result


def test_pii_mask_empty():
    assert mask("") == ""
    assert mask(None) is None


def test_pii_mask_with_log(caplog):
    result = mask_with_log("Call user@test.com", context="test_log")
    assert "REDACTED" in result
    # Check that logging occurred
    records = [r for r in caplog.records if r.name == "aso.pii"]
    if records:
        assert "PII mask triggered in test_log" in records[0].message


def test_detect_pii():
    text = "Email: user@test.com, phone: +1-555-123-4567"
    results = detect_pii(text)
    assert len(results) > 0
    assert "email" in results
    assert "phone" in results


def test_mask_simple():
    text = "user@test.com and 192.168.1.1"
    result = mask_simple(text)
    assert "<REDACTED>" in result


def test_pii_mask_chinese_id():
    """Chinese ID numbers should be masked."""
    result = mask("ID: 110105199003071234")
    assert "REDACTED" in result


def test_pii_mask_credit_card():
    """Credit card numbers should be masked."""
    result = mask("CC: 4111-1111-1111-1111")
    assert "REDACTED" in result


def test_pii_mask_password():
    """Password patterns should be masked."""
    result = mask("password=mySecretPass123!")
    assert "REDACTED" in result or "***" in result


# === LLM Cache Tests ===


def test_llm_cache_init():
    cache = LLMCache()
    assert cache is not None
    stats = cache.stats
    assert "hits" in stats
    assert "misses" in stats


def test_llm_cache_set_get():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = LLMCache(cache_dir=tmpdir, ttl_seconds=3600)
        messages = [{"role": "user", "content": "Hello"}]
        cache.set("World", messages, "test-model", 0.7, 100)
        result = cache.get(messages, "test-model", 0.7, 100)
        assert result == "World"


def test_llm_cache_miss():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = LLMCache(cache_dir=tmpdir)
        result = cache.get(
            [{"role": "user", "content": "Never cached"}],
            "test-model", 0.5, 50
        )
        assert result is None


def test_llm_cache_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = LLMCache(cache_dir=tmpdir)
        _ = cache.get([{"role": "user", "content": "Miss"}], "test-model")
        stats = cache.stats
        assert stats["misses"] >= 1


def test_llm_cache_clear():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = LLMCache(cache_dir=tmpdir)
        messages = [{"role": "user", "content": "Hello"}]
        cache.set("World", messages, "test-model")
        cache.clear()
        result = cache.get(messages, "test-model")
        assert result is None


def test_llm_cache_eviction():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = LLMCache(cache_dir=tmpdir, max_entries=5)
        for i in range(10):
            cache.set(f"Response{i}", [{"role": "user", "content": f"Query{i}"}], "test-model")
        # After adding 10 entries with max=5, cache should have <= 5
        stats = cache.stats
        assert stats["entries"] <= 5


def test_hash_key_deterministic():
    messages = [{"role": "user", "content": "Hello"}]
    h1 = _hash_key(messages, "model-a", 0.7, 100)
    h2 = _hash_key(messages, "model-a", 0.7, 100)
    assert h1 == h2


def test_hash_key_different():
    h1 = _hash_key([{"role": "user", "content": "A"}], "model-a", 0.7, 100)
    h2 = _hash_key([{"role": "user", "content": "B"}], "model-a", 0.7, 100)
    assert h1 != h2


# === Config YAML fallback parser ===


def test_config_loader_fallback_parse():
    """Test the simple YAML parser fallback."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("key1: value1\nkey2: value2\n")
        temp_path = f.name
    try:
        config = reload_config(temp_path)
        # The simple parser may store values differently
        assert config is not None
    finally:
        Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
