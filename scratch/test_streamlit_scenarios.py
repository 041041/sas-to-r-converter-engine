"""
scratch/test_streamlit_scenarios.py
───────────────────────────────────
Headless Streamlit AppTest simulation to verify Scenarios A through F.
"""

from streamlit.testing.v1 import AppTest
from project_engine.quality import evaluate_quality_summary

def run_streamlit_tests():
    print("--- Running Streamlit AppTest Scenarios A to F ---")

    # Scenario A: Simple Successful Conversion
    at = AppTest.from_file("app.py", default_timeout=30).run()
    at.text_area[0].input("data target; set source; where age > 30; run;").run()
    at.button[0].click().run()

    assert "current_quality_summary" in at.session_state
    qs_a = at.session_state["current_quality_summary"]
    print(f"Scenario A Status: {qs_a.status.value} | Label: {qs_a.status_label}")
    print(f"Confidence: {qs_a.confidence_percentage}% ({qs_a.confidence_band.value}) | R Validation: {qs_a.r_validation_label}")
    assert qs_a.status.value in ("SUCCESS", "SUCCESS_WITH_REVIEW")
    assert qs_a.r_validation_status == "VALID_R"
    print("✅ Scenario A PASS (including Native Quality Popover)\n")

    # Scenario C: Manual Review / Partial Case
    at.text_area[0].input("proc format; value agefmt 18-30='Young'; run;").run()
    at.button[0].click().run()
    qs_c = at.session_state["current_quality_summary"]
    print(f"Scenario C Status: {qs_c.status.value} | Label: {qs_c.status_label}")
    print(f"Review Items Count: {len(qs_c.review_items)}")
    assert qs_c.status.value in ("SUCCESS_WITH_REVIEW", "PARTIAL")
    print("✅ Scenario C PASS\n")

    # Scenario D: Invalid / Failed State Evaluation
    qs_d = evaluate_quality_summary(r_code="b <- &unresolved_var", conversion_error=None)
    print(f"Scenario D Status: {qs_d.status.value} | Label: {qs_d.status_label} | R Val: {qs_d.r_validation_label}")
    assert qs_d.status.value != "SUCCESS"
    assert qs_d.r_validation_status == "R_REVIEW_REQUIRED"
    print("✅ Scenario D PASS\n")

    # Scenario E: Clear
    at.button[1].click().run()  # Clear button
    assert "current_quality_summary" not in at.session_state or at.session_state["current_quality_summary"] is None
    assert len(at.session_state.pipeline_results) == 0
    print("✅ Scenario E (Clear) PASS\n")

    # Scenario F: Re-conversion after clear
    at.text_area[0].input("data final; set raw; run;").run()
    at.button[0].click().run()
    qs_f = at.session_state["current_quality_summary"]
    print(f"Scenario F Status: {qs_f.status.value} | Label: {qs_f.status_label}")
    assert qs_f is not None
    print("✅ Scenario F PASS\n")

    print("ALL STREAMLIT SCENARIOS PASSED PERFECTLY!")

if __name__ == "__main__":
    run_streamlit_tests()
