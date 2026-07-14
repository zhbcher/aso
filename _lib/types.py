"""_lib/types.py — Strongly typed data classes for ASO.

Replaces bare `Dict[str, Any]` usage throughout the codebase.
Provides type-safe wrappers for evaluation results, candidates, traces, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

# === Evaluation / Benchmark types ===


@dataclass
class MetricValue:
    """A single metric with mean and optional per-value list."""
    mean: float = 0.0
    total: float = 0.0
    values: list[float] = dc_field(default_factory=list)


@dataclass
class BenchmarkResult:
    """Benchmark run result."""
    skill_path: str = ""
    timestamp: str = ""
    total_tests: int = 0
    passed: int = 0
    pass_rate: MetricValue = dc_field(default_factory=MetricValue)
    tokens: MetricValue = dc_field(default_factory=MetricValue)
    time_seconds: MetricValue = dc_field(default_factory=MetricValue)
    tool_call_rate: MetricValue = dc_field(default_factory=MetricValue)
    latency_ms: MetricValue = dc_field(default_factory=MetricValue)
    cost: float = 0.0
    stability: float = 0.0
    test_results: list[dict[str, Any]] = dc_field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkResult:
        return cls(
            skill_path=str(data.get("skill_path", "")),
            timestamp=str(data.get("timestamp", "")),
            total_tests=int(data.get("total_tests", 0)),
            passed=int(data.get("passed", 0)),
            pass_rate=_metric(data.get("pass_rate", {})),
            tokens=_metric(data.get("tokens", {})),
            time_seconds=_metric(data.get("time_seconds", {})),
            tool_call_rate=_metric(data.get("tool_call_rate", {})),
            latency_ms=_metric(data.get("latency_ms", {})),
            cost=float(data.get("cost", 0.0)),
            stability=float(data.get("stability", 0.0)),
            test_results=data.get("test_results", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_path": self.skill_path,
            "timestamp": self.timestamp,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "pass_rate": {"mean": self.pass_rate.mean, "total": self.pass_rate.total},
            "tokens": {"mean": self.tokens.mean, "total": self.tokens.total},
            "time_seconds": {"mean": self.time_seconds.mean, "total": self.time_seconds.total},
            "tool_call_rate": {"mean": self.tool_call_rate.mean, "total": self.tool_call_rate.total},
            "latency_ms": {"mean": self.latency_ms.mean, "total": self.latency_ms.total},
            "cost": self.cost,
            "stability": self.stability,
            "test_results": self.test_results,
        }


def _metric(data: dict[str, Any]) -> MetricValue:
    return MetricValue(
        mean=float(data.get("mean", 0.0)),
        total=float(data.get("total", 0.0)),
        values=[float(v) for v in data.get("values", []) if isinstance(v, (int, float))],
    )


@dataclass
class EvalResult:
    """Single evaluation test result."""
    test_id: str = ""
    output: str = ""
    passed: bool = False
    latency_seconds: float = 0.0
    tokens: int = 0


# === Delta types ===


@dataclass
class DeltaResult:
    """Delta between baseline and candidate benchmark."""
    pass_rate_vs_without: float = 0.0
    pass_rate_vs_old: float = 0.0
    tokens_vs_old_pct: float = 0.0
    time_vs_old_pct: float = 0.0
    tool_call_rate_vs_old: float = 0.0
    latency_ms_vs_old: float = 0.0
    verdict: str = "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_rate_vs_without": self.pass_rate_vs_without,
            "pass_rate_vs_old": self.pass_rate_vs_old,
            "tokens_vs_old_pct": self.tokens_vs_old_pct,
            "time_vs_old_pct": self.time_vs_old_pct,
            "tool_call_rate_vs_old": self.tool_call_rate_vs_old,
            "latency_ms_vs_old": self.latency_ms_vs_old,
            "verdict": self.verdict,
        }


@dataclass
class GateCheck:
    """Single gate check result."""
    name: str = ""
    passed: bool = False
    detail: str = ""


@dataclass
class GateResult:
    """Aggregated gate verification result."""
    passed: bool = False
    total: int = 0
    passed_count: int = 0
    failed_count: int = 0
    checks: list[GateCheck] = dc_field(default_factory=list)
    summary: str = ""


# === Candidate / Mechanism types ===


@dataclass
class MechanismSpec:
    """Optimization mechanism specification."""
    name: str = ""
    category: str = ""  # renamed from 'field' to avoid shadowing
    description: str = ""
    applicable_to: list[str] = dc_field(default_factory=list)
    expected_impact: str = "medium"


@dataclass
class ChangeSpec:
    """Single change within a candidate."""
    action: str = ""
    mechanism: str = ""
    target_module: str = ""
    description: str = ""
    file_path: str = ""
    new_content: str = ""
    operation: str = "replace"


@dataclass
class InterfaceSpec:
    """Interface specification for a mechanism."""
    class_name: str = ""
    constructor_args: list[str] = dc_field(default_factory=list)
    methods: list[dict[str, Any]] = dc_field(default_factory=list)
    description: str = ""


@dataclass
class IntegrationSpec:
    """Integration specification for a mechanism."""
    file: str = ""
    hook_into: str = ""
    import_method: str = ""
    validation: str = ""


@dataclass
class Candidate:
    """Evolution candidate."""
    type: str = "config"
    strategy: str = "aso"
    generator: str = ""
    mechanism: str = ""
    description: str = ""
    changes: list[ChangeSpec] = dc_field(default_factory=list)
    risk: str = "low"
    expected_improvement: str = ""
    review: dict[str, Any] = dc_field(default_factory=dict)


# === Trace types ===


@dataclass
class SkillTrace:
    """Single skill invocation trace."""
    id: str = ""
    version: str = "v1"
    duration_ms: int = 0
    tokens: int = 0
    success: bool = True
    retry_count: int = 0
    error: str | None = None


@dataclass
class AgentTrace:
    """Agent-level trace data."""
    id: str = "agent"
    version: str = "v1"
    success: bool = True
    latency_ms: int = 0


@dataclass
class MemoryTrace:
    """Memory subsystem trace data."""
    hit_rate: float = 0.0
    latency_ms: int = 0


@dataclass
class Trace:
    """Full session trace."""
    task_id: str = ""
    timestamp: str = ""
    source: str = ""
    total_tokens: int = 0
    total_duration_ms: int = 0
    agent: AgentTrace = dc_field(default_factory=AgentTrace)
    skills: list[SkillTrace] = dc_field(default_factory=list)
    memory: MemoryTrace = dc_field(default_factory=MemoryTrace)
    models_used: list[str] = dc_field(default_factory=list)
    tool_call_count: int = 0
    tool_call_success_rate: float = 1.0
    message_count: int = 0


# === Diagnosis types ===


@dataclass
class DimensionScore:
    """Single diagnosis dimension."""
    score: float = 0.0
    trend: str = "stable"
    confidence: float = 0.0


@dataclass
class DiagnosisReport:
    """Full bottleneck diagnosis report."""
    tool_efficiency: DimensionScore = dc_field(default_factory=DimensionScore)
    task_quality: DimensionScore = dc_field(default_factory=DimensionScore)
    skill_success: DimensionScore = dc_field(default_factory=DimensionScore)
    context_utilization: DimensionScore = dc_field(default_factory=DimensionScore)
    priority: list[str] = dc_field(default_factory=list)
    trace_count: int = 0
    analysis_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_efficiency": {"score": self.tool_efficiency.score, "trend": self.tool_efficiency.trend, "confidence": self.tool_efficiency.confidence},
            "task_quality": {"score": self.task_quality.score, "trend": self.task_quality.trend, "confidence": self.task_quality.confidence},
            "skill_success": {"score": self.skill_success.score, "trend": self.skill_success.trend, "confidence": self.skill_success.confidence},
            "context_utilization": {"score": self.context_utilization.score, "trend": self.context_utilization.trend, "confidence": self.context_utilization.confidence},
            "priority": self.priority,
            "trace_count": self.trace_count,
            "analysis_confidence": self.analysis_confidence,
        }


# === Pipeline result types ===


@dataclass
class BudgetUsed:
    """Budget tracking."""
    tokens: int = 0
    time_sec: float = 0.0
    cost: float = 0.0


@dataclass
class PipelineStep:
    """Single pipeline step result."""
    step: str = ""
    status: str = ""
    trace_count: int = 0
    priority: list[str] = dc_field(default_factory=list)
    generator: str = ""
    candidate_type: str = ""
    mechanism: str = ""
    passed_count: int = 0
    failed_count: int = 0
    checks: list[dict[str, Any]] = dc_field(default_factory=list)
    delta: float = 0.0
    verdict: str = ""
    error: str = ""
    valid: bool = False
    reason: str = ""
    target: str = ""


@dataclass
class PipelineResult:
    """Pipeline execution result."""
    pipeline_steps: list[PipelineStep] = dc_field(default_factory=list)
    errors: list[str] = dc_field(default_factory=list)
    success: bool = False
    budget_used: BudgetUsed = dc_field(default_factory=BudgetUsed)
    proposal: dict[str, Any] | None = None


# === Sandbox result types ===


@dataclass
class SandboxResult:
    """Sandbox evaluation result."""
    baseline_score: float = 0.0
    candidate_score: float = 0.0
    delta: float = 0.0
    verdict: str = "unknown"
    reliability: float = 0.0
    runs: int = 0
    budget_used: BudgetUsed = dc_field(default_factory=BudgetUsed)
    error: str | None = None
    details: dict[str, Any] | None = None


# === Bootstrap significance types ===


@dataclass
class BootstrapResult:
    """Bootstrap significance test result."""
    p_value: float = 1.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    diff_mean: float = 0.0
    significant: bool = False
    method: str = "bootstrap"
    n: int = 0
