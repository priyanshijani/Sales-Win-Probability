{# 765 CRM account records -> one master account per company (lowest account_id wins). #}
with keyed as (
    select
        *,
        trim(regexp_replace(
            regexp_replace(
                regexp_replace(replace(replace({{ name_key('account_name') }}, '.', ''), '/', ''), '[^a-z0-9 ]', '', 'g'),
                '\s+(sp z oo|zoo|oo|gmbh|ag|ltd|plc|sa|se|sas|srl|bv|nv|ab|sl|spa|as|aps|oyj|oy|lda|asa|dac|sro|rl)$', ''),
            '\s+', ' ', 'g'))                                           as company_key
    from {{ ref('stg_crm__accounts') }}
),

masters as (
    select company_key, min(account_id) as master_account_id
    from keyed group by 1
),

city_coords as (
    select city, avg(latitude) as city_lat, avg(longitude) as city_lon
    from keyed where latitude is not null group by 1
)

select
    k.account_id,
    m.master_account_id,
    k.account_id = m.master_account_id                                  as is_master_record,
    k.company_key,
    k.account_name,
    k.industry,
    k.country_code,
    r.country_name,
    r.sales_region,
    r.currency                                                          as country_currency,
    k.city,
    k.company_size_band,
    k.annual_revenue_eur_m,
    coalesce(k.latitude,  c.city_lat)                                   as latitude,
    coalesce(k.longitude, c.city_lon)                                   as longitude,
    k.latitude is null                                                  as coordinates_filled_from_city
from keyed k
join masters m using (company_key)
left join {{ ref('country_region_mapping') }} r on r.country_code = k.country_code
left join city_coords c on c.city = k.city
