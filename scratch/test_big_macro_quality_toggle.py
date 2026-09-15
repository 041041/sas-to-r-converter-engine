"""
scratch/test_big_macro_quality_toggle.py
──────────────────────────────────────────
Test the BIG_MACRO 3-file project with stable anchored header shell and native details quality dropdown.
"""

from streamlit.testing.v1 import AppTest
from project_engine.analyzer import ProjectAnalyzer
from project_engine.validation import ProjectValidator

def test_big_macro_project_quality_toggle():
    print("--- Testing BIG_MACRO 3-file project with stable anchored header shell ---")

    files = [
        ("BIG_MACRO.sas", "%include 'MACRO_A.sas'; %include 'MACRO_B.sas'; %macro_a(in=WORK.DS1); %macro_b(in=WORK.DS2);"),
        ("MACRO_A.sas", "%macro macro_a(in=); data WORK.STEP_A; set &in; run; %mend macro_a;"),
        ("MACRO_B.sas", "%macro macro_b(in=); data WORK.STEP_B; set &in; run; %mend macro_b;"),
    ]

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project(files, main_filename="BIG_MACRO.sas")
    ProjectValidator().validate(ctx)

    at = AppTest.from_file("app.py", default_timeout=30).run()
    at.session_state["project_context"] = ctx
    at.text_area[0].input(ctx.main_program_content).run()
    at.button[0].click().run()

    from project_engine.quality import evaluate_quality_summary
    qs = evaluate_quality_summary(project_context=ctx, r_code="# converted R code")
    print(f"BIG_MACRO Project Resolution: {qs.project_resolution_label}")
    print(f"Confidence: {qs.confidence_percentage}% ({qs.confidence_band.value}) | Status: {qs.status.value}")
    assert qs.is_project is True
    assert qs.files_count == 3
    assert qs.macros_count == 2
    assert "Fully Resolved" in qs.project_resolution_label

    print("✅ BIG_MACRO 3-file project stable anchored header shell verification PASSED!\n")

if __name__ == "__main__":
    test_big_macro_project_quality_toggle()
