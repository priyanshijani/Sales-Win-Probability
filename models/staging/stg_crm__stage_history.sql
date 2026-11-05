{# Audit log: keep only Stage changes, parse the 3 timestamp formats, standardise IDs and stage names. #}
select
    "Log ID"                                                    as log_id,
    {{ opp_id('"Opportunity ID"') }}                            as opportunity_id,
    {{ alias('stage', '"Old Value"') }}                         as from_stage,
    {{ alias('stage', '"New Value"') }}                         as to_stage,
    {{ parse_ts('"Changed On"') }}                              as changed_at,
    lower(trim("Changed By"))                                   as changed_by
from read_csv('{{ var("raw_dir") }}/stage_history_log.csv', all_varchar = true)
where "Field" = 'Stage'
