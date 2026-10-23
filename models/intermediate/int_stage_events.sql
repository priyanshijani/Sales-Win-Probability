{# Stage-change events for real deals only. The log holds the same change twice when one copy was written with
   minute precision and the other with seconds - duplicates that only look identical AFTER parsing the three
   timestamp formats. Keep one event per (deal, from, to, minute), the more precise copy. #}
with parsed as (
    select
        e.opportunity_id,
        max(e.changed_at)                                               as changed_at,
        e.from_stage,
        e.to_stage
    from {{ ref('stg_crm__stage_history') }} e
    where e.to_stage is not null
      and e.opportunity_id in (select opportunity_id from {{ ref('int_opportunities_clean') }})
    group by e.opportunity_id, e.from_stage, e.to_stage, date_trunc('minute', e.changed_at)
)

select
    *,
    row_number() over (partition by opportunity_id order by changed_at, to_stage) as event_seq
from parsed
