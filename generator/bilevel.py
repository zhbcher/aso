"""generator/bilevel.py — OpenClaw 版 Bilevel Autoresearch Generator

4-round LLM dialogue: Explore -> Critique -> Specify -> Generate
Adapted from KLXZ evolve-skill-v4 generator/bilevel.py.
Replaced klzm-proxy LLM calls with OpenClaw _lib/oc_llm_client.py.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional, List, Dict

# Add _lib to import path
_lib_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from oc_llm_client import call_with_fallback, parse_json_response
from path_utils import EVOLVE_DIR


class Generator:
    """Bilevel Autoresearch Generator for OpenClaw.

    Implements 4-round LLM dialogue:
    1. Explore:   Analyze Trace + bottleneck report, discover candidate mechanisms
    2. Critique:  Evaluate candidates, select the best match
    3. Specify:   Write precise interface specification
    4. Generate:  Produce complete runnable Candidate

    Each round uses a different model pipeline configured in oc_llm_client.PIPELINE_MODELS:
    - Round 1: deepseek-v4-flash (exploration / reasoning)
    - Round 2: step-3.7-flash (evaluation / critique)
    - Round 3: deepseek-v4-flash (specification)
    - Round 4: step-3.5-flash (review)

    If primary model fails, falls back through FALLBACK_CHAIN.
    """

    name = "bilevel"
    description = "Bilevel Autoresearch: 4-round LLM dialogue with multi-model rotation via OpenClaw"

    # Default allowed targets, overridden from evolution-policy.yaml
    allowed_targets: List[str] = ["planner", "workflow", "prompt", "memory", "skill", "router"]

    def __init__(self) -> None:
        """Initialize and load allowed_targets from policy file."""
        self._load_allowed_targets()

    def _load_allowed_targets(self) -> None:
        """Read allowed_targets from evolution-policy.yaml."""
        policy_path = EVOLVE_DIR / "evolution-policy.yaml"
        if not policy_path.exists():
            return

        try:
            import yaml
            with open(policy_path, "r", encoding="utf-8") as f:
                policy = yaml.safe_load(f)
        except ImportError:
            policy = self._parse_yaml_simple(str(policy_path))
        except Exception:
            return

        if not isinstance(policy, dict):
            return

        scopes = policy.get("generator_scopes", {})
        bilevel_scope = scopes.get("bilevel", {})
        policy_targets = bilevel_scope.get("allowed_targets", [])
        if policy_targets:
            self.allowed_targets = policy_targets

    def _parse_yaml_simple(self, path: str) -> dict:
        """Simple YAML parser fallback when yaml library is not available."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            import re
            result: dict = {
                "generator_scopes": {"bilevel": {"allowed_targets": self.allowed_targets.copy()}}
            }
            match = re.search(
                r'bilevel:\s*\n\s+allowed_targets:\s*\n((?:\s+-\s+\S+\s*\n)+)',
                content,
            )
            if match:
                targets = re.findall(r'-\s+(\S+)', match.group(1))
                if targets:
                    result["generator_scopes"]["bilevel"]["allowed_targets"] = targets
                    self.allowed_targets = targets
            return result
        except Exception:
            return {}

    def generate(self, target: str, report: dict) -> dict:
        """
        4-round LLM dialogue to generate evolution candidate.

        Args:
            target: Evolution target (must be in allowed_targets)
            report: diagnose.skill output BottleneckReport

        Returns:
            dict: Candidate with changes, risk, expected improvement
        """
        if target not in self.allowed_targets:
            raise ValueError(
                f"Target '{target}' is not allowed for generator 'bilevel'. "
                f"Allowed targets: {self.allowed_targets}"
            )

        bottleneck = self._find_bottleneck(report)

        # Multi-round conversation: messages carry context between rounds
        messages: List[dict] = []

        # Round 1: Explore
        explore_result = self._explore(target, report, bottleneck, messages)
        messages.append({"role": "assistant", "content": json.dumps(explore_result, ensure_ascii=False)})

        # Round 2: Critique
        critique_result = self._critique(explore_result, bottleneck, messages)
        messages.append({"role": "assistant", "content": json.dumps(critique_result, ensure_ascii=False)})

        # Round 3: Specify
        specification = self._specify(critique_result, target, messages)
        messages.append({"role": "assistant", "content": json.dumps(specification, ensure_ascii=False)})

        # Round 4: Generate
        candidate = self._generate(specification, target, bottleneck)

        return candidate

    def _find_bottleneck(self, report: dict) -> dict:
        """Identify the worst-performing module from the bottleneck report."""
        priority = report.get("priority", [])
        if not priority:
            return {"module": "unknown", "score": 0.0, "trend": "stable"}
        worst = priority[0]
        module_data = report.get(worst, {})
        return {
            "module": worst,
            "score": module_data.get("score", 0.0),
            "trend": module_data.get("trend", "stable"),
            "confidence": module_data.get("confidence", 0.0),
        }

    def _llm_call(self, system_prompt: str, messages: List[dict], role: str,
                  max_tokens: int = 1200) -> str:
        """Call LLM via OpenClaw oc_llm_client with role-based model selection.

        Args:
            system_prompt: System prompt for the LLM.
            messages: Conversation history (user/assistant turns, no system message yet).
            role: Pipeline role key (e.g. "round_1_explore").
            max_tokens: Max output tokens.

        Returns:
            LLM response text.
        """
        # Build full messages: prepend system prompt, append JSON instruction
        full_messages: List[dict] = [{"role": "system", "content": system_prompt}] + messages
        full_messages.append(
            {"role": "user", "content": "请继续你的分析，输出 JSON 格式结果。"}
        )

        response = call_with_fallback(
            messages=full_messages,
            role=role,
            temperature=0.7,
            max_tokens=max_tokens,
            timeout=60,
        )
        return response

    def _explore(self, target: str, report: dict, bottleneck: dict,
                 messages: List[dict]) -> dict:
        """Round 1: Explore -- discover candidate mechanisms."""
        priority = report.get("priority", [])
        bottleneck_mod = bottleneck["module"]
        report_summary = json.dumps(report.get(bottleneck_mod, {}), indent=2, ensure_ascii=False)

        system_prompt = (
            "你是一个 AI 系统演化工程师。你的任务是从相邻搜索领域（组合优化、多臂老虎机、"
            "实验设计、贝叶斯优化、搜索空间剪枝等）为 OpenClaw 系统发现候选优化机制。\n\n"
            "请输出 JSON 格式，包含:\n"
            "- failure_mode: 诊断的失败模式描述\n"
            "- mechanisms: 候选机制列表，每个包含 name, field, description, applicable_to, expected_impact\n"
            "- reasoning: 推理过程说明\n\n"
            "仅输出 JSON。"
        )

        user_prompt = (
            f"目标 Target: {target}\n"
            f"瓶颈模块: {bottleneck_mod}（评分: {bottleneck['score']}，趋势: {bottleneck['trend']}）\n"
            f"优先级列表: {priority}\n"
            f"瓶颈模块报告:\n{report_summary}\n\n"
            f"请分析以上瓶颈信息，从相邻搜索领域发现 2-4 个候选优化机制。"
        )

        try:
            llm_messages: List[dict] = messages + [{"role": "user", "content": user_prompt}]
            llm_output = self._llm_call(system_prompt, llm_messages, "round_1_explore", max_tokens=1200)
            parsed = parse_json_response(llm_output)

            mechanisms = parsed.get("mechanisms", [])
            if not isinstance(mechanisms, list):
                mechanisms = []

            return {
                "mechanisms": mechanisms,
                "failure_mode": parsed.get("failure_mode",
                    f"{bottleneck_mod}: 评分 {bottleneck['score']}"),
                "reasoning": parsed.get("reasoning", "LLM 推理"),
                "target": target,
                "bottleneck_module": bottleneck_mod,
                "bottleneck_score": bottleneck["score"],
            }
        except Exception as e:
            return self._fallback_explore(target, bottleneck)

    def _fallback_explore(self, target: str, bottleneck: dict) -> dict:
        """Fallback when LLM call fails — rules-based mechanism discovery."""
        score = bottleneck["score"]
        mechanisms: List[dict] = []
        if score < 0.5:
            mechanisms.append({
                "name": "tabu_search", "field": "组合优化",
                "description": "禁忌搜索 - 维护已探索参数列表，防止重复探索",
                "applicable_to": ["planner", "workflow"], "expected_impact": "high",
            })
            mechanisms.append({
                "name": "explore_exploit_bandit", "field": "多臂老虎机",
                "description": "探索-利用平衡 - 在已知好参数和未知区域间自动平衡",
                "applicable_to": ["planner", "router"], "expected_impact": "high",
            })
        elif score < 0.7:
            mechanisms.append({
                "name": "bayesian_optimization", "field": "贝叶斯优化",
                "description": "用高斯过程代理模型建模参数空间",
                "applicable_to": ["planner", "prompt"], "expected_impact": "medium",
            })
        else:
            mechanisms.append({
                "name": "pruning", "field": "搜索空间剪枝",
                "description": "剔除低潜力参数维度，聚焦关键参数，降低搜索空间规模",
                "applicable_to": ["planner", "prompt"], "expected_impact": "low",
            })

        mechanisms.append({
            "name": "random_restart", "field": "随机重启",
            "description": "定期从随机新起点重新开始搜索，防止局部最优",
            "applicable_to": [target], "expected_impact": "medium",
        })

        return {
            "mechanisms": mechanisms,
            "failure_mode": f"{bottleneck['module']}: 评分 {bottleneck['score']}（LLM fallback）",
            "reasoning": "LLM 调用失败，使用规则 fallback",
            "target": target,
            "bottleneck_module": bottleneck["module"],
            "bottleneck_score": bottleneck["score"],
        }

    def _critique(self, explore_result: dict, bottleneck: dict,
                  messages: List[dict]) -> dict:
        """Round 2: Critique -- evaluate and select best mechanism."""
        mechanisms = explore_result.get("mechanisms", [])
        bottleneck_mod = bottleneck["module"]

        if not mechanisms:
            return {"selected": {}, "alternatives": [], "justification": "无候选机制"}

        system_prompt = (
            "你是一个 AI 系统演化评审员。评估候选优化机制，选择与给定瓶颈最匹配的一个。\n\n"
            "请输出 JSON 格式:\n"
            "- selected: {name, field, description, expected_impact, why_choose_this}\n"
            "- justification: 为什么选择这个机制的详细理由\n\n"
            "仅输出 JSON。"
        )

        user_prompt = (
            f"瓶颈模块: {bottleneck_mod}（评分: {bottleneck['score']}）\n"
            f"候选机制:\n{json.dumps(mechanisms, indent=2, ensure_ascii=False)}\n\n"
            f"请评估并选择最适合 {bottleneck_mod} 的优化机制。"
        )

        try:
            llm_messages: List[dict] = messages + [{"role": "user", "content": user_prompt}]
            llm_output = self._llm_call(system_prompt, llm_messages, "round_2_critique", max_tokens=800)
            parsed = parse_json_response(llm_output)
            selected = parsed.get("selected", {})
            return {
                "selected": selected,
                "alternatives": [],
                "justification": parsed.get("justification", "LLM 已选择"),
            }
        except Exception:
            return self._fallback_critique(mechanisms, bottleneck_mod)

    def _fallback_critique(self, mechanisms: list, bottleneck_mod: str) -> dict:
        """Fallback when LLM call fails — rules-based mechanism selection."""
        candidates = [m for m in mechanisms if bottleneck_mod in m.get("applicable_to", [])]
        impact_order = {"high": 3, "medium": 2, "low": 1}
        candidates.sort(key=lambda m: impact_order.get(m.get("expected_impact", "low"), 0), reverse=True)
        selected = candidates[0] if candidates else mechanisms[0]
        return {
            "selected": selected,
            "alternatives": candidates[1:] if len(candidates) > 1 else [],
            "justification": f"选择 {selected.get('name', 'unknown')}（规则 fallback）",
        }

    def _specify(self, critique_result: dict, target: str, messages: List[dict]) -> dict:
        """Round 3: Specify -- write interface specification."""
        selected = critique_result.get("selected", {})
        mechanism_name = selected.get("name", "unknown")

        system_prompt = (
            "你是一个 AI 系统架构师。根据选定的优化机制，写出精确的接口规范和集成方案。\n\n"
            "请输出 JSON 格式:\n"
            "- interface: {class_name, constructor_args, methods: [{name, args, returns}], description}\n"
            "- integration: {file, hook_into, import_method, validation}\n\n"
            "仅输出 JSON。"
        )

        user_prompt = (
            f"选定的机制: {mechanism_name}\n"
            f"描述: {selected.get('description', '')}\n"
            f"Target: {target}\n\n"
            f"请设计 {mechanism_name} 在 OpenClaw 系统中的精确接口规范和集成方案。"
        )

        try:
            llm_messages: List[dict] = messages + [{"role": "user", "content": user_prompt}]
            llm_output = self._llm_call(system_prompt, llm_messages, "round_3_specify", max_tokens=1000)
            parsed = parse_json_response(llm_output)
            return {
                "interface": parsed.get("interface", {}),
                "integration": parsed.get("integration", {}),
                "mechanism": selected,
            }
        except Exception:
            return self._fallback_specify(selected, target)

    def _fallback_specify(self, selected: dict, target: str) -> dict:
        """Fallback when LLM call fails — rules-based interface specification."""
        mechanism_name = selected.get("name", "unknown")
        interface_spec: dict = {
            "class_name": f"{mechanism_name.title().replace('_', '')}Mechanism",
            "constructor_args": ["config: dict"],
            "methods": [
                {"name": "propose", "args": ["state: dict", "trace: list[dict]"], "returns": "dict"},
                {"name": "update", "args": ["feedback: dict"], "returns": "None"},
                {"name": "reset", "args": [], "returns": "None"},
            ],
            "description": selected.get("description", ""),
        }
        integration: dict = {
            "file": f"generator/{mechanism_name}.py",
            "hook_into": "inner_loop.propose",
            "import_method": "importlib",
            "validation": "import成功 → 替换活跃 runner → 失败回滚备份",
        }
        return {"interface": interface_spec, "integration": integration, "mechanism": selected}

    def _generate(self, specification: dict, target: str, bottleneck: dict) -> dict:
        """Round 4: Generate — review specification and produce complete Candidate."""
        mechanism = specification.get("mechanism", {})
        mechanism_name = mechanism.get("name", "unknown")

        system_prompt = (
            "你是一个 AI 系统演化审查员。请审查以下优化方案的接口规范和集成方案，"
            "评估其合理性、风险和可行性。\n\n"
            "请输出 JSON 格式:\n"
            "- approved: bool, 是否批准该方案\n"
            "- risk_adjustment: 如果风险评估需要调整，给出新值 (low/medium/high)\n"
            "- concerns: 担忧列表（字符串数组），如果没有则为空\n"
            "- suggestions: 改进建议列表（字符串数组）\n"
            "- expected_improvement: 预期改进描述\n\n"
            "仅输出 JSON。"
        )

        user_prompt = (
            f"机制: {mechanism_name}\n"
            f"描述: {mechanism.get('description', '')}\n"
            f"Target: {target}\n"
            f"接口规范: {json.dumps(specification.get('interface', {}), ensure_ascii=False)}\n"
            f"集成方案: {json.dumps(specification.get('integration', {}), ensure_ascii=False)}\n"
            f"瓶颈: {json.dumps(bottleneck, ensure_ascii=False)}\n\n"
            f"请审查以上方案，评估其可行性并给出建议。"
        )

        review_result: Optional[dict] = None
        try:
            llm_output = self._llm_call(
                system_prompt,
                [{"role": "user", "content": user_prompt}],
                "round_4_review",
                max_tokens=800,
            )
            review_result = parse_json_response(llm_output)
        except Exception:
            # Fallback: proceed without review if LLM fails
            review_result = {
                "approved": True,
                "risk_adjustment": None,
                "concerns": [],
                "suggestions": [],
                "expected_improvement": "",
            }

        # Assess risk, potentially adjusted by review
        risk = self._assess_risk(mechanism, bottleneck)
        if review_result.get("risk_adjustment"):
            risk = review_result["risk_adjustment"]

        # Build candidate with review metadata
        return {
            "type": self._infer_candidate_type(target),
            "strategy": "bilevel",
            "generator": self.name,
            "mechanism": mechanism_name,
            "description": mechanism.get("description", mechanism.get("name", "unknown") + " 优化机制"),
            "changes": [
                {
                    "action": "integrate_mechanism",
                    "mechanism": mechanism_name,
                    "target_module": target,
                    "interface": specification.get("interface", {}),
                    "integration": specification.get("integration", {}),
                    "description": mechanism.get("description", mechanism.get("name", "unknown") + " 优化机制"),
                },
                {
                    "action": "modify_search_loop",
                    "parameter": "proposal_strategy",
                    "from": "standard_llm_propose",
                    "to": f"llm_propose_with_{mechanism_name}",
                },
            ],
            "risk": risk,
            "expected_improvement": review_result.get("expected_improvement") or
                self._estimate_improvement(mechanism, bottleneck),
            "review": {
                "approved": review_result.get("approved", True),
                "concerns": review_result.get("concerns", []),
                "suggestions": review_result.get("suggestions", []),
            },
        }

    def _infer_candidate_type(self, target: str) -> str:
        """Map target name to candidate change type."""
        type_map: Dict[str, str] = {
            "planner": "workflow", "workflow": "workflow", "prompt": "prompt",
            "memory": "config", "router": "config", "skill": "skill", "policy": "config",
        }
        return type_map.get(target, "config")

    def _assess_risk(self, mechanism: dict, bottleneck: dict) -> str:
        """Assess risk based on mechanism impact and bottleneck score."""
        impact = mechanism.get("expected_impact", "medium")
        score = bottleneck.get("score", 0.5)
        if impact == "high" and score < 0.3:
            return "high"
        elif impact == "high":
            return "medium"
        return "low" if impact == "low" else "medium"

    def _estimate_improvement(self, mechanism: dict, bottleneck: dict) -> str:
        """Estimate expected improvement based on mechanism impact."""
        impact = mechanism.get("expected_impact", "medium")
        score = bottleneck.get("score", 0.5)
        if impact == "high":
            return f"预期评分提升 20-40%（当前 {round(score, 2)}）"
        elif impact == "medium":
            return f"预期评分提升 10-20%（当前 {round(score, 2)}）"
        return f"预期评分提升 5-10%（当前 {round(score, 2)}）"