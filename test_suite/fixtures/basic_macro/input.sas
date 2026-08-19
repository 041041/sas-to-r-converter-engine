%macro filter_data(min_age=18);
    data work.dm_filtered;
        set work.dm;
        if age >= &min_age;
    run;
%mend filter_data;

%filter_data(min_age=18);
