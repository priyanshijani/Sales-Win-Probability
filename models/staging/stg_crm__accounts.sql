{# Excel report: 3 junk rows above the header (header on line 4) and footer rows, dropped by the ACC- filter. #}
with raw as (
    select *
    from read_xlsx('{{ var("raw_dir") }}/accounts_export.xlsx',
                   header = true, range = 'A4:J5000', all_varchar = true)
    where "Account ID" like 'ACC-%'
),

typed as (
    select
        "Account ID"                                            as account_id,
        trim("Account Name")                                    as account_name,
        {{ alias('industry', '"Industry"') }}                   as industry,
        {{ alias('country', '"Country"') }}                      as country_code,
        array_to_string(list_transform(string_split(lower(trim("City")), ' '), lambda x: upper(left(x, 1)) || substr(x, 2)), ' ') as city,
        {{ alias('company_size', '"Employees"') }}              as company_size_band,
        try_cast("Annual Revenue (EUR m)" as double)            as annual_revenue_eur_m,
        try_cast("Latitude" as double)                          as latitude_raw,
        try_cast("Longitude" as double)                         as longitude_raw,
        "Website"                                               as website
    from raw
)

select
    *,
    {# swapped lat/long: latitude outside Europe's 34-72 band while longitude sits inside it #}
    case when (latitude_raw not between 34 and 72) and (longitude_raw between 34 and 72)
         then longitude_raw else latitude_raw end               as latitude,
    case when (latitude_raw not between 34 and 72) and (longitude_raw between 34 and 72)
         then latitude_raw else longitude_raw end               as longitude
from typed
