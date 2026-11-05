-- Risk flags only make sense for open deals.
select opportunity_id from {{ ref('pipeline_deals') }}
where not is_open and (is_stuck or is_stale or is_past_due or is_at_risk)
