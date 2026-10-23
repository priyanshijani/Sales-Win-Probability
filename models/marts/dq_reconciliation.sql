{# The Data Trust page. Every check has an expected and an actual value; any FAIL breaks `dbt build`
   (see tests/assert_reconciliation_passes.sql). Part 1 = the CRM's own control totals, part 2 = row bridges and integrity. #}
with latest_all as (
    select * from {{ ref('int_opportunity_versions') }} where version_rank = 1
),

latest_real as (
    select * from latest_all where not is_test_record
),

control as (
    select "Control Total" as control_total, "Dimension" as dimension, "Value" as value
    from {{ ref('crm_control_totals') }}
),

crm_checks as (
    select 'CRM control total' as check_group, control_total as check_name, dimension,
           cast(value as double) as expected,
           case
             when control_total like 'Unique opportunities%' then (select count(*) from latest_all)
             when control_total like 'Opportunities by stage%'
                  then (select count(*) from {{ ref('pipeline_deals') }} d where d.stage = c.dimension)
             when control_total like 'Sum of Amount as stored%'
                  then (select coalesce(sum(amount_local_stored), 0) from latest_real r
                        where coalesce(r.currency_stored, '(blank)') = c.dimension)
             when control_total like 'Opportunities with blank Amount%'
                  then (select count(*) from latest_real where amount_local_stored is null)
             when control_total like 'Account records%' then (select count(*) from {{ ref('stg_crm__accounts') }})
           end as actual
    from control c
),

bridge_checks as (
    select 'Row bridge', 'Raw rows = deals + older versions + test records', 'All',
           (select count(*) from {{ ref('stg_crm__opportunities') }}),
           (select count(*) from {{ ref('pipeline_deals') }}) + (select count(*) from {{ ref('rejected_records') }})
    union all
    select 'Row bridge', 'Account records = master accounts + merged duplicates', 'All',
           (select count(*) from {{ ref('stg_crm__accounts') }}),
           (select count(*) from {{ ref('dim_accounts') }}) + (select count(*) from {{ ref('int_accounts_master') }} where not is_master_record)
    union all
    select 'Row bridge', 'Stage stints = open-stage sittings in the audit log', 'All',
           (select count(*) from {{ ref('int_stage_stints') }}), (select count(*) from {{ ref('pipeline_stage_stints') }})
    union all
    select 'Integrity', 'Deals with no FX rate', 'All', 0, (select count(*) from {{ ref('pipeline_deals') }} where fx_rate is null)
    union all
    select 'Integrity', 'Deals whose owner could not be resolved', 'All', 0, (select count(*) from {{ ref('pipeline_deals') }} where owner_name is null)
    union all
    select 'Integrity', 'Deals with an unmapped stage / department', 'All', 0,
           (select count(*) from {{ ref('stg_crm__opportunities') }} where stage is null or department is null)
    union all
    select 'Integrity', 'Closed deals still without a close date', 'All', 0,
           (select count(*) from {{ ref('pipeline_deals') }} where not is_open and actual_close_date is null)
    union all
    select 'Integrity', 'Open deals without a current stage entry date', 'All', 0,
           (select count(*) from {{ ref('pipeline_deals') }} where is_open and stage_entered_date is null)
    union all
    select 'Integrity', 'Deals pointing to a deleted account (kept, flagged)', 'All', 10,
           (select count(*) from {{ ref('pipeline_deals') }} where dq_flags like '%ACCOUNT_MISSING%')
)

select
    row_number() over (order by check_group desc, check_name, dimension)          as check_id,
    check_group,
    check_name,
    dimension,
    expected,
    actual,
    actual - expected                                                             as difference,
    case when abs(actual - expected) < 0.5 then 'PASS' else 'FAIL' end           as status
from (
    select * from crm_checks
    union all
    select * from bridge_checks
)
