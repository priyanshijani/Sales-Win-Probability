{# One row per time a deal SAT IN an open stage. Equivalent of a grouped Multi-Row Formula: the next event
   (lead) closes the previous stint. #}
with sequenced as (
    select
        e.opportunity_id,
        e.event_seq,
        e.to_stage                                                      as stage,
        e.changed_at                                                    as entered_at,
        lead(e.changed_at) over w                                       as exited_at,
        lead(e.to_stage)   over w                                       as next_stage
    from {{ ref('int_stage_events') }} e
    window w as (partition by e.opportunity_id order by e.event_seq)
),

open_stints as (
    select s.*, r.stage_order, r.stuck_after_days, r.governed_probability, n.stage_order as next_stage_order
    from sequenced s
    join {{ ref('stage_rules') }} r on r.stage = s.stage and r.is_open = 1
    left join {{ ref('stage_rules') }} n on n.stage = s.next_stage
)

select
    opportunity_id,
    event_seq                                                           as stint_seq,
    stage,
    stage_order,
    stuck_after_days,
    governed_probability,
    entered_at,
    exited_at,
    next_stage,
    case
        when next_stage is null           then 'Open'
        when next_stage = 'Closed Won'    then 'Won'
        when next_stage = 'Closed Lost'   then 'Lost'
        when next_stage_order > stage_order then 'Advanced'
        when next_stage_order < stage_order then 'Regressed'
        else 'Same stage'
    end                                                                 as exit_type,
    date_diff('day', entered_at, coalesce(exited_at, timestamp '{{ var("snapshot_date") }} 23:59:59')) as days_in_stage,
    coalesce(exited_at, timestamp '{{ var("snapshot_date") }} 23:59:59') = timestamp '{{ var("snapshot_date") }} 23:59:59'
        and exited_at is null                                           as is_current_stint
from open_stints
