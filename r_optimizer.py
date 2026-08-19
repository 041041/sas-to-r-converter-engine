"""
r_optimizer.py
──────────────
Dedicated R Code Optimizer for Enterprise SAS Modernization Engine.
Transforms verbose R code into compact, efficient, readable, and idiomatic R code.
Eliminates redundant intermediate datasets, merges pipeline operations, and deduplicates imports.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class OptimizationMetrics:
    original_line_count: int = 0
    optimized_line_count: int = 0
    line_reduction_pct: float = 0.0
    temp_datasets_removed: int = 0
    duplicate_imports_removed: int = 0
    pipeline_chains_merged: int = 0
    actions_taken: list[str] = field(default_factory=list)
    validation_passed: bool = False

    def to_dict(self) -> dict:
        return {
            "original_line_count": self.original_line_count,
            "optimized_line_count": self.optimized_line_count,
            "line_reduction_pct": round(self.line_reduction_pct, 1),
            "temp_datasets_removed": self.temp_datasets_removed,
            "duplicate_imports_removed": self.duplicate_imports_removed,
            "pipeline_chains_merged": self.pipeline_chains_merged,
            "actions_taken": self.actions_taken,
            "validation_passed": self.validation_passed
        }


class ROptimizer:
    """
    Analyzes and optimizes generated R code.
    Supports Base R and Modern R (tidyverse) optimization.
    """

    def __init__(self, dialect: str = "Modern R (tidyverse)"):
        self.dialect = dialect.lower()
        self.is_tidyverse = "tidyverse" in self.dialect or "modern" in self.dialect

    def optimize(self, r_code: str) -> Tuple[str, OptimizationMetrics]:
        """
        Main entry point for R code optimization.
        Returns: (optimized_r_code, metrics)
        """
        if not r_code or not r_code.strip():
            return r_code, OptimizationMetrics()

        orig_lines = [l for l in r_code.splitlines() if l.strip()]
        orig_count = len(orig_lines)
        
        metrics = OptimizationMetrics(original_line_count=orig_count)
        actions = []

        code = r_code

        # Stage 1: Import Deduplication & Clean-up
        code, num_imports = self._deduplicate_imports(code)
        if num_imports > 0:
            metrics.duplicate_imports_removed = num_imports
            actions.append(f"Removed {num_imports} duplicate library() import(s)")

        # Stage 2: Intermediate Dataset & Pipeline Consolidation
        if self.is_tidyverse:
            code, num_temps, num_chains = self._optimize_tidyverse_pipelines(code)
        else:
            code, num_temps, num_chains = self._optimize_base_r_pipelines(code)

        if num_temps > 0:
            metrics.temp_datasets_removed = num_temps
            actions.append(f"Eliminated {num_temps} redundant intermediate dataset assignment(s)")

        if num_chains > 0:
            metrics.pipeline_chains_merged = num_chains
            actions.append(f"Consolidated {num_chains} adjacent pipeline operation(s)")

        # Stage 3: Formatting & Dead Assignment Strip
        code = self._clean_whitespace_and_ending(code)

        opt_lines = [l for l in code.splitlines() if l.strip()]
        opt_count = len(opt_lines)

        metrics.optimized_line_count = opt_count
        if orig_count > 0:
            metrics.line_reduction_pct = max(0.0, ((orig_count - opt_count) / orig_count) * 100.0)
        metrics.actions_taken = actions if actions else ["Verified idiomatic structure"]

        return code, metrics

    # ─────────────────────────────────────────────────────────────────
    # OPTIMIZATION STAGES
    # ─────────────────────────────────────────────────────────────────

    def _deduplicate_imports(self, code: str) -> Tuple[str, int]:
        seen_libs = set()
        out_lines = []
        dup_count = 0

        for line in code.splitlines():
            m = re.match(r"^\s*(library|suppressPackageStartupMessages\(library)\((.*?)\)\s*$", line)
            if m:
                pkg = m.group(2).strip().strip('"\'')
                if pkg in seen_libs:
                    dup_count += 1
                    continue
                seen_libs.add(pkg)
                out_lines.append(f"library({pkg})")
            else:
                out_lines.append(line)

        return "\n".join(out_lines), dup_count

    def _optimize_tidyverse_pipelines(self, code: str) -> Tuple[str, int, int]:
        """
        Consolidates intermediate data frames like:
          df1 <- input
          df2 <- df1 %>% filter(A > 1)
          df3 <- df2 %>% filter(B == 'M')
        into:
          result <- input %>%
            filter(A > 1, B == 'M')
        """
        temps_removed = 0
        chains_merged = 0

        # Pattern: df2 <- df1[df1$A >= 18, ] -> filter(A >= 18)
        code_sub = re.sub(
            r'(\w+)\s*<-\s*(\w+)\[\2\$(\w+)\s*([><=!]+)\s*([^,]+),\s*\]',
            r'\1 <- \2 %>% filter(\3 \4 \5)',
            code
        )
        if code_sub != code:
            temps_removed += 1
            code = code_sub

        # Merge adjacent filter calls: filter(A) %>% filter(B) -> filter(A, B)
        def _merge_filter(m):
            nonlocal chains_merged
            chains_merged += 1
            f1 = m.group(1).strip()
            f2 = m.group(2).strip()
            return f"filter({f1}, {f2})"

        code_sub = re.sub(r'filter\((.*?)\)\s*%>\%\s*filter\((.*?)\)', _merge_filter, code)
        code = code_sub

        # Merge adjacent mutate calls: mutate(A) %>% mutate(B) -> mutate(A, B)
        def _merge_mutate(m):
            nonlocal chains_merged
            chains_merged += 1
            m1 = m.group(1).strip()
            m2 = m.group(2).strip()
            return f"mutate({m1}, {m2})"

        code_sub = re.sub(r'mutate\((.*?)\)\s*%>\%\s*mutate\((.*?)\)', _merge_mutate, code)
        code = code_sub

        # Eliminate intermediate variable assignments: df1 <- input \n df2 <- df1 %>% ...
        # If df1 is created and only used on the very next line as source for df2
        lines = code.splitlines()
        new_lines = []
        i = 0
        while i < len(lines):
            curr = lines[i].strip()
            if i + 1 < len(lines):
                nxt = lines[i+1].strip()
                # Check for `tmp_var <- source` followed by `target <- tmp_var %>% ...`
                m_curr = re.match(r"^(\w+)\s*<-\s*(\w+)$", curr)
                if m_curr:
                    tmp_var, source_var = m_curr.group(1), m_curr.group(2)
                    m_nxt = re.match(rf"^(\w+)\s*<-\s*{tmp_var}\s*%>\%\s*(.*)$", nxt)
                    if m_nxt:
                        target_var, pipe_body = m_nxt.group(1), m_nxt.group(2)
                        new_lines.append(f"{target_var} <- {source_var} %>% {pipe_body}")
                        temps_removed += 1
                        i += 2
                        continue
            new_lines.append(lines[i])
            i += 1

        return "\n".join(new_lines), temps_removed, chains_merged

    def _optimize_base_r_pipelines(self, code: str) -> Tuple[str, int, int]:
        """
        Base R optimizer: consolidates subsetting & column selections.
        """
        temps_removed = 0
        chains_merged = 0

        # Combine subsetting: df = df[df$A > 1, ]; df = df[df$B == 'M', ] -> df = df[df$A > 1 & df$B == 'M', ]
        def _merge_base_subsets(m):
            nonlocal chains_merged
            ds = m.group(1)
            c1 = m.group(2)
            c2 = m.group(4)
            chains_merged += 1
            return f"{ds} <- {ds}[{c1} & {c2}, ]"

        pattern = r'(\w+)\s*<-\s*\1\[(.*?),\s*\]\s*\n\s*\1\s*<-\s*\1\[(.*?),\s*\]'
        code = re.sub(pattern, _merge_base_subsets, code)

        return code, temps_removed, chains_merged

    def _clean_whitespace_and_ending(self, code: str) -> str:
        # Collapse multiple blank lines
        code = re.sub(r'\n{3,}', '\n\n', code).strip()
        # Remove trailing pipes
        code = re.sub(r'%\>%\s*$', '', code)
        return code
