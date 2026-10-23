{# One row per time a deal sat in an open stage, enriched with the cumulative regression count at that point. #}
select
    s.opportunity_id,
    s.stint_seq,
    s.stage,
    s.stage_order,
    s.governed_probability,
    s.stuck_after_days,
    s.entered_at,
    s.exited_at,
    s.exit_type,
    s.days_in_stage,
    s.is_current_stint,
    coalesce(count(*) filter (where s.exit_type = 'Regressed') over (
        partition by s.opportunity_id order by s.stint_seq
        rows between unbounded preceding and 1 preceding), 0)       as regressions_so_far,
    d.department,
    d.service_line,
    d.sales_region,
    d.owner_email
from {{ ref('int_stage_stints') }} s
join {{ ref('pipeline_deals') }} d using (opportunity_id)
