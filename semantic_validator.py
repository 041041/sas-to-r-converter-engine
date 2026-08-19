"""
semantic_validator.py
──────────────────────
Semantic Validation & Passthrough Detection Layer for Enterprise SAS Modernization Engine.
Ensures SAS->R conversions are semantically equivalent and not false-positive passthroughs.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional, Any
import pandas as pd


@dataclass
class SemanticValidationResult:
    is_equivalent: bool
    confidence_score: float
    detected_sas_ops: list[str]
    detected_r_ops: list[str]
    missing_r_ops: list[str]
    is_passthrough_false_positive: bool
    review_notes: list[str] = field(default_factory=list)


class PassthroughDetector:
    """Detects false-positive passthrough conversions (e.g., RESULT <- ORDERS)."""

    @staticmethod
    def is_passthrough(sas_code: str, r_code: str) -> bool:
        sas_low = sas_code.lower()
        r_low = r_code.lower()

        # Check if SAS contains meaningful data transformations
        has_sas_transformations = any(kw in sas_low for kw in [
            "group by", "sum(", "count(", "avg(", "mean(", "max(", "min(",
            "having", "join", "where ", "if "
        ])

        if not has_sas_transformations:
            return False

        # Check if R code is simple direct assignment (e.g., OUT <- IN)
        # Remove comments & whitespace
        r_lines = [l.strip() for l in r_low.split('\n') if l.strip() and not l.strip().startswith('#')]
        
        # If R has pipe (%>%) or group_by or summarise or filter or arrange or left_join, it's NOT a passthrough
        has_r_transformations = any(kw in r_low for kw in [
            "%>%", "group_by", "summarise", "filter(", "arrange(", "left_join", "inner_join", "merge("
        ])

        if has_sas_transformations and not has_r_transformations:
            return True

        return False


class SemanticValidator:
    """Validates operational equivalence between SAS source and generated R."""

    def validate(self, sas_code: str, r_code: str) -> SemanticValidationResult:
        sas_low = sas_code.lower()
        r_low = r_code.lower()

        sas_ops = []
        r_ops = []
        missing_ops = []
        notes = []

        # 1. GROUP BY
        if "group by" in sas_low:
            sas_ops.append("GROUP_BY")
            if any(k in r_low for k in ["group_by", "aggregate(", "count("]):
                r_ops.append("GROUP_BY")
            else:
                missing_ops.append("GROUP_BY")
                notes.append("SAS contains GROUP BY but generated R lacks group_by() or aggregate().")

        # 2. AGGREGATION (COUNT, SUM, AVG/MEAN, MAX, MIN)
        has_sas_agg = any(k in sas_low for k in ["count(", "sum(", "avg(", "mean(", "max(", "min("])
        if has_sas_agg:
            sas_ops.append("AGGREGATION")
            if any(k in r_low for k in ["summarise", "count(", "n()", "sum(", "mean(", "max(", "min("]):
                r_ops.append("AGGREGATION")
            else:
                missing_ops.append("AGGREGATION")
                notes.append("SAS contains aggregate functions but generated R lacks summarise().")

        # 3. HAVING
        if "having" in sas_low:
            sas_ops.append("HAVING")
            if "filter(" in r_low:
                r_ops.append("HAVING")
            else:
                missing_ops.append("HAVING")
                notes.append("SAS contains HAVING clause but generated R lacks filter().")

        # 4. ORDER BY
        if "order by" in sas_low or "proc sort" in sas_low:
            sas_ops.append("ORDER_BY")
            if any(k in r_low for k in ["arrange(", "order("]):
                r_ops.append("ORDER_BY")
            else:
                missing_ops.append("ORDER_BY")
                notes.append("SAS contains ORDER BY/PROC SORT but generated R lacks arrange().")

        # 5. JOIN
        if "join" in sas_low:
            sas_ops.append("JOIN")
            if any(k in r_low for k in ["left_join", "inner_join", "full_join", "right_join", "merge("]):
                r_ops.append("JOIN")
            else:
                missing_ops.append("JOIN")
                notes.append("SAS contains JOIN but generated R lacks left_join() or merge().")

        # 6. WHERE / IF filter
        if "where " in sas_low or "if " in sas_low:
            sas_ops.append("FILTER")
            if any(k in r_low for k in ["filter(", "["]):
                r_ops.append("FILTER")

        is_passthrough_fp = PassthroughDetector.is_passthrough(sas_code, r_code)
        if is_passthrough_fp:
            notes.append("CRITICAL: Detected false-positive passthrough assignment (SEMANTIC_CONVERSION_INCOMPLETE).")

        is_equivalent = (len(missing_ops) == 0) and (not is_passthrough_fp)

        # Confidence calculation
        if not sas_ops:
            score = 100.0
        elif is_equivalent:
            score = 95.0
        else:
            pct_missing = len(missing_ops) / len(sas_ops)
            score = max(10.0, round((1.0 - pct_missing) * 100.0, 1))

        return SemanticValidationResult(
            is_equivalent=is_equivalent,
            confidence_score=score,
            detected_sas_ops=sas_ops,
            detected_r_ops=r_ops,
            missing_r_ops=missing_ops,
            is_passthrough_false_positive=is_passthrough_fp,
            review_notes=notes
        )


class DataLevelValidator:
    """Deterministically validates expected tabular output for Orders benchmark dataset."""

    @staticmethod
    def expected_orders_result() -> pd.DataFrame:
        data = [
            {"cust_id": "C1", "order_date": "01JAN2024", "amount": 500},
            {"cust_id": "C1", "order_date": "15FEB2024", "amount": 300},
            {"cust_id": "C2", "order_date": "20MAR2024", "amount": 800},
            {"cust_id": "C2", "order_date": "10APR2024", "amount": 200},
            {"cust_id": "C3", "order_date": "05MAY2024", "amount": 600},
        ]
        df = pd.DataFrame(data)
        
        grouped = df.groupby("cust_id").agg(
            total_orders=("amount", "count"),
            total_spent=("amount", "sum"),
            avg_spent=("amount", "mean"),
            max_order=("amount", "max"),
            min_order=("amount", "min")
        ).reset_index()

        filtered = grouped[grouped["total_spent"] > 500]
        sorted_df = filtered.sort_values(by="total_spent", ascending=False).reset_index(drop=True)
        return sorted_df

    @classmethod
    def verify_orders_data_equivalence(cls, result_df: pd.DataFrame) -> bool:
        expected = cls.expected_orders_result()
        if len(result_df) != len(expected):
            return False
        
        # Check cust_id ordering
        expected_custs = list(expected["cust_id"])
        actual_custs = list(result_df["cust_id"])
        if expected_custs != actual_custs:
            return False

        # Check total_spent sums
        for i in range(len(expected)):
            if abs(result_df.loc[i, "total_spent"] - expected.loc[i, "total_spent"]) > 0.001:
                return False

        return True
