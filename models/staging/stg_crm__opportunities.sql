-- depends_on: {{ ref('crm_field_mapping_v1_v2') }}
{# One row per opportunity VERSION across all 24 monthly extracts (both CRM schemas), typed and parsed. #}
with raw as (
    select *
    from read_csv('{{ var("raw_dir") }}/opportunities/opps_*.csv',
                  union_by_name = true, all_varchar = true, filename = true)
),

mapped as (
    select
        {{ standardise_opportunity_columns('raw') }}
        filename as source_file,
        case when "Opportunity ID" is not null then 'v1' else 'v2' end as crm_version
    from raw
)

select
    {{ opp_id('opportunity_id') }}                              as opportunity_id,
    opportunity_name,
    account_id,
    account_name,
    lower(owner_email)                                          as owner_email,
    owner_name,
    {{ alias('department', 'department_raw') }}                 as department,
    service_line,
    {{ alias('stage', 'stage_raw') }}                           as stage,
    {{ parse_probability('probability_raw') }}                  as rep_probability,
    {{ parse_amount('amount_raw') }}                            as amount_local_stored,
    upper(case when trim(currency_raw) = '€' then 'EUR' else trim(currency_raw) end) as currency_stored,
    {{ currency_from_amount_text('amount_raw') }}               as currency_in_amount_text,
    {{ parse_date('created_date_raw') }}                        as created_date,
    {{ parse_date('expected_close_raw') }}                      as expected_close_date,
    {{ parse_date('actual_close_raw') }}                        as actual_close_date,
    {{ alias('loss_reason', 'loss_reason_raw') }}               as loss_reason,
    {{ alias('lead_source', 'lead_source_raw') }}               as lead_source,
    {{ parse_date('last_activity_raw') }}                       as last_activity_date,
    {{ parse_ts('last_modified_raw') }}                         as last_modified,
    forecast_category_rep,
    crm_version,
    regexp_extract(source_file, 'opps_[0-9]{4}_[0-9]{2}[.]csv')                     as source_file
from mapped
