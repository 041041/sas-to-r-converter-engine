%include "util_chkvars.sas";
%include "util_num_periods.sas";
%include "gen_tp_join_adsl.sas";

%gen_tp_join_adsl(_dsnin=adsl, _dsnout=adsl_out, _trtoption=OPTION1, _analstartdtvar=ADT);

proc print data=adsl_out;
run;
