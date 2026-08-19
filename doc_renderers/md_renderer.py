"""
doc_renderers/md_renderer.py
────────────────────────────
Markdown Exporter for Modernization Document Model.
Renders the 10-section report into clean, publication-ready GitHub-flavored Markdown.
"""

from __future__ import annotations
from doc_generator import ModernizationDocument


def render_markdown(doc: ModernizationDocument) -> str:
    md = []
    
    md.append(f"# 🚀 SAS Modernization Report: {doc.program_name}\n")
    
    # Section 1: Executive Summary
    md.append("## 1. Executive Summary")
    md.append(f"{doc.executive_summary}\n")
    
    # Section 2: Original SAS Metadata
    md.append("## 2. Original SAS Metadata")
    md.append(f"- **Program Name**: `{doc.program_name}`")
    md.append(f"- **Input Datasets**: `{', '.join(doc.input_datasets) if doc.input_datasets else 'None'}`")
    md.append(f"- **Output Datasets**: `{', '.join(doc.output_datasets) if doc.output_datasets else 'None'}`")
    md.append("- **Libraries / Data Sources**:")
    for lib, val in doc.libraries.items():
        md.append(f"  - `{lib}` $\\rightarrow$ `{val}`")
    if not doc.libraries:
        md.append("  - *None defined*")
    md.append("\n")
    
    # Section 3: SAS Logic Analysis
    md.append("## 3. SAS Logic Analysis")
    md.append("| Step # | Name | Type | Method | Confidence |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")
    for s in doc.step_descriptions:
        md.append(f"| {s['step_index']} | `{s['name']}` | `{s['type']}` | `{s['method']}` | {s['confidence']} |")
    md.append("\n")
    
    # Section 4: Macro Analysis
    md.append("## 4. Macro Analysis")
    if doc.macro_summaries:
        for m in doc.macro_summaries:
            md.append(f"### Macro: `{m['name']}`")
            md.append(f"- **Parameters**: `{', '.join(m['params']) if m['params'] else 'None'}`")
            md.append(f"- **Complexity Score**: `{m['complexity_score']}/100`")
            md.append(f"- **Nested Macro Calls**: `{', '.join(m['nested_calls']) if m['nested_calls'] else 'None'}`")
            md.append(f"- **Dynamic Naming**: `{'Yes ⚠️' if m['has_dynamic_naming'] else 'No'}`")
    else:
        md.append("*No macros defined in this program.*\n")
    md.append("\n")
    
    # Section 5: SAS -> R Mapping Table
    md.append("## 5. SAS → R Construct Mapping")
    md.append("| SAS Construct | Target R Equivalent | Confidence | Translation Method |")
    md.append("| :--- | :--- | :--- | :--- |")
    for row in doc.mapping_table:
        md.append(f"| `{row.sas_construct}` | `{row.r_equivalent}` | **{row.confidence}** | `{row.method}` |")
    md.append("\n")
    
    # Section 6: Generated R Architecture & Optimization Metrics
    md.append("## 6. R Code Optimization Metrics")
    opt = doc.optimization_summary
    md.append(f"- **Original R Lines**: `{opt.get('original_line_count', 0)}`")
    md.append(f"- **Optimized R Lines**: `{opt.get('optimized_line_count', 0)}`")
    md.append(f"- **Line Reduction**: **`{opt.get('line_reduction_pct', 0.0):.1f}%`**")
    md.append(f"- **Redundant Intermediate Datasets Removed**: `{opt.get('temp_datasets_removed', 0)}`")
    md.append(f"- **Duplicate Imports Removed**: `{opt.get('duplicate_imports_removed', 0)}`")
    md.append(f"- **Pipeline Operations Merged**: `{opt.get('pipeline_chains_merged', 0)}`")
    md.append("- **Optimization Actions Log**:")
    for act in opt.get('actions_taken', []):
        md.append(f"  - ✓ {act}")
    md.append("\n")
    
    # Section 7: Generated R Code
    md.append("## 7. Final Optimized R Code")
    md.append("```r")
    md.append(doc.final_optimized_r)
    md.append("```\n")
    
    # Section 8: Validation Results
    md.append("## 8. Validation Results")
    md.append(f"- **Status**: **{doc.validation_status}**")
    md.append(f"- **Details**: {doc.validation_details}\n")
    
    # Section 9: Manual Review Items
    md.append("## 9. Manual Review Items")
    if doc.manual_review_items:
        for item in doc.manual_review_items:
            md.append(f"- ⚠️ {item}")
    else:
        md.append("✅ *No manual review items flagged. 100% automated conversion.*")
    md.append("\n")
    
    # Section 10: Conversion Confidence
    md.append("## 10. Conversion Confidence & Rationale")
    md.append(f"- **Overall Confidence Score**: **`{doc.overall_confidence}%`**")
    md.append(f"- **Rationale**: {doc.confidence_rationale}\n")
    
    return "\n".join(md)
