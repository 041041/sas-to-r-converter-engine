"""
test_suite/test_false_dependency_regression.py
─────────────────────────────────────────────────
Regression tests for false macro dependency filtering and macro definition precedence.
Ensures SAS macro control language keywords (%TO, %WHILE, %QSCAN, %QUIT, etc.) are never
reported as unresolved project macro dependencies.
"""

import pytest
from project_engine import (
    ProjectAnalyzer,
    ResolutionStatus,
    DependencyParser
)
from project_engine.models import DependencyType


def test_customer_large_macro_builtins_not_unresolved():
    """
    Step 5 Test Case:
    Customer's macro pattern with %TO, %WHILE, %QSCAN, %QUIT, %IF, %THEN, %LET, %LOCAL, %EVAL.
    Must NOT be reported as unresolved project dependencies.
    """
    chkvars_code = '''
%macro UTIL_CHKVARS(ds, varlist);
   %local i var;
   %let i=1;

   %do %while(&i <= 10);
      %let var=%qscan(&varlist, &i);
      %if &i = 1 %then %do;
         %put Checking variable &var;
      %end;
      %let i=%eval(&i + 1);
   %end;

   %if &i > 10 %then %do;
      %goto finish;
   %end;

   %quit;

   finish:
%mend;
'''

    join_adsl_code = '''
%macro GEN_TP_JOIN_ADSL();
   %do i=1 %to 10;
      %put Iteration &i;
   %end;
%mend;
'''

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("UTIL_CHKVARS.sas", chkvars_code),
        ("GEN_TP_JOIN_ADSL.sas", join_adsl_code)
    ], main_filename="GEN_TP_JOIN_ADSL.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert len(ctx.resolution_result.missing_dependencies) == 0
    assert len(ctx.errors) == 0

    # Verify none of the built-ins appear as dependency edges
    dependencies = {edge.dependency for edge in ctx.dependency_graph.edges}
    forbidden_builtins = {"TO", "WHILE", "QSCAN", "QUIT", "DO", "END", "IF", "THEN", "LET", "LOCAL", "EVAL", "GOTO", "PUT"}
    intersection = dependencies.intersection(forbidden_builtins)
    assert len(intersection) == 0, f"Built-ins found as dependencies: {intersection}"


def test_real_nested_user_macros():
    """
    Step 6 Test Case:
    4 nested user-defined macros: MAIN -> B -> A -> UTIL.
    Expected:
    - 4 macros discovered
    - 3 user-defined macro dependency edges
    - all 4 resolved
    - no false dependencies
    """
    util_code = "%macro UTIL(); proc print data=sashelp.class; run; %mend;"
    a_code = "%macro A(); %UTIL(); %mend;"
    b_code = "%macro B(); %A(); %mend;"
    main_code = "%macro MAIN(); %B(); %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("UTIL.sas", util_code),
        ("A.sas", a_code),
        ("B.sas", b_code),
        ("MAIN.sas", main_code)
    ], main_filename="MAIN.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert len(ctx.macro_registry) == 4
    assert set(ctx.macro_registry.keys()) == {"UTIL", "A", "B", "MAIN"}

    macro_edges = [
        (e.caller, e.dependency) for e in ctx.dependency_graph.edges
        if e.dependency_type == DependencyType.MACRO_CALL
    ]

    expected_edges = {("MAIN", "B"), ("B", "A"), ("A", "UTIL")}
    assert set(macro_edges) == expected_edges
    assert ctx.dependency_order == ["UTIL", "A", "B", "MAIN"]


def test_mixed_realistic_macro_library():
    """
    Step 7 Test Case:
    Realistic macro library containing PROC SQL, PROC SORT, nested user macros, and SAS control keywords:
    %IF, %THEN, %ELSE, %DO, %END, %WHILE, %TO, %BY, %LET, %LOCAL, %QSCAN, %SCAN, %SUBSTR, %SYSFUNC, %EVAL, %QUIT.
    Only actual user-defined macro calls appear in the dependency graph.
    """
    lib_code = '''
%macro HELPER_SORT(data=, out=, by=);
   proc sort data=&data out=&out;
      by &by;
   run;
%mend;

%macro HELPER_QUERY(data=, out=);
   %local nvar;
   %let nvar=%sysfunc(countw(&data));
   proc sql noprint;
      create table &out as
      select * from &data;
   quit;
%mend;

%macro PROCESS_DATA(in=, out=, byvar=);
   %local i var sub;
   %let i=1;

   %do %while(&i <= 5);
      %let var=%qscan(&byvar, &i);
      %let sub=%substr(&var, 1, 3);
      %if %length(&var) > 0 %then %do;
         %HELPER_SORT(data=&in, out=work.sorted_&i, by=&var);
         %HELPER_QUERY(data=work.sorted_&i, out=work.out_&i);
      %end;
      %else %do;
         %put Empty var;
      %end;
      %let i=%eval(&i + 1);
   %end;
%mend;
'''

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([("library.sas", lib_code)], main_filename="library.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert len(ctx.macro_registry) == 3
    assert set(ctx.macro_registry.keys()) == {"HELPER_SORT", "HELPER_QUERY", "PROCESS_DATA"}

    edges = {(e.caller, e.dependency) for e in ctx.dependency_graph.edges}
    assert edges == {("PROCESS_DATA", "HELPER_SORT"), ("PROCESS_DATA", "HELPER_QUERY")}


def test_macro_definition_takes_precedence_over_builtin():
    """
    Step 4 Test Case:
    User defines a custom macro matching a built-in keyword name (e.g. %macro SCAN).
    Because it is defined in the project, calling %SCAN() must be registered as a user-defined macro dependency edge.
    """
    scan_def = "%macro SCAN(str, idx); data _null_; run; %mend;"
    caller_def = "%macro MY_CALLER(); %SCAN(hello, 1); %mend;"

    analyzer = ProjectAnalyzer()
    ctx = analyzer.analyze_project([
        ("scan.sas", scan_def),
        ("caller.sas", caller_def)
    ], main_filename="caller.sas")

    assert ctx.resolution_result.status == ResolutionStatus.RESOLVED
    assert "SCAN" in ctx.macro_registry
    assert ("MY_CALLER", "SCAN") in {(e.caller, e.dependency) for e in ctx.dependency_graph.edges}
