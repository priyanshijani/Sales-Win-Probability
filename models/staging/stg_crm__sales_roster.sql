select
    "Employee ID"                                               as employee_id,
    trim("Full Name")                                           as full_name,
    {{ name_key('"Full Name"') }}                               as name_key,
    lower(trim("Email"))                                        as email,
    "Role"                                                      as role,
    {{ alias('department', '"Department"') }}                   as department,
    nullif(trim("Sales Manager"), '')                           as sales_manager,
    "Territory"                                                 as territory,
    {{ parse_date('"Hire Date"') }}                             as hire_date,
    {{ parse_date('"Leave Date"') }}                            as leave_date,
    try_cast("Annual Quota (EUR)" as double)                    as annual_quota_eur
from read_csv('{{ var("raw_dir") }}/sales_team_roster.csv', all_varchar = true)
