"""BE2-10-09 政策规则适用性测试（synthetic fixture，不是真实政策）。

覆盖任务要求的 15 个测试维度、版本验证（历史所属期选择当时生效的规则版本、
判定确定性）以及核心禁止项（不默认选最新、未审核不进计算、缺失身份不猜测、
缺失规则不用零税率、参数不合成）。fixture 值全部为 SYNTHETIC_* 占位，
DEC-002～005/011 确认前不得当作真实地区、主体、身份或税率。
"""

from datetime import date

from app.services.policy_applicability import (
    ApplicabilityContext,
    FilingPeriodInput,
    MerchantProfileInput,
    PolicyRuleInput,
    PolicySourceState,
    SupportedScopeInput,
    evaluate_rule_applicability,
)

REGION_A = "SYNTHETIC_REGION_A"
REGION_B = "SYNTHETIC_REGION_B"
ENTITY_X = "SYNTHETIC_ENTITY_X"
ENTITY_Y = "SYNTHETIC_ENTITY_Y"
IDENTITY_P = "SYNTHETIC_IDENTITY_P"
IDENTITY_Q = "SYNTHETIC_IDENTITY_Q"
FILING = "SYNTHETIC_FILING"

VERIFIED = PolicySourceState(source_id="src-verified", status="verified", content_hash="a" * 64)
CANDIDATE_SOURCE = PolicySourceState(source_id="src-candidate", status="candidate", content_hash="b" * 64)
SOURCES = {"src-verified": VERIFIED, "src-candidate": CANDIDATE_SOURCE}


def approved_rule(**overrides) -> PolicyRuleInput:
    base = {
        "rule_key": "SYNTHETIC_RULE",
        "rule_version": "synthetic-v1",
        "source_ids": ["src-verified"],
        "region_code": REGION_A,
        "entity_type": ENTITY_X,
        "taxpayer_identity": IDENTITY_P,
        "filing_kind": FILING,
        "effective_from": date(2026, 1, 1),
        "effective_to": date(2026, 12, 31),
        "status": "approved",
        "parameters": {"synthetic_rate": "example_only"},
    }
    base.update(overrides)
    return PolicyRuleInput(**base)


def make_context(*, period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
                 taxpayer_identity=IDENTITY_P, region_code=REGION_A, entity_type=ENTITY_X,
                 filing_kind=FILING, scope=None) -> ApplicabilityContext:
    return ApplicabilityContext(
        profile=MerchantProfileInput(region_code=region_code, entity_type=entity_type, taxpayer_identity=taxpayer_identity),
        period=FilingPeriodInput(period_start=period_start, period_end=period_end),
        filing_kind=filing_kind,
        scope=scope,
    )


def codes_of(result, rule_index=0) -> set[str]:
    return set(result.evaluated_rules[rule_index].reasons)


def blocker_codes(result) -> set[str]:
    return {item.code for item in result.blockers}


# 维度 1-2：地区一致 / 地区不一致


def test_region_consistency_and_mismatch() -> None:
    matched = evaluate_rule_applicability(make_context(), [approved_rule()], SOURCES)
    assert matched.outcome == "applicable"
    assert (matched.rule_key, matched.rule_version) == ("SYNTHETIC_RULE", "synthetic-v1")
    assert matched.blockers == []

    mismatched = evaluate_rule_applicability(make_context(), [approved_rule(region_code=REGION_B)], SOURCES)
    assert mismatched.outcome == "blocked"
    assert "region_mismatch" in codes_of(mismatched)
    assert "region_mismatch" in blocker_codes(mismatched)
    assert mismatched.parameters == {}


# 维度 3-4：经营主体一致 / 不一致


def test_entity_type_consistency_and_mismatch() -> None:
    matched = evaluate_rule_applicability(make_context(), [approved_rule()], SOURCES)
    assert matched.outcome == "applicable"

    mismatched = evaluate_rule_applicability(make_context(), [approved_rule(entity_type=ENTITY_Y)], SOURCES)
    assert mismatched.outcome == "blocked"
    assert "entity_type_mismatch" in codes_of(mismatched)


# 维度 5-6：纳税人身份一致 / 不一致（规则未限定身份时按身份不限处理）


def test_taxpayer_identity_consistency_and_mismatch() -> None:
    matched = evaluate_rule_applicability(make_context(), [approved_rule()], SOURCES)
    assert matched.outcome == "applicable"

    unrestricted = evaluate_rule_applicability(make_context(), [approved_rule(taxpayer_identity=None)], SOURCES)
    assert unrestricted.outcome == "applicable"

    mismatched = evaluate_rule_applicability(make_context(), [approved_rule(taxpayer_identity=IDENTITY_Q)], SOURCES)
    assert mismatched.outcome == "blocked"
    assert "taxpayer_identity_mismatch" in codes_of(mismatched)


# 维度 7-8-9：生效日期之前 / 之内 / 失效之后


def test_period_before_inside_and_after_effective_window() -> None:
    inside = evaluate_rule_applicability(make_context(), [approved_rule()], SOURCES)
    assert inside.outcome == "applicable"

    before = evaluate_rule_applicability(
        make_context(period_start=date(2025, 6, 1), period_end=date(2025, 6, 30)), [approved_rule()], SOURCES
    )
    assert before.outcome == "blocked"
    assert "period_before_effective" in codes_of(before)

    after = evaluate_rule_applicability(
        make_context(period_start=date(2027, 6, 1), period_end=date(2027, 6, 30)), [approved_rule()], SOURCES
    )
    assert after.outcome == "blocked"
    assert "period_after_effective" in codes_of(after)


# 维度 10：所属期跨越规则生效边界


def test_period_crossing_effective_boundary_is_blocked() -> None:
    crossing_start = evaluate_rule_applicability(
        make_context(period_start=date(2025, 12, 1), period_end=date(2026, 1, 31)), [approved_rule()], SOURCES
    )
    assert crossing_start.outcome == "blocked"
    assert "period_crosses_effective_boundary" in codes_of(crossing_start)

    crossing_end = evaluate_rule_applicability(
        make_context(period_start=date(2026, 12, 1), period_end=date(2027, 1, 31)), [approved_rule()], SOURCES
    )
    assert crossing_end.outcome == "blocked"
    assert "period_crosses_effective_boundary" in codes_of(crossing_end)


# 维度 11：规则尚未审核（禁止未审核规则进入正式计算）


def test_unapproved_rules_never_enter_calculation() -> None:
    for status in ("candidate", "under_review", "rejected", "retired"):
        result = evaluate_rule_applicability(make_context(), [approved_rule(status=status)], SOURCES)
        assert result.outcome == "blocked", status
        assert "rule_not_approved" in codes_of(result), status
        assert result.parameters == {}, status
        assert result.rule_key is None, status


# 维度 12：存在冲突规则（禁止默认选择最新规则）


def test_conflicting_rules_block_without_auto_selection() -> None:
    version_overlap = [
        approved_rule(rule_version="synthetic-v1", effective_from=date(2025, 1, 1), effective_to=None),
        approved_rule(rule_version="synthetic-v2", effective_from=date(2026, 1, 1), effective_to=None,
                      parameters={"synthetic_rate": "newer"}),
    ]
    overlap = evaluate_rule_applicability(make_context(), version_overlap, SOURCES)
    assert overlap.outcome == "blocked"
    assert "rule_version_conflict" in blocker_codes(overlap)
    assert overlap.parameters == {}
    assert overlap.rule_version is None  # 不允许默认选择最新版本

    declared = [
        approved_rule(rule_key="SYNTHETIC_RULE_A", conflicts_with=["SYNTHETIC_RULE_B"]),
        approved_rule(rule_key="SYNTHETIC_RULE_B", conflicts_with=["SYNTHETIC_RULE_A"], parameters={"synthetic_rate": "other"}),
    ]
    conflict = evaluate_rule_applicability(make_context(), declared, SOURCES)
    assert conflict.outcome == "blocked"
    assert "rule_conflict" in blocker_codes(conflict)
    assert conflict.parameters == {}

    undeclared = [
        approved_rule(rule_key="SYNTHETIC_RULE_A"),
        approved_rule(rule_key="SYNTHETIC_RULE_B", parameters={"synthetic_rate": "other"}),
    ]
    ambiguous = evaluate_rule_applicability(make_context(), undeclared, SOURCES)
    assert ambiguous.outcome == "blocked"
    assert "rule_conflict" in blocker_codes(ambiguous)


# 维度 13：缺少纳税人身份（禁止猜测身份）


def test_missing_taxpayer_identity_blocks_without_guessing() -> None:
    result = evaluate_rule_applicability(make_context(taxpayer_identity=None), [approved_rule()], SOURCES)
    assert result.outcome == "blocked"
    assert "taxpayer_identity_missing" in blocker_codes(result)
    assert result.evaluated_rules == []  # 不猜测、不套用任何身份比对
    assert result.parameters == {}


# 维度 14：缺少必要适用条件


def test_missing_required_condition_blocks() -> None:
    cases = (
        ({"region_code": None}, "region_code"),
        ({"entity_type": "   "}, "entity_type"),
        ({"filing_kind": None}, "filing_kind"),
        ({"effective_from": None}, "effective_from"),
    )
    for overrides, condition in cases:
        result = evaluate_rule_applicability(make_context(), [approved_rule(**overrides)], SOURCES)
        assert result.outcome == "blocked", condition
        assert "missing_required_condition" in codes_of(result), condition
        flagged = [item for item in result.blockers if item.code == "missing_required_condition"]
        assert flagged and flagged[0].condition == condition, condition


# 维度 15：支持范围不匹配


def test_supported_scope_mismatch_blocks() -> None:
    covering = SupportedScopeInput(region_code=REGION_A, entity_type=ENTITY_X, taxpayer_identity=IDENTITY_P,
                                   filing_kind=FILING, form_version="SYNTHETIC_FORM_A", status="active")
    ok = evaluate_rule_applicability(make_context(scope=covering), [approved_rule()], SOURCES)
    assert ok.outcome == "applicable"

    draft_scope = covering.model_copy(update={"status": "draft"})
    unusable = evaluate_rule_applicability(make_context(scope=draft_scope), [approved_rule()], SOURCES)
    assert unusable.outcome == "blocked"
    assert "scope_not_supported" in blocker_codes(unusable)

    wrong_region = covering.model_copy(update={"region_code": REGION_B})
    uncovered = evaluate_rule_applicability(make_context(scope=wrong_region), [approved_rule()], SOURCES)
    assert uncovered.outcome == "blocked"
    assert "scope_not_supported" in blocker_codes(uncovered)

    form_mismatch = evaluate_rule_applicability(
        make_context(scope=covering), [approved_rule(form_version="SYNTHETIC_FORM_B")], SOURCES
    )
    assert form_mismatch.outcome == "blocked"
    assert "scope_mismatch" in codes_of(form_mismatch)

    outside = evaluate_rule_applicability(make_context(scope=covering), [approved_rule(region_code=REGION_B)], SOURCES)
    assert outside.outcome == "blocked"
    assert {"region_mismatch", "scope_mismatch"} <= codes_of(outside)


# 来源明确：引用缺失或未核验来源的规则不能进入计算


def test_source_provenance_is_required() -> None:
    no_source = evaluate_rule_applicability(make_context(), [approved_rule(source_ids=[])], SOURCES)
    assert no_source.outcome == "blocked"
    assert "source_missing" in codes_of(no_source)

    unknown = evaluate_rule_applicability(make_context(), [approved_rule(source_ids=["src-unknown"])], SOURCES)
    assert unknown.outcome == "blocked"
    assert "source_missing" in codes_of(unknown)

    unverified = evaluate_rule_applicability(make_context(), [approved_rule(source_ids=["src-candidate"])], SOURCES)
    assert unverified.outcome == "blocked"
    assert "source_not_verified" in codes_of(unverified)


# 版本验证：历史所属期选择当时生效的规则版本


def test_historical_period_selects_historically_effective_version() -> None:
    versions = [
        approved_rule(rule_version="synthetic-v1", effective_from=date(2025, 1, 1), effective_to=date(2025, 12, 31),
                      parameters={"synthetic_rate": "v1"}),
        approved_rule(rule_version="synthetic-v2", effective_from=date(2026, 1, 1), effective_to=None,
                      parameters={"synthetic_rate": "v2"}),
    ]
    historical = evaluate_rule_applicability(
        make_context(period_start=date(2025, 6, 1), period_end=date(2025, 6, 30)), versions, SOURCES
    )
    assert historical.outcome == "applicable"
    assert historical.rule_version == "synthetic-v1"
    assert historical.parameters == {"synthetic_rate": "v1"}

    current = evaluate_rule_applicability(make_context(), versions, SOURCES)
    assert current.outcome == "applicable"
    assert current.rule_version == "synthetic-v2"
    assert current.parameters == {"synthetic_rate": "v2"}


# 版本验证：同一输入、同一规则版本的判定结果一致


def test_decision_is_deterministic() -> None:
    rules = [approved_rule()]
    first = evaluate_rule_applicability(make_context(), rules, SOURCES)
    second = evaluate_rule_applicability(make_context(), rules, SOURCES)
    assert first.model_dump() == second.model_dump()
    assert first.decision_hash == second.decision_hash

    other = evaluate_rule_applicability(make_context(period_start=date(2026, 7, 1), period_end=date(2026, 7, 31)), rules, SOURCES)
    assert other.decision_hash != first.decision_hash


# 禁止项：缺失规则时阻塞，不产生零税率或任何参数


def test_no_applicable_rule_blocks_without_zero_rate() -> None:
    empty = evaluate_rule_applicability(make_context(), [], SOURCES)
    assert empty.outcome == "blocked"
    assert "no_applicable_rule" in blocker_codes(empty)
    assert empty.parameters == {}
    assert empty.rule_key is None

    all_failing = evaluate_rule_applicability(make_context(), [approved_rule(status="candidate")], SOURCES)
    assert all_failing.outcome == "blocked"
    assert "no_applicable_rule" in blocker_codes(all_failing)
    assert all_failing.parameters == {}


# 禁止项：参数只逐字回显已审核规则声明值，不合成、不补足


def test_parameters_only_echo_declared_rule_values() -> None:
    declared = {"synthetic_rate": "example_only", "synthetic_note": "no_real_policy"}
    result = evaluate_rule_applicability(make_context(), [approved_rule(parameters=declared)], SOURCES)
    assert result.outcome == "applicable"
    assert result.parameters == declared
    assert set(result.parameters) == set(declared)
