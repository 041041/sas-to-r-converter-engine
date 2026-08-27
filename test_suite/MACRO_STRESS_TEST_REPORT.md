# SAS → R Macro Architecture Stress Test Report

**Date/Time**: Deterministic Automated Stress Run  
**Total Stress Tests**: 125  
**Passed**: 118  
**Failed**: 7  
**Pass Rate**: **94.4%**  

## 1. Complexity Breakdown

| Complexity | Total | Passed | Failed | Pass Rate |
| :--- | :---: | :---: | :---: | :---: |
| **BASIC** | 25 | 25 | 0 | 100.0% |
| **MODERATE** | 25 | 24 | 1 | 96.0% |
| **COMPLEX** | 25 | 25 | 0 | 100.0% |
| **VERY_COMPLEX** | 25 | 25 | 0 | 100.0% |
| **TORTURE** | 25 | 19 | 6 | 76.0% |

## 2. Macro Path Classification Results

| Path Architecture | Total | Passed | Failed | Pass Rate |
| :--- | :---: | :---: | :---: | :---: |
| **PATH_A (Compile-time Template)** | 68 | 63 | 5 | 92.6% |
| **PATH_B (Reusable R Utility)** | 79 | 77 | 2 | 97.5% |

## 3. Failure Categories Summary

| Failure Category | Count |
| :--- | :---: |
| `R_SYNTAX_FAILURE` | 7 |

## 4. Top Failures & Minimized Reproductions

### 1. MODERATE_029 (MODERATE)
- **Category**: `R_SYNTAX_FAILURE`
- **Description**: Macro containing PROC SORT step
- **Details**: `Rscript syntax parse check failed: Error in parse("/Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_MODERATE_029.R") : 
  /Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_MODERATE_029.R:16:38: unexpected symbol
15: 
16: AE_SORTED <- sort_domain(AE, USUBJID AEDECOD
                                         ^
Execution halted`
- **Reproduction Command**:
  ```bash
  python3 -c 'from test_suite.run_macro_stress_tests import check_test_case; import json; print(check_test_case(json.load(open("test_suite/generated_macro_cases/MODERATE_029.json"))))'
  ```
- **Artifacts Path**: [file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/MODERATE_029](file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/MODERATE_029)

### 2. TORTURE_102 (TORTURE)
- **Category**: `R_SYNTAX_FAILURE`
- **Description**: Macro parameters with %str quotes, whitespace around =, and multiline defaults
- **Details**: `Generated R contains residual '%func(...)' macro call syntax`
- **Reproduction Command**:
  ```bash
  python3 -c 'from test_suite.run_macro_stress_tests import check_test_case; import json; print(check_test_case(json.load(open("test_suite/generated_macro_cases/TORTURE_102.json"))))'
  ```
- **Artifacts Path**: [file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_102](file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_102)

### 3. TORTURE_106 (TORTURE)
- **Category**: `R_SYNTAX_FAILURE`
- **Description**: Dynamic PROC SQL complex join and aggregation macro TORTURE_MAC_106
- **Details**: `Rscript syntax parse check failed: Error in parse("/Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_106.R") : 
  /Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_106.R:5:35: unexpected symbol
4:   dplyr::inner_join(LB, by = "USUBJID") %>%
5:   dplyr::filter(AGE >= 18  &  not missing
                                     ^
Execution halted`
- **Reproduction Command**:
  ```bash
  python3 -c 'from test_suite.run_macro_stress_tests import check_test_case; import json; print(check_test_case(json.load(open("test_suite/generated_macro_cases/TORTURE_106.json"))))'
  ```
- **Artifacts Path**: [file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_106](file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_106)

### 4. TORTURE_110 (TORTURE)
- **Category**: `R_SYNTAX_FAILURE`
- **Description**: Dynamic PROC SQL complex join and aggregation macro TORTURE_MAC_110
- **Details**: `Rscript syntax parse check failed: Error in parse("/Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_110.R") : 
  /Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_110.R:5:35: unexpected symbol
4:   dplyr::inner_join(LB, by = "USUBJID") %>%
5:   dplyr::filter(AGE >= 18  &  not missing
                                     ^
Execution halted`
- **Reproduction Command**:
  ```bash
  python3 -c 'from test_suite.run_macro_stress_tests import check_test_case; import json; print(check_test_case(json.load(open("test_suite/generated_macro_cases/TORTURE_110.json"))))'
  ```
- **Artifacts Path**: [file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_110](file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_110)

### 5. TORTURE_114 (TORTURE)
- **Category**: `R_SYNTAX_FAILURE`
- **Description**: Dynamic PROC SQL complex join and aggregation macro TORTURE_MAC_114
- **Details**: `Rscript syntax parse check failed: Error in parse("/Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_114.R") : 
  /Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_114.R:5:35: unexpected symbol
4:   dplyr::inner_join(LB, by = "USUBJID") %>%
5:   dplyr::filter(AGE >= 18  &  not missing
                                     ^
Execution halted`
- **Reproduction Command**:
  ```bash
  python3 -c 'from test_suite.run_macro_stress_tests import check_test_case; import json; print(check_test_case(json.load(open("test_suite/generated_macro_cases/TORTURE_114.json"))))'
  ```
- **Artifacts Path**: [file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_114](file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_114)

### 6. TORTURE_118 (TORTURE)
- **Category**: `R_SYNTAX_FAILURE`
- **Description**: Dynamic PROC SQL complex join and aggregation macro TORTURE_MAC_118
- **Details**: `Rscript syntax parse check failed: Error in parse("/Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_118.R") : 
  /Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_118.R:5:35: unexpected symbol
4:   dplyr::inner_join(LB, by = "USUBJID") %>%
5:   dplyr::filter(AGE >= 18  &  not missing
                                     ^
Execution halted`
- **Reproduction Command**:
  ```bash
  python3 -c 'from test_suite.run_macro_stress_tests import check_test_case; import json; print(check_test_case(json.load(open("test_suite/generated_macro_cases/TORTURE_118.json"))))'
  ```
- **Artifacts Path**: [file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_118](file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_118)

### 7. TORTURE_122 (TORTURE)
- **Category**: `R_SYNTAX_FAILURE`
- **Description**: Dynamic PROC SQL complex join and aggregation macro TORTURE_MAC_122
- **Details**: `Rscript syntax parse check failed: Error in parse("/Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_122.R") : 
  /Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/_temp_TORTURE_122.R:5:35: unexpected symbol
4:   dplyr::inner_join(LB, by = "USUBJID") %>%
5:   dplyr::filter(AGE >= 18  &  not missing
                                     ^
Execution halted`
- **Reproduction Command**:
  ```bash
  python3 -c 'from test_suite.run_macro_stress_tests import check_test_case; import json; print(check_test_case(json.load(open("test_suite/generated_macro_cases/TORTURE_122.json"))))'
  ```
- **Artifacts Path**: [file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_122](file:///Users/sandeep/.gemini/antigravity/scratch/sas-to-r-converter-cleaned/test_suite/failure_artifacts/TORTURE_122)
