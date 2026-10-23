{# One row per master account (the 45 duplicate CRM records are folded into their master). #}
select
    a.master_account_id,
    a.account_name,
    a.industry,
    a.company_size_band,
    a.country_code,
    a.country_name,
    a.sales_region,
    a.city,
    a.latitude,
    a.longitude,
    a.annual_revenue_eur_m,
    a.coordinates_filled_from_city,
    (select count(*) from {{ ref('int_accounts_master') }} x where x.master_account_id = a.master_account_id) as crm_records_merged,
    count(d.opportunity_id)                                             as deal_count,
    coalesce(sum(d.amount_eur) filter (where d.is_won), 0)              as won_eur,
    coalesce(sum(d.amount_eur) filter (where d.is_open), 0)             as open_pipeline_eur,
    max(d.account_status)                                               as account_status
from {{ ref('int_accounts_master') }} a
left join {{ ref('pipeline_deals') }} d on d.master_account_id = a.master_account_id
where a.is_master_record
group by all
