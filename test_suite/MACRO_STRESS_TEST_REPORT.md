# SAS → R Macro Architecture Stress Test Report

**Date/Time**: Deterministic Automated Stress Run  
**Total Stress Tests**: 125  
**Passed**: 124  
**Failed**: 1  
**Pass Rate**: **99.2%**  

## 1. Complexity Breakdown

| Complexity | Total | Passed | Failed | Pass Rate |
| :--- | :---: | :---: | :---: | :---: |
| **BASIC** | 25 | 25 | 0 | 100.0% |
| **MODERATE** | 25 | 24 | 1 | 96.0% |
| **COMPLEX** | 25 | 25 | 0 | 100.0% |
| **VERY_COMPLEX** | 25 | 25 | 0 | 100.0% |
| **TORTURE** | 25 | 25 | 0 | 100.0% |

## 2. Macro Path Classification Results

| Path Architecture | Total | Passed | Failed | Pass Rate |
| :--- | :---: | :---: | :---: | :---: |
| **PATH_A (Compile-time Template)** | 68 | 68 | 0 | 100.0% |
| **PATH_B (Reusable R Utility)** | 79 | 78 | 1 | 98.7% |

## 3. Failure Categories Summary

| Failure Category | Count |
| :--- | :---: |
| `R_SYNTAX_FAILURE` | 1 |

## 4. Top Failures & Minimized Reproductions

### 1. MODERATE_029 (MODERATE)
- **Category**: `R_SYNTAX_FAILURE`
- **Description**: Macro containing PROC SORT step
- **Details**: `Rscript syntax parse check failed: Error in parse("/Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_MODERATE_029.R") : 
  /Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_MODERATE_029.R:17:38: unexpected symbol
16: 
17: AE_SORTED <- sort_domain(AE, USUBJID AEDECOD
                                         ^
Execution halted`
- **Reproduction Command**:
  ```bash
  python3 -c 'from test_suite.run_macro_stress_tests import check_test_case; import json; print(check_test_case(json.load(open("test_suite/generated_macro_cases/MODERATE_029.json"))))'
  ```
- **Artifacts Path**: [file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/MODERATE_029](file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/MODERATE_029)
