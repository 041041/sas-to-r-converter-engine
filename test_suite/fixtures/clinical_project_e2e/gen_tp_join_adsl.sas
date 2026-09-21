%macro GEN_TP_JOIN_ADSL(_dsnin=adsl, _dsnout=, _trtoption=OPTION1, _dropvars=, _analstartdtvar=ADT);
    %UTIL_NUM_PERIODS(_dsn=&_dsnin);
    %UTIL_CHKVARS(_dsnin=&_dsnin, _varlist=&_dropvars);
%mend GEN_TP_JOIN_ADSL;
