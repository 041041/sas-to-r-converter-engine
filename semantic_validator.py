"""
semantic_validator.py
──────────────────────
Strict Expression-Level Semantic Validation & Passthrough Detection Layer
for Enterprise SAS Modernization Engine.
Ensures SAS->R conversions are semantically complete, dataset-verified, and not false positives.
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
    missing_columns: list[str] = field(default_factory=list)
    expected_columns: list[str] = field(default_factory=list)


def extract_expected_sas_columns(sas_code: str) -> list[str]:
    """Extracts expected output variable names from SAS PROC SQL or DATA steps."""
    sas_clean = re.sub(r'/\*.*?\*/', '', sas_code, flags=re.DOTALL)
    sas_clean = re.sub(r'--.*?\n', '\n', sas_clean)
    
    expected_cols = []
    
    # 1. PROC SQL SELECT clause handling
    select_match = re.search(r'\bselect\b(.*?)\bfrom\b', sas_clean, re.I | re.DOTALL)
    if select_match:
        select_clause = select_match.group(1)
        
        items = []
        current = []
        depth = 0
        for char in select_clause:
            if char in '([':
                depth += 1
                current.append(char)
            elif char in ')]':
                depth -= 1
                current.append(char)
            elif char == ',' and depth == 0:
                items.append(''.join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            items.append(''.join(current).strip())
            
        sql_keywords = {
            "SELECT", "DISTINCT", "FROM", "WHERE", "GROUP", "HAVING", "ORDER",
            "BY", "CASE", "WHEN", "THEN", "ELSE", "END", "AS", "CALCULATED",
            "COUNT", "SUM", "AVG", "MEAN", "MIN", "MAX", "INT", "COALESCE",
            "UPPER", "LOWER", "ON", "LEFT", "RIGHT", "JOIN", "INNER", "OUTER"
        }
        
        for item in items:
            item_clean = item.strip()
            if not item_clean:
                continue
            
            as_match = re.search(r'\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$', item_clean, re.I)
            if as_match:
                alias = as_match.group(1).upper()
                if alias not in sql_keywords and alias not in expected_cols:
                    expected_cols.append(alias)
                continue
                
            implicit_as = re.search(r'(?:END|\))\s+([A-Za-z_][A-Za-z0-9_]*)\s*$', item_clean, re.I)
            if implicit_as:
                alias = implicit_as.group(1).upper()
                if alias not in sql_keywords and alias not in expected_cols:
                    expected_cols.append(alias)
                continue

            col_match = re.search(r'^(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)$', item_clean, re.I)
            if col_match:
                col_name = col_match.group(1).upper()
                if col_name not in sql_keywords and col_name not in expected_cols:
                    expected_cols.append(col_name)
                continue

    # 2. DATA STEP assignment handling
    else:
        statements = sas_clean.split(";")
        data_keywords = {
            "IF", "THEN", "ELSE", "DO", "END", "LENGTH", "RETAIN", "KEEP",
            "DROP", "SET", "MERGE", "BY", "FORMAT", "LABEL", "DATA", "RUN",
            "QUIT", "INPUT", "OUTPUT", "WHERE"
        }
        for stmt in statements:
            stmt_clean = stmt.strip()
            if not stmt_clean:
                continue

            target_str = stmt_clean
            then_match = re.search(r'\bthen\b(.*)$', stmt_clean, re.I | re.DOTALL)
            if then_match:
                target_str = then_match.group(1).strip()
            else:
                else_match = re.search(r'^\s*else\b(.*)$', stmt_clean, re.I | re.DOTALL)
                if else_match:
                    target_str = else_match.group(1).strip()

            assign_match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)(.*)$', target_str, re.DOTALL)
            if assign_match:
                var_name = assign_match.group(1).upper()
                if var_name not in data_keywords and var_name not in expected_cols:
                    expected_cols.append(var_name)

    return expected_cols


def validate_semantic_completeness(sas_code: str, r_code: str) -> tuple[bool, list[str], list[str], list[str]]:
    """
    Validates that all expected output columns/variables from the SAS step are represented in the generated R code.
    Returns: (is_complete, expected_cols, present_cols, missing_cols)
    """
    expected_cols = extract_expected_sas_columns(sas_code)
    if not expected_cols:
        return True, [], [], []

    r_lines = [l.split('#')[0] for l in r_code.split('\n')]
    r_code_clean = '\n'.join(r_lines)

    present_cols = []
    missing_cols = []

    for col in expected_cols:
        pattern = r'\b' + re.escape(col) + r'\b'
        if re.search(pattern, r_code_clean, re.I):
            present_cols.append(col)
        else:
            missing_cols.append(col)

    is_complete = (len(missing_cols) == 0)
    return is_complete, expected_cols, present_cols, missing_cols


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
        r_lines = [l.strip() for l in r_low.split('\n') if l.strip() and not l.strip().startswith('#')]
        
        has_r_transformations = any(kw in r_low for kw in [
            "%>%", "group_by", "summarise", "filter(", "arrange(", "left_join", "inner_join", "merge("
        ])

        if has_sas_transformations and not has_r_transformations:
            return True

        return False


class SemanticValidator:
    """Validates strict expression-level operational equivalence between SAS source and generated R."""

    def validate(self, sas_code: str, r_code: str) -> SemanticValidationResult:
        sas_low = sas_code.lower()
        r_low = r_code.lower()
        # Strip comments from R code for operational matching
        r_clean = re.sub(r'#.*$', '', r_code, flags=re.MULTILINE).lower()

        req_items = []
        matched_items = []
        missing_ops = []
        notes = []

        # 1. GROUP BY
        if "group by" in sas_low:
            req_items.append("GROUP_BY")
            if any(k in r_clean for k in ["group_by", "aggregate(", "count("]):
                matched_items.append("GROUP_BY")
            else:
                missing_ops.append("GROUP_BY")
                notes.append("SAS contains GROUP BY but generated R lacks group_by().")

        # 2. AGGREGATION (COUNT, SUM, AVG/MEAN, MAX, MIN)
        has_sas_agg = any(k in sas_low for k in ["count(", "sum(", "avg(", "mean(", "max(", "min("])
        if has_sas_agg:
            req_items.append("AGGREGATION")
            if any(k in r_clean for k in ["summarise", "count(", "n()", "sum(", "mean(", "max(", "min("]):
                matched_items.append("AGGREGATION")
            else:
                missing_ops.append("AGGREGATION")
                notes.append("SAS contains aggregate functions but generated R lacks summarise().")

        # 3. HAVING
        if "having" in sas_low:
            req_items.append("HAVING")
            if "filter(" in r_clean:
                matched_items.append("HAVING")
            else:
                missing_ops.append("HAVING")
                notes.append("SAS contains HAVING clause but generated R lacks filter().")

        # 4. ORDER BY
        if "order by" in sas_low or "proc sort" in sas_low:
            req_items.append("ORDER_BY")
            if any(k in r_clean for k in ["arrange(", "order("]):
                matched_items.append("ORDER_BY")
            else:
                missing_ops.append("ORDER_BY")
                notes.append("SAS contains ORDER BY/PROC SORT but generated R lacks arrange().")

        # 5. JOIN
        if "join" in sas_low:
            req_items.append("JOIN")
            if any(k in r_clean for k in ["left_join", "inner_join", "full_join", "right_join", "merge("]):
                matched_items.append("JOIN")
            else:
                missing_ops.append("JOIN")
                notes.append("SAS contains JOIN but generated R lacks left_join().")

        # 6. WHERE / IF filter
        if "where " in sas_low or "if " in sas_low:
            req_items.append("FILTER")
            if any(k in r_clean for k in ["filter(", "["]):
                matched_items.append("FILTER")
            else:
                missing_ops.append("FILTER")
                notes.append("SAS contains filter logic but generated R lacks filter().")

        # 7. EXPRESSION-LEVEL COLUMNS & DERIVATIONS
        # serious_ae
        if "serious_ae" in sas_low or "serious" in sas_low and "sum(" in sas_low:
            req_items.append("COL_serious_ae")
            if "serious_ae" in r_clean or "serious" in r_clean:
                matched_items.append("COL_serious_ae")
            else:
                missing_ops.append("COL_serious_ae")
                notes.append("SAS derives serious_ae column but generated R lacks it.")

        # SEXN
        if "sexn" in sas_low:
            req_items.append("COL_SEXN")
            if "sexn" in r_clean:
                matched_items.append("COL_SEXN")
            else:
                missing_ops.append("COL_SEXN")
                notes.append("SAS derives SEXN variable but generated R lacks it.")

        # STUDYID / STUDY
        if "studyid" in sas_low or "study" in sas_low:
            req_items.append("COL_STUDYID")
            if "studyid" in r_clean or "study" in r_clean:
                matched_items.append("COL_STUDYID")
            else:
                missing_ops.append("COL_STUDYID")
                notes.append("SAS derives STUDYID/STUDY but generated R lacks it.")

        # ANALYSIS_DATE
        if "analysis_date" in sas_low or "today()" in sas_low or "yymmddn8" in sas_low:
            req_items.append("COL_ANALYSIS_DATE")
            if "analysis_date" in r_clean or "sys.date" in r_clean or "today" in r_clean:
                matched_items.append("COL_ANALYSIS_DATE")
            else:
                missing_ops.append("COL_ANALYSIS_DATE")
                notes.append("SAS derives ANALYSIS_DATE but generated R lacks it.")

        # EX_SUM Dataset
        if "ex_sum" in sas_low:
            req_items.append("DS_EX_SUM")
            if "ex_sum" in r_clean:
                matched_items.append("DS_EX_SUM")
            else:
                missing_ops.append("DS_EX_SUM")
                notes.append("SAS creates EX_SUM dataset but generated R lacks EX_SUM pipeline.")

        is_passthrough_fp = PassthroughDetector.is_passthrough(sas_code, r_code)
        if is_passthrough_fp:
            notes.append("CRITICAL: Detected false-positive passthrough assignment (SEMANTIC_CONVERSION_INCOMPLETE).")

        # 8. Variable/Column Semantic Completeness Gate
        col_complete, exp_cols, pres_cols, miss_cols = validate_semantic_completeness(sas_code, r_code)
        if not col_complete:
            notes.append(f"SEMANTIC COMPLETENESS FAIL: Missing required output columns/variables: {', '.join(miss_cols)}")

        # Expression-Level Completeness Score
        total_req = len(req_items)
        total_match = len(matched_items)

        if total_req == 0:
            completeness_score = 100.0 if col_complete else 50.0
            is_equivalent = col_complete
        else:
            completeness_score = round((total_match / total_req) * 100.0, 1) if col_complete else min(round((total_match / total_req) * 100.0, 1), 50.0)
            is_equivalent = (len(missing_ops) == 0) and (not is_passthrough_fp) and col_complete and (completeness_score >= 95.0)

        # Cap confidence score strictly by completeness
        confidence_score = completeness_score if is_equivalent else min(completeness_score, 80.0)

        return SemanticValidationResult(
            is_equivalent=is_equivalent,
            confidence_score=confidence_score,
            detected_sas_ops=req_items,
            detected_r_ops=matched_items,
            missing_r_ops=missing_ops,
            is_passthrough_false_positive=is_passthrough_fp,
            review_notes=notes,
            missing_columns=miss_cols,
            expected_columns=exp_cols
        )


class DataLevelValidator:
    """Deterministically validates expected tabular output for benchmark datasets."""

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
        
        expected_custs = list(expected["cust_id"])
        actual_custs = list(result_df["cust_id"])
        if expected_custs != actual_custs:
            return False

        for i in range(len(expected)):
            if abs(result_df.loc[i, "total_spent"] - expected.loc[i, "total_spent"]) > 0.001:
                return False

        return True

    @staticmethod
    def expected_clinical_result() -> dict[str, pd.DataFrame]:
        """Expected tabular results for User Complex Clinical Macro."""
        # DM Dataset
        dm_data = [
            {"usubjid": "01-001", "age": 45, "sex": "M", "SAFFL": "Y"},
            {"usubjid": "01-002", "age": 17, "sex": "F", "SAFFL": "Y"},  # filtered out age < 18
            {"usubjid": "01-003", "age": 60, "sex": "F", "SAFFL": "Y"}
        ]
        dm_df = pd.DataFrame(dm_data)
        adsl_df = dm_df[dm_df["age"] >= 18].copy()
        adsl_df["SEXN"] = adsl_df["sex"].map({"M": 1, "F": 2})
        adsl_df["STUDYID"] = "STUDY001"

        # AE Dataset
        ae_data = [
            {"usubjid": "01-001", "serious": "Y", "severity": 3},
            {"usubjid": "01-001", "serious": "N", "severity": 1},
            {"usubjid": "01-003", "serious": "N", "severity": 2}
        ]
        ae_df = pd.DataFrame(ae_data)
        adae_sum = ae_df.groupby("usubjid").agg(
            total_ae=("serious", "count"),
            serious_ae=("serious", lambda s: (s == "Y").sum()),
            max_severity=("severity", "max")
        ).reset_index()

        # EX Dataset
        ex_data = [
            {"usubjid": "01-001", "dose": 100},
            {"usubjid": "01-003", "dose": 200}
        ]
        ex_df = pd.DataFrame(ex_data)
        ex_sum = ex_df.groupby("usubjid").agg(
            exposure_records=("dose", "count"),
            total_dose=("dose", "sum"),
            avg_dose=("dose", "mean"),
            max_dose=("dose", "max"),
            min_dose=("dose", "min")
        ).reset_index()

        # Merged ADSL_FINAL
        final_df = adsl_df.merge(adae_sum, on="usubjid", how="left")
        final_df["RISK_CATEGORY"] = final_df["total_ae"].apply(
            lambda x: "HIGH" if x >= 5 else ("MEDIUM" if x >= 2 else "LOW")
        )
        final_df["ANALYSIS_FLAG"] = "Y"
        final_sorted = final_df.sort_values(by=["total_ae", "usubjid"], ascending=[False, True]).reset_index(drop=True)

        return {
            "ADSL": adsl_df,
            "ADAE_SUM": adae_sum,
            "EX_SUM": ex_sum,
            "ADSL_FINAL": final_sorted
        }
