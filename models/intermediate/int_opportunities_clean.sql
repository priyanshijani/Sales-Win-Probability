{# Latest version of every real deal, with owner resolved to a roster email and currency filled. #}
with latest as (
    select * from {{ ref('int_opportunity_versions') }}
    where version_rank = 1 and not is_test_record
),

ae as (
    select * from {{ ref('int_sales_team') }} where role = 'Account Executive'
),

-- v1 records carry the owner as typed text. Match in passes; the first pass that hits wins.
v1_names as (
    select distinct
        owner_name,
        {{ name_key('owner_name') }}                                    as typed_key,
        -- "Hughes, Oliver" -> "oliver hughes"
        case when owner_name like '%,%'
             then {{ name_key("trim(split_part(owner_name, ',', 2)) || ' ' || trim(split_part(owner_name, ',', 1))") }}
        end                                                             as reordered_key,
        -- "S. Andersson" -> initial 's' + surname
        case when regexp_matches(owner_name, '^[A-Za-z]\.\s*\S+')
             then lower(left(trim(owner_name), 1)) || '|' || {{ name_key("regexp_replace(trim(owner_name), '^[A-Za-z]\.\s*', '')") }}
        end                                                             as initial_surname_key,
        lower(trim(owner_name))                                         as alias_key
    from latest
    where owner_email is null and owner_name is not null
),

roster_keys as (
    select
        email,
        full_name,
        name_key,
        lower(left(full_name, 1)) || '|' || {{ name_key("split_part(full_name, ' ', -1)") }} as initial_surname_key
    from ae
),

owner_aliases as (
    select alias_key, standard_value as email
    from {{ ref('stg_value_aliases') }}
    where domain = 'owner'
),

resolved as (
    select
        v.owner_name,
        coalesce(p1.email, p2.email, p3.email, p4.email)                as owner_email_resolved,
        case when p1.email is not null then 'v1_exact_name'
             when p2.email is not null then 'v1_last_first'
             when p3.email is not null then 'v1_initial_surname'
             when p4.email is not null then 'v1_alias'
        end                                                             as owner_match_method
    from v1_names v
    left join roster_keys p1 on p1.name_key = v.typed_key
    left join roster_keys p2 on p2.name_key = v.reordered_key
    left join roster_keys p3 on p3.initial_surname_key = v.initial_surname_key
    left join owner_aliases oa on oa.alias_key = v.alias_key
    left join roster_keys p4 on p4.email = oa.email
),

accounts as (
    select * from {{ ref('int_accounts_master') }}
)

select
    l.opportunity_id,
    l.opportunity_name,
    l.account_id,
    a.master_account_id,
    coalesce(l.owner_email, r.owner_email_resolved)                     as owner_email,
    case when l.owner_email is not null then 'v2_email' else r.owner_match_method end as owner_match_method,
    l.department,
    l.service_line,
    l.stage,
    l.rep_probability,
    l.forecast_category_rep,
    l.amount_local_stored,
    l.currency_stored,
    -- currency: stored value, else symbol/prefix inside the amount text, else the account country's currency
    coalesce(l.currency_stored, l.currency_in_amount_text, a.country_currency) as currency,
    case when l.currency_stored is not null then 'stored'
         when l.currency_in_amount_text is not null then 'amount_text'
         when a.country_currency is not null then 'account_country' end as currency_source,
    l.created_date,
    l.expected_close_date,
    l.actual_close_date,
    l.loss_reason,
    l.lead_source,
    l.last_activity_date,
    l.crm_version,
    l.source_file,
    a.account_id is null                                                as account_missing
from latest l
left join resolved r on r.owner_name = l.owner_name and l.owner_email is null
left join accounts a on a.account_id = l.account_id
