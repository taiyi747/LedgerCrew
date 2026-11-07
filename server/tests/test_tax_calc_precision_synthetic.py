"""BE2-10-10 synthetic-only precision / threshold / rounding tests.

SYNTHETIC TEST HARNESS — NOT A BUSINESS TAX IMPLEMENTATION.

The v0.2 deterministic tax calculation engine (BE2-06) does not exist yet and
DEC-002~004 / DEC-010~013 are still ``pending``. Every rate, threshold and the
rounding fixture below is an explicitly marked SYNTHETIC placeholder used only
to exercise the generic amount-precision capabilities that any future engine
must provide:

- amounts enter and leave as integer cents (``int``); yuan strings and floats
  are rejected (unit-confusion guard);
- ratios are decimal strings parsed with :class:`decimal.Decimal`; no float
  participates in the calculation;
- intermediate values keep full precision; one explicit rounding
  (``ROUND_HALF_UP`` fixture) is applied only at the final step;
- missing input or missing rule blocks the calculation instead of silently
  becoming zero;
- the result snapshot carries input hash, rule version, engine version,
  formula, parameters, intermediates and rounding, so the same snapshot and
  versions reproduce the identical result and rule version changes are
  distinguishable.

Real tax rates, preferential thresholds and rounding policy stay BLOCKED and
must not be inferred from these fixtures.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext

# ---------------------------------------------------------------------------
# SYNTHETIC fixtures (placeholder values only — never real policy).
# ---------------------------------------------------------------------------
ENGINE_VERSION = "synthetic-engine-1"
ROUNDING_FIXTURE = "ROUND_HALF_UP"  # synthetic, explicit; real rounding policy is BLOCKED
THRESHOLD_SEMANTICS = "SYNTHETIC: base_cents >= threshold_cents applies rate, below applies zero rate"


@dataclass(frozen=True)
class SyntheticRule:
    """Placeholder rule parameters. Values are synthetic, not tax policy."""

    rule_version: str
    rate: str
    threshold_cents: int | None = None


RULE_V1 = SyntheticRule(rule_version="SYNTH-RULE-v1", rate="0.07")
RULE_V1_THRESHOLD = SyntheticRule(rule_version="SYNTH-RULE-v1-threshold", rate="0.07", threshold_cents=100000)
RULE_V2 = SyntheticRule(rule_version="SYNTH-RULE-v2", rate="0.09")


# ---------------------------------------------------------------------------
# Synthetic deterministic kernel.
# ---------------------------------------------------------------------------
def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def run_calculation(
    *,
    base_cents: int | None,
    extra_cents: tuple[int, ...] = (),
    rule: SyntheticRule | None,
    engine_version: str = ENGINE_VERSION,
) -> dict:
    """Compute one synthetic calculation and return a traceable snapshot.

    ``base_cents`` must be integer cents or ``None`` (missing). Floats and
    yuan strings are rejected so unit confusion and float mixing fail fast.
    """
    for amount in (base_cents, *extra_cents):
        if amount is not None and not isinstance(amount, int):
            raise TypeError("amount_cents must be integer cents, not float or string")

    amounts = [] if base_cents is None else [base_cents, *extra_cents]
    input_snapshot = {
        "amounts_cents": amounts,
        "engine_version": engine_version,
        "rule_parameters": (
            {
                "rule_version": rule.rule_version,
                "rate": rule.rate,
                "threshold_cents": rule.threshold_cents,
                "threshold_semantics": THRESHOLD_SEMANTICS,
            }
            if rule is not None
            else None
        ),
    }
    input_hash = _sha256(input_snapshot)

    def blocked(code: str) -> dict:
        result = {
            "status": "blocked",
            "blockers": [{"code": code}],
            "engine_version": engine_version,
            "rule_version": rule.rule_version if rule is not None else None,
            "input_snapshot": input_snapshot,
            "input_hash": input_hash,
            "formula": None,
            "rule_parameters": input_snapshot["rule_parameters"],
            "intermediates": [],
            "rounding": ROUNDING_FIXTURE,
            "threshold_met": None,
            "effective_rate": None,
            "final_cents": None,
        }
        result["result_hash"] = _sha256(result)
        return result

    if base_cents is None:
        return blocked("missing_input")
    if rule is None:
        return blocked("missing_rule")
    if not rule.rate.strip():
        return blocked("missing_rule_parameter")

    rate = Decimal(rule.rate)  # exact decimal string -> Decimal; float never enters
    threshold_met = True if rule.threshold_cents is None else base_cents >= rule.threshold_cents
    effective_rate = rate if threshold_met else Decimal("0")

    intermediates = []
    total = Decimal("0")
    for amount in amounts:
        raw = Decimal(amount) * effective_rate  # full precision, no early rounding
        intermediates.append({"amount_cents": amount, "raw_tax_cents": str(raw)})
        total += raw

    # Single explicit rounding at the final step, integer cents out.
    final_cents = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    result = {
        "status": "completed",
        "blockers": [],
        "engine_version": engine_version,
        "rule_version": rule.rule_version,
        "input_snapshot": input_snapshot,
        "input_hash": input_hash,
        "formula": "tax_cents = ROUND( Σ(amount_i_cents × effective_rate), 1 cent )",
        "rule_parameters": input_snapshot["rule_parameters"],
        "intermediates": intermediates,
        "rounding": ROUNDING_FIXTURE,
        "threshold_met": threshold_met,
        "effective_rate": str(effective_rate),
        "final_cents": final_cents,
    }
    result["result_hash"] = _sha256(result)
    return result


# ---------------------------------------------------------------------------
# 1. 普通金额计算
# ---------------------------------------------------------------------------
def test_scenario01_normal_amount() -> None:
    result = run_calculation(base_cents=12345, rule=RULE_V1)
    assert result["status"] == "completed"
    assert result["final_cents"] == 864  # 12345 × 0.07 = 864.15 → 864
    assert result["intermediates"] == [{"amount_cents": 12345, "raw_tax_cents": "864.15"}]
    assert isinstance(result["final_cents"], int)
    assert result["rounding"] == ROUNDING_FIXTURE
    assert len(result["input_hash"]) == 64 and len(result["result_hash"]) == 64


# ---------------------------------------------------------------------------
# 2. 小额金额计算
# ---------------------------------------------------------------------------
def test_scenario02_small_amounts() -> None:
    tiny = run_calculation(base_cents=1, rule=RULE_V1)
    assert tiny["intermediates"][0]["raw_tax_cents"] == "0.07"
    assert tiny["final_cents"] == 0  # rounded result, still status=completed, not blocked

    small = run_calculation(base_cents=3, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.33"))
    assert small["intermediates"][0]["raw_tax_cents"] == "0.99"
    assert small["final_cents"] == 1


# ---------------------------------------------------------------------------
# 3. 大额金额计算
# ---------------------------------------------------------------------------
def test_scenario03_large_amounts() -> None:
    big = run_calculation(base_cents=10**15, rule=RULE_V1)
    assert big["intermediates"][0]["raw_tax_cents"] == "70000000000000.00"  # exact product scale
    assert big["final_cents"] == 70 * 10**12

    # 1234567890123456789 × 0.001 = 1234567890123456.789 → 1234567890123457.
    # Cross-checked with pure integer arithmetic so the expectation does not
    # depend on Decimal or float: (n × 1) / 1000 rounded half up = (n + 500)//1000.
    huge_n = 1234567890123456789
    huge = run_calculation(base_cents=huge_n, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.001"))
    assert huge["intermediates"][0]["raw_tax_cents"] == "1234567890123456.789"
    assert huge["final_cents"] == (huge_n + 500) // 1000 == 1234567890123457


# ---------------------------------------------------------------------------
# 4. 正好达到阈值
# ---------------------------------------------------------------------------
def test_scenario04_exactly_at_threshold() -> None:
    result = run_calculation(base_cents=100000, rule=RULE_V1_THRESHOLD)
    assert result["threshold_met"] is True
    assert result["effective_rate"] == "0.07"
    assert result["final_cents"] == 7000  # 100000 × 0.07 = 7000.00


# ---------------------------------------------------------------------------
# 5. 低于阈值一个最小货币单位
# ---------------------------------------------------------------------------
def test_scenario05_one_unit_below_threshold() -> None:
    result = run_calculation(base_cents=99999, rule=RULE_V1_THRESHOLD)
    assert result["status"] == "completed"  # evaluated, not blocked, not missing
    assert result["threshold_met"] is False
    assert result["effective_rate"] == "0"
    assert result["intermediates"] == [{"amount_cents": 99999, "raw_tax_cents": "0"}]
    assert result["final_cents"] == 0


# ---------------------------------------------------------------------------
# 6. 高于阈值一个最小货币单位
# ---------------------------------------------------------------------------
def test_scenario06_one_unit_above_threshold() -> None:
    result = run_calculation(base_cents=100001, rule=RULE_V1_THRESHOLD)
    assert result["threshold_met"] is True
    assert result["effective_rate"] == "0.07"
    assert result["intermediates"][0]["raw_tax_cents"] == "7000.07"
    assert result["final_cents"] == 7000


# ---------------------------------------------------------------------------
# 7. 小数边界
# ---------------------------------------------------------------------------
def test_scenario07_decimal_boundaries() -> None:
    repeating = run_calculation(base_cents=3, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.333333333333333333"))
    assert repeating["intermediates"][0]["raw_tax_cents"] == "0.999999999999999999"
    assert repeating["final_cents"] == 1

    long_rate = run_calculation(
        base_cents=10, rule=SyntheticRule("SYNTH-RULE-v1", rate="1.234567890123456789012345678")
    )
    assert long_rate["intermediates"][0]["raw_tax_cents"] == "12.34567890123456789012345678"
    assert long_rate["final_cents"] == 12

    tenth = run_calculation(base_cents=7, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.1"))
    assert tenth["intermediates"][0]["raw_tax_cents"] == "0.7"  # exact Decimal, not 0.7000000000000001
    assert tenth["final_cents"] == 1

    quarter = run_calculation(base_cents=3, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.25"))
    assert quarter["intermediates"][0]["raw_tax_cents"] == "0.75"
    assert quarter["final_cents"] == 1


# ---------------------------------------------------------------------------
# 8. 舍入边界
# ---------------------------------------------------------------------------
def test_scenario08_rounding_boundaries() -> None:
    below = run_calculation(base_cents=4, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.1"))
    exact_half = run_calculation(base_cents=5, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.1"))
    above = run_calculation(base_cents=6, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.1"))
    assert (below["final_cents"], exact_half["final_cents"], above["final_cents"]) == (0, 1, 1)

    # Rounding must be explicit: the ambient Decimal context cannot change it.
    with localcontext() as ctx:
        ctx.rounding = ROUND_DOWN
        forced_down = run_calculation(base_cents=5, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.1"))
        ctx.rounding = ROUND_CEILING
        forced_up = run_calculation(base_cents=5, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.1"))
    assert forced_down["final_cents"] == forced_up["final_cents"] == 1

    # The rounding mode is part of the recorded policy surface: a different
    # mode would give a different answer, so it must stay versioned in the
    # snapshot (synthetic demo only).
    raw_half = Decimal(5) * Decimal("0.1")
    assert int(raw_half.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) == 1
    assert int(raw_half.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)) == 0
    assert exact_half["rounding"] == "ROUND_HALF_UP"


# ---------------------------------------------------------------------------
# 9. 多步骤计算（只在最终步舍入一次）
# ---------------------------------------------------------------------------
def test_scenario09_multi_step_single_rounding() -> None:
    result = run_calculation(base_cents=10, extra_cents=(10,), rule=SyntheticRule("SYNTH-RULE-v1", rate="0.05"))
    assert result["intermediates"] == [
        {"amount_cents": 10, "raw_tax_cents": "0.50"},
        {"amount_cents": 10, "raw_tax_cents": "0.50"},
    ]
    # Full-precision total is 1.0 → 1 cent. Rounding each step first would give
    # 1 + 1 = 2 cents; the engine rounds once, at the end.
    assert result["final_cents"] == 1

    tiny_steps = run_calculation(
        base_cents=1, extra_cents=(1,), rule=SyntheticRule("SYNTH-RULE-v1", rate="0.05")
    )
    assert tiny_steps["intermediates"][0]["raw_tax_cents"] == "0.05"
    assert tiny_steps["final_cents"] == 0  # 0.1 total

    mixed = run_calculation(
        base_cents=12345,
        extra_cents=(10, 3),
        rule=SyntheticRule("SYNTH-RULE-v1", rate="0.05"),
    )
    assert [i["raw_tax_cents"] for i in mixed["intermediates"]] == ["617.25", "0.50", "0.15"]
    assert mixed["final_cents"] == 618  # 617.9 total


# ---------------------------------------------------------------------------
# 10. 负数和退款场景
# ---------------------------------------------------------------------------
def test_scenario10_negative_and_refunds() -> None:
    negative = run_calculation(base_cents=-12345, rule=RULE_V1)
    assert negative["intermediates"][0]["raw_tax_cents"] == "-864.15"
    assert negative["final_cents"] == -864

    # Exact negative half: the synthetic rounding fixture goes away from zero,
    # which must be stated explicitly because other modes differ.
    neg_half = run_calculation(base_cents=-5, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.1"))
    assert neg_half["intermediates"][0]["raw_tax_cents"] == "-0.5"
    assert neg_half["final_cents"] == -1

    # Refund pairing: a charge and its full refund cancel exactly.
    charge = run_calculation(base_cents=12345, rule=RULE_V1)
    refund = run_calculation(base_cents=-12345, rule=RULE_V1)
    assert charge["final_cents"] + refund["final_cents"] == 0

    for base in (12345, 5, 1):
        pos = run_calculation(base_cents=base, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.1"))
        neg = run_calculation(base_cents=-base, rule=SyntheticRule("SYNTH-RULE-v1", rate="0.1"))
        assert pos["final_cents"] == -neg["final_cents"]


# ---------------------------------------------------------------------------
# 11. 零金额输入
# ---------------------------------------------------------------------------
def test_scenario11_zero_amount() -> None:
    result = run_calculation(base_cents=0, rule=RULE_V1)
    assert result["status"] == "completed"
    assert result["blockers"] == []
    assert result["final_cents"] == 0
    assert result["input_hash"] != run_calculation(base_cents=None, rule=RULE_V1)["input_hash"]
    # Zero is an evaluated amount, not a missing input.
    assert run_calculation(base_cents=None, rule=RULE_V1)["status"] == "blocked"


# ---------------------------------------------------------------------------
# 12. 缺失输入
# ---------------------------------------------------------------------------
def test_scenario12_missing_input() -> None:
    result = run_calculation(base_cents=None, rule=RULE_V1)
    assert result["status"] == "blocked"
    assert [b["code"] for b in result["blockers"]] == ["missing_input"]
    assert result["final_cents"] is None

    # Unit-confusion guards: floats and yuan strings are rejected outright.
    for bad in (12.5, "12.34", 0.001):
        try:
            run_calculation(base_cents=bad, rule=RULE_V1)
        except TypeError:
            pass
        else:
            raise AssertionError(f"accepted non-integer amount: {bad!r}")
    try:
        run_calculation(base_cents=100, extra_cents=(1.5,), rule=RULE_V1)
    except TypeError:
        pass
    else:
        raise AssertionError("accepted float extra amount")


# ---------------------------------------------------------------------------
# 13. 缺失规则
# ---------------------------------------------------------------------------
def test_scenario13_missing_rule() -> None:
    no_rule = run_calculation(base_cents=12345, rule=None)
    assert no_rule["status"] == "blocked"
    assert [b["code"] for b in no_rule["blockers"]] == ["missing_rule"]
    assert no_rule["final_cents"] is None

    no_param = run_calculation(base_cents=12345, rule=SyntheticRule("SYNTH-RULE-v1", rate=""))
    assert no_param["status"] == "blocked"
    assert [b["code"] for b in no_param["blockers"]] == ["missing_rule_parameter"]
    assert no_param["final_cents"] is None  # never silently zero


# ---------------------------------------------------------------------------
# 14. 规则版本变化
# ---------------------------------------------------------------------------
def test_scenario14_rule_version_change() -> None:
    old = run_calculation(base_cents=12345, rule=RULE_V1)
    new = run_calculation(base_cents=12345, rule=RULE_V2)
    assert old["final_cents"] == 864  # × 0.07
    assert new["final_cents"] == 1111  # 12345 × 0.09 = 1111.05
    assert old["rule_version"] == "SYNTH-RULE-v1" and new["rule_version"] == "SYNTH-RULE-v2"
    assert old["input_hash"] != new["input_hash"]
    assert old["result_hash"] != new["result_hash"]

    # Recomputing with the pinned old version reproduces the old result exactly.
    replay = run_calculation(base_cents=12345, rule=RULE_V1)
    assert replay["result_hash"] == old["result_hash"]

    # Engine version is part of the snapshot: same numbers, distinguishable record.
    other_engine = run_calculation(base_cents=12345, rule=RULE_V1, engine_version="synthetic-engine-2")
    assert other_engine["final_cents"] == old["final_cents"]
    assert other_engine["result_hash"] != old["result_hash"]
    assert other_engine["input_hash"] != old["input_hash"]


# ---------------------------------------------------------------------------
# 15. 重复计算
# ---------------------------------------------------------------------------
def test_scenario15_repeat_calculation() -> None:
    runs = [run_calculation(base_cents=12345, extra_cents=(10,), rule=RULE_V1_THRESHOLD) for _ in range(10)]
    first = runs[0]
    for result in runs[1:]:
        assert result["result_hash"] == first["result_hash"]
        assert _canonical(result) == _canonical(first)

    blocked_runs = [run_calculation(base_cents=None, rule=RULE_V1) for _ in range(3)]
    assert len({r["result_hash"] for r in blocked_runs}) == 1

    # Canonical hashing ignores key order and dict insertion order.
    reordered = {"rule_version": "SYNTH-RULE-v1", "rate": "0.07", "threshold_cents": None,
                 "threshold_semantics": THRESHOLD_SEMANTICS}
    original = {"threshold_semantics": THRESHOLD_SEMANTICS, "threshold_cents": None,
                "rate": "0.07", "rule_version": "SYNTH-RULE-v1"}
    assert _sha256(reordered) == _sha256(original)
