{# Main fact table: one row per opportunity. All row-level business logic lives here (docs/business_definitions.md);
   Power BI only aggregates. #}
{% set snap = "date '" ~ var("snapshot_date") ~ "'" %}

with deals as (
    select * from {{ ref('int_opportunities_clean') }}
),

rules as (
    select * from {{ ref('stage_rules') }}
),

stint_summary as (
    select
        opportunity_id,
        max(case when is_current_stint then cast(entered_at as date) end)           as stage_entered_date,
        count(*) filter (where exit_type = 'Regressed')                             as regression_count,
        max(stage_order)                                                            as max_open_stage_order,
        max(stage) filter (where exit_type = 'Lost')                                  as lost_at_stage
    from {{ ref('int_stage_stints') }}
    group by 1
),

close_event as (
    select opportunity_id, cast(max(changed_at) as date) as close_event_date
    from {{ ref('int_stage_events') }}
    where to_stage in ('Closed Won', 'Closed Lost')
    group by 1
),

accounts as (
    select * from {{ ref('int_accounts_master') }} where is_master_record
),

team as (
    select * from {{ ref('int_sales_team') }} where role = 'Account Executive'
),

base as (
    select
        d.*,
        coalesce(d.actual_close_date, case when r.is_open = 0 then c.close_event_date end) as actual_close_date_filled,
        d.actual_close_date is null and r.is_open = 0                               as close_date_from_log,
        r.stage_order,
        r.confidence_band,
        r.governed_probability,
        r.forecast_category,
        r.stuck_after_days,
        r.is_open = 1                                                               as is_open,
        d.stage = 'Closed Won'                                                      as is_won,
        d.stage = 'Closed Lost'                                                     as is_lost
    from deals d
    join rules r on r.stage = d.stage
    left join close_event c on c.opportunity_id = d.opportunity_id
),

fx as (
    select
        b.*,
        case when b.is_open then strftime({{ snap }}, '%Y-%m')
             else strftime(b.actual_close_date_filled, '%Y-%m') end                 as fx_month
    from base b
),

priced as (
    select
        f.*,
        x."EUR per 1 unit"                                                          as fx_rate,
        abs(f.amount_local_stored)                                                  as amount_local,
        abs(f.amount_local_stored) * x."EUR per 1 unit"                             as amount_eur_all
    from fx f
    left join {{ ref('fx_rates_monthly') }} x on x."Month" = f.fx_month and x."Currency" = f.currency
),

first_win as (
    select master_account_id, min(actual_close_date_filled) as first_won_date
    from priced where is_won group by 1
),

account_status as (
    select
        master_account_id,
        max(actual_close_date_filled) filter (where is_won)                         as last_won_date
    from priced group by 1
)

, scored as (
select
    -- keys
    p.opportunity_id,
    p.opportunity_name,
    p.master_account_id,
    -- account
    coalesce(a.account_name, 'Unknown (deleted in CRM)')                            as account_name,
    a.industry,
    a.company_size_band,
    a.country_code,
    a.country_name,
    a.sales_region,
    a.city,
    a.latitude,
    a.longitude,
    case
        when a.account_id is null then 'Unknown'
        when s.last_won_date > {{ snap }} - interval 12 month then 'Active Customer'
        when s.last_won_date is not null then 'Lapsed Customer'
        else 'Prospect'
    end                                                                             as account_status,
    -- people
    p.owner_email,
    t.full_name                                                                     as owner_name,
    t.sales_manager,
    p.department,
    t.is_active                                                                     as owner_is_active,
    -- deal
    p.service_line,
    p.lead_source,
    case when fw.first_won_date < p.created_date then 'Expansion' else 'New Logo' end as deal_type,
    p.loss_reason,
    case when p.is_lost then ss.lost_at_stage end                                   as lost_at_stage,
    -- stage
    p.stage,
    p.stage_order,
    p.confidence_band,
    p.forecast_category,
    p.is_open,
    p.is_won,
    p.is_lost,
    case when p.is_won then 5 else coalesce(ss.max_open_stage_order, p.stage_order) end as max_stage_reached,
    -- money
    p.amount_local,
    p.currency,
    p.fx_rate,
    case when p.amount_eur_all is not null and p.amount_eur_all <= {{ var("outlier_threshold_eur") }}
         then p.amount_eur_all end                                                  as amount_eur,
    p.governed_probability,
    case when p.is_open and p.amount_eur_all <= {{ var("outlier_threshold_eur") }}
         then p.amount_eur_all * p.governed_probability end                         as weighted_amount_eur,
    p.rep_probability,
    p.rep_probability - p.governed_probability * 100                                as probability_gap_pts,
    case
        when p.amount_eur_all is null or p.amount_eur_all > {{ var("outlier_threshold_eur") }} then null
        when p.amount_eur_all <   50000 then '1. < 50k'
        when p.amount_eur_all <  150000 then '2. 50-150k'
        when p.amount_eur_all <  500000 then '3. 150-500k'
        when p.amount_eur_all < 1000000 then '4. 500k-1M'
        else '5. > 1M'
    end                                                                             as deal_size_band,
    -- dates
    p.created_date,
    p.expected_close_date,
    p.actual_close_date_filled                                                      as actual_close_date,
    p.last_activity_date,
    ss.stage_entered_date,
    year(p.actual_close_date_filled) || '-Q' || quarter(p.actual_close_date_filled) as close_quarter,
    year(p.expected_close_date) || '-Q' || quarter(p.expected_close_date)           as expected_close_quarter,
    -- velocity & risk
    case when p.is_open then date_diff('day', ss.stage_entered_date, {{ snap }}) end as days_in_current_stage,
    p.stuck_after_days,
    p.is_open and date_diff('day', ss.stage_entered_date, {{ snap }}) > p.stuck_after_days as is_stuck,
    date_diff('day', p.last_activity_date, {{ snap }})                              as days_since_activity,
    p.is_open and date_diff('day', p.last_activity_date, {{ snap }}) > {{ var("stale_after_days") }} as is_stale,
    p.is_open and p.expected_close_date < {{ snap }}                                as is_past_due,
    coalesce(ss.regression_count, 0)                                                as regression_count,
    case when not p.is_open then date_diff('day', p.created_date, p.actual_close_date_filled) end as sales_cycle_days,
    -- raw flag inputs
    p.amount_local_stored is null                                                   as f_amount_missing,
    p.amount_local_stored < 0                                                       as f_amount_negative,
    p.amount_eur_all > {{ var("outlier_threshold_eur") }}                           as f_amount_outlier,
    p.account_missing                                                               as f_account_missing,
    p.currency_source <> 'stored'                                                   as f_currency_filled,
    p.close_date_from_log                                                           as f_close_date_from_log,
    p.crm_version
from priced p
left join accounts a on a.master_account_id = p.master_account_id
left join team t on t.email = p.owner_email
left join stint_summary ss on ss.opportunity_id = p.opportunity_id
left join first_win fw on fw.master_account_id = p.master_account_id
left join account_status s on s.master_account_id = p.master_account_id
)

select
    * exclude (f_amount_missing, f_amount_negative, f_amount_outlier, f_account_missing, f_currency_filled, f_close_date_from_log),
    is_open and (is_stuck or is_stale or is_past_due or not owner_is_active)        as is_at_risk,
    case when is_open then array_to_string(list_filter([
        case when is_stuck then 'STUCK' end,
        case when is_stale then 'STALE' end,
        case when is_past_due then 'PAST_DUE' end,
        case when not owner_is_active then 'OWNER_LEFT' end], x -> x is not null), ';') end as risk_reasons,
    array_to_string(list_filter([
        case when f_amount_missing then 'AMOUNT_MISSING' end,
        case when f_amount_negative then 'AMOUNT_NEGATIVE' end,
        case when f_amount_outlier then 'AMOUNT_OUTLIER' end,
        case when f_account_missing then 'ACCOUNT_MISSING' end,
        case when f_currency_filled then 'CURRENCY_FILLED' end,
        case when f_close_date_from_log then 'CLOSE_DATE_FROM_LOG' end,
        case when is_open and not owner_is_active then 'OWNER_LEFT' end], x -> x is not null), ';') as dq_flags,
    date '{{ var("snapshot_date") }}'                                               as snapshot_date
from scored
