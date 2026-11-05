-- A deal can only be in one stage at a time.
select s.opportunity_id, s.stint_seq
from {{ ref('pipeline_stage_stints') }} s
join {{ ref('pipeline_stage_stints') }} n on n.opportunity_id = s.opportunity_id and n.stint_seq > s.stint_seq
where s.exited_at is null or n.entered_at < s.exited_at
