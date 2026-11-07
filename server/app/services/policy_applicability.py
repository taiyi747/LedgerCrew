"""政策规则适用性判断的通用框架（机制，不是政策）。

BE2-10-09。DEC-002～005、DEC-011 均为 pending：本模块**不含任何真实地区、主体、
纳税人身份、税率或表单值**，只对调用方传入的规则结构做确定性的适用性判定。
synthetic 值仅用于测试与结构验证，不得升格为真实政策。

边界（与 ``policy_template_preview`` 一致）：

- 不持久化、不建表、不迁移、不挂载 API；BE2-05/06 的正式 PolicySource/PolicyRule
  模型、审核 Service 与计算服务不存在，本模块不能替代它们。
- 不默认选择最新规则；未审核规则不得进入正式计算；缺失纳税人身份不猜测；
  缺失适用规则不给零税率；无任何 AI/LLM 参与，参数只逐字回显规则声明值。
- 判定过程纯函数、固定顺序，同一输入必然产生同一结果（含 decision_hash）。

判定门（按固定顺序，逐条给出阻塞码）：
``source -> approved -> required conditions -> region/entity/identity/filing kind
-> period -> supported scope -> conflicts``。
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RuleStatus = Literal["candidate", "under_review", "approved", "rejected", "retired"]
SourceStatus = Literal["candidate", "verified", "unavailable", "retired"]
ScopeStatus = Literal["draft", "verified", "active", "retired"]

# 必要适用条件：缺失即阻塞，不猜测、不补默认值
REQUIRED_CONDITIONS = ("region_code", "entity_type", "filing_kind", "effective_from")


class PolicySourceState(BaseModel):
    """规则来源状态（来源明确性检查用）。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    status: SourceStatus
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PolicyRuleInput(BaseModel):
    """一条规则的适用性判定输入；``None``/空白表示该适用条件缺失。"""

    model_config = ConfigDict(extra="forbid")

    rule_key: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    region_code: str | None = None
    entity_type: str | None = None
    taxpayer_identity: str | None = None
    filing_kind: str | None = None
    form_version: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    status: RuleStatus
    parameters: dict[str, str] = Field(default_factory=dict)
    conflicts_with: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_window(self):
        if self.effective_from is not None and self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        return self


class MerchantProfileInput(BaseModel):
    """申报主体适用条件（商户税务档案的适用性视图）。"""

    model_config = ConfigDict(extra="forbid")

    region_code: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    taxpayer_identity: str | None = None


class FilingPeriodInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: date
    period_end: date

    @model_validator(mode="after")
    def valid_range(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end precedes period_start")
        return self


class SupportedScopeInput(BaseModel):
    """申报任务所属支持范围的适用性视图。"""

    model_config = ConfigDict(extra="forbid")

    region_code: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    taxpayer_identity: str | None = None
    filing_kind: str = Field(min_length=1)
    form_version: str | None = None
    status: ScopeStatus


class ApplicabilityContext(BaseModel):
    """一次适用性判断的申报任务上下文。"""

    model_config = ConfigDict(extra="forbid")

    profile: MerchantProfileInput
    period: FilingPeriodInput
    filing_kind: str = Field(min_length=1)
    scope: SupportedScopeInput | None = None


class ApplicabilityBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    rule_key: str | None = None
    rule_version: str | None = None
    condition: str | None = None


class RuleEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_key: str
    rule_version: str
    applicable: bool
    reasons: list[str] = Field(default_factory=list)


class ApplicabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["applicable", "blocked"]
    rule_key: str | None = None
    rule_version: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    blockers: list[ApplicabilityBlocker] = Field(default_factory=list)
    evaluated_rules: list[RuleEvaluation] = Field(default_factory=list)
    decision_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _blocker(code: str, message: str, rule: PolicyRuleInput | None = None, condition: str | None = None) -> ApplicabilityBlocker:
    return ApplicabilityBlocker(
        code=code,
        message=message,
        rule_key=rule.rule_key if rule else None,
        rule_version=rule.rule_version if rule else None,
        condition=condition,
    )


def _condition_missing(rule: PolicyRuleInput) -> str | None:
    for name in REQUIRED_CONDITIONS:
        value = getattr(rule, name)
        if value is None or (isinstance(value, str) and not value.strip()):
            return name
    return None


def _check_rule(
    rule: PolicyRuleInput,
    context: ApplicabilityContext,
    sources: Mapping[str, PolicySourceState],
) -> list[ApplicabilityBlocker]:
    """逐门检查单条规则；返回全部阻塞原因（空表示该规则通过所有门）。"""
    blockers: list[ApplicabilityBlocker] = []

    # 1. 来源明确：必须引用已知且已核验的来源
    if not rule.source_ids:
        blockers.append(_blocker("source_missing", f"rule {rule.rule_key}@{rule.rule_version} declares no policy source", rule))
    for source_id in rule.source_ids:
        source = sources.get(source_id)
        if source is None:
            blockers.append(_blocker("source_missing", f"rule {rule.rule_key}@{rule.rule_version} references unknown source {source_id}", rule))
        elif source.status != "verified":
            blockers.append(_blocker("source_not_verified", f"source {source_id} is '{source.status}', not verified", rule))

    # 2. 规则已审核：只有 approved 可进入正式计算
    if rule.status != "approved":
        blockers.append(_blocker("rule_not_approved", f"rule {rule.rule_key}@{rule.rule_version} has status '{rule.status}'", rule))

    # 3. 必要适用条件完整
    missing = _condition_missing(rule)
    if missing is not None:
        blockers.append(_blocker("missing_required_condition", f"rule {rule.rule_key}@{rule.rule_version} lacks required condition '{missing}'", rule, condition=missing))

    # 4. 适用条件逐项比对（条件缺失时跳过比对，不做猜测）
    if rule.region_code is not None and rule.region_code.strip() and rule.region_code != context.profile.region_code:
        blockers.append(_blocker("region_mismatch", f"rule region '{rule.region_code}' != profile region '{context.profile.region_code}'", rule))
    if rule.entity_type is not None and rule.entity_type.strip() and rule.entity_type != context.profile.entity_type:
        blockers.append(_blocker("entity_type_mismatch", f"rule entity '{rule.entity_type}' != profile entity '{context.profile.entity_type}'", rule))
    if rule.taxpayer_identity is not None and rule.taxpayer_identity != context.profile.taxpayer_identity:
        blockers.append(_blocker("taxpayer_identity_mismatch", "rule taxpayer identity does not match profile taxpayer identity", rule))
    if rule.filing_kind is not None and rule.filing_kind.strip() and rule.filing_kind != context.filing_kind:
        blockers.append(_blocker("filing_kind_mismatch", f"rule filing kind '{rule.filing_kind}' != task filing kind '{context.filing_kind}'", rule))

    # 5. 所属期适用：必须完全落在规则生效区间内，跨界即阻塞
    if rule.effective_from is not None:
        if context.period.period_end < rule.effective_from:
            blockers.append(_blocker("period_before_effective", "filing period ends before the rule becomes effective", rule))
        elif rule.effective_to is not None and context.period.period_start > rule.effective_to:
            blockers.append(_blocker("period_after_effective", "filing period starts after the rule expires", rule))
        elif context.period.period_start < rule.effective_from or (
            rule.effective_to is not None and context.period.period_end > rule.effective_to
        ):
            blockers.append(_blocker("period_crosses_effective_boundary", "filing period crosses the rule effective boundary", rule))

    # 6. 支持范围匹配
    scope = context.scope
    if scope is not None:
        if rule.region_code is not None and rule.region_code.strip() and rule.region_code != scope.region_code:
            blockers.append(_blocker("scope_mismatch", "rule region does not match the supported scope", rule))
        if rule.entity_type is not None and rule.entity_type.strip() and rule.entity_type != scope.entity_type:
            blockers.append(_blocker("scope_mismatch", "rule entity type does not match the supported scope", rule))
        if rule.filing_kind is not None and rule.filing_kind.strip() and rule.filing_kind != scope.filing_kind:
            blockers.append(_blocker("scope_mismatch", "rule filing kind does not match the supported scope", rule))
        if rule.form_version is not None and scope.form_version is not None and rule.form_version != scope.form_version:
            blockers.append(_blocker("scope_mismatch", "rule form version is outside the supported scope", rule))

    return blockers


def _check_scope_state(context: ApplicabilityContext) -> list[ApplicabilityBlocker]:
    """支持范围本身必须覆盖申报任务，否则整体阻塞。"""
    scope = context.scope
    if scope is None:
        return []
    mismatches = (
        scope.status not in ("verified", "active"),
        scope.region_code != context.profile.region_code,
        scope.entity_type != context.profile.entity_type,
        scope.filing_kind != context.filing_kind,
        scope.taxpayer_identity is not None and scope.taxpayer_identity != context.profile.taxpayer_identity,
    )
    if any(mismatches):
        return [_blocker("scope_not_supported", "supported scope does not cover this filing task or is not usable")]
    return []


def _check_conflicts(candidates: Sequence[PolicyRuleInput]) -> dict[tuple[str, str], list[ApplicabilityBlocker]]:
    """冲突检查：显式冲突、同键多版本、多条未声明关系的适用规则一律阻塞。"""
    result: dict[tuple[str, str], list[ApplicabilityBlocker]] = {}
    keys = {rule.rule_key for rule in candidates}
    by_key: dict[str, list[PolicyRuleInput]] = {}
    for rule in candidates:
        by_key.setdefault(rule.rule_key, []).append(rule)
        if keys & set(rule.conflicts_with):
            result.setdefault((rule.rule_key, rule.rule_version), []).append(
                _blocker("rule_conflict", f"rule {rule.rule_key}@{rule.rule_version} conflicts with another applicable rule", rule)
            )
    for rule_key, group in by_key.items():
        if len(group) > 1:
            for rule in group:
                result.setdefault((rule.rule_key, rule.rule_version), []).append(
                    _blocker("rule_version_conflict", f"multiple versions of '{rule_key}' apply; selecting the newest is forbidden", rule)
                )
    if len(candidates) > 1:
        for rule in candidates:
            result.setdefault((rule.rule_key, rule.rule_version), []).append(
                _blocker("rule_conflict", "more than one rule applies and no approved combination exists; auto-selection is forbidden", rule)
            )
    return result


def evaluate_rule_applicability(
    context: ApplicabilityContext,
    rules: Sequence[PolicyRuleInput],
    sources: Mapping[str, PolicySourceState],
) -> ApplicabilityResult:
    """判断规则集合适用于申报任务的唯一规则；不适用或冲突时返回明确阻塞原因。

    保证：不默认选最新规则、未审核规则不进计算、缺失身份不猜测、
    缺失规则不产生任何参数（含零税率）、参数仅逐字回显规则声明值。
    """
    # 缺少纳税人身份：无法验证身份适用性，整体阻塞且不猜测
    if context.profile.taxpayer_identity is None:
        blocker = _blocker("taxpayer_identity_missing", "profile has no taxpayer identity; guessing an identity is forbidden")
        return ApplicabilityResult(
            outcome="blocked",
            blockers=[blocker],
            evaluated_rules=[],
            decision_hash=_decision_hash(context, None, None, {}, [blocker]),
        )

    ordered = sorted(rules, key=lambda rule: (rule.rule_key, rule.rule_version))
    evaluations: list[RuleEvaluation] = []
    blockers: list[ApplicabilityBlocker] = []
    candidates: list[PolicyRuleInput] = []
    reasons_by_rule: dict[tuple[str, str], list[str]] = {}

    scope_blockers = _check_scope_state(context)
    blockers.extend(scope_blockers)

    for rule in ordered:
        rule_blockers = _check_rule(rule, context, sources) + scope_blockers
        key = (rule.rule_key, rule.rule_version)
        if rule_blockers:
            reasons_by_rule[key] = [item.code for item in rule_blockers]
            blockers.extend(rule_blockers)
        else:
            reasons_by_rule[key] = []
            candidates.append(rule)

    conflict_blockers = _check_conflicts(candidates)
    for rule in candidates:
        key = (rule.rule_key, rule.rule_version)
        extra = conflict_blockers.get(key, [])
        if extra:
            reasons_by_rule[key] = [item.code for item in extra]
            blockers.extend(extra)

    final = [rule for rule in candidates if (rule.rule_key, rule.rule_version) not in conflict_blockers]

    for rule in ordered:
        key = (rule.rule_key, rule.rule_version)
        evaluations.append(RuleEvaluation(rule_key=rule.rule_key, rule_version=rule.rule_version,
                                          applicable=key not in conflict_blockers and not reasons_by_rule.get(key),
                                          reasons=reasons_by_rule.get(key, [])))

    if len(final) == 1:
        chosen = final[0]
        return ApplicabilityResult(
            outcome="applicable",
            rule_key=chosen.rule_key,
            rule_version=chosen.rule_version,
            parameters=dict(chosen.parameters),
            blockers=[],
            evaluated_rules=evaluations,
            decision_hash=_decision_hash(context, chosen.rule_key, chosen.rule_version, chosen.parameters, blockers),
        )

    summary = _blocker("no_applicable_rule", "no single approved rule applies; entering calculation is blocked without fallback")
    blockers.append(summary)
    return ApplicabilityResult(
        outcome="blocked",
        blockers=blockers,
        evaluated_rules=evaluations,
        decision_hash=_decision_hash(context, None, None, {}, blockers),
    )


def _decision_hash(
    context: ApplicabilityContext,
    rule_key: str | None,
    rule_version: str | None,
    parameters: dict[str, str],
    blockers: Sequence[ApplicabilityBlocker],
) -> str:
    payload = {
        "context": context.model_dump(mode="json"),
        "rule_key": rule_key,
        "rule_version": rule_version,
        "parameters": parameters,
        "blockers": sorted((item.code, item.rule_key, item.rule_version, item.condition) for item in blockers),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
