{# Targets vs bookings (by close quarter) vs open pipeline expected to close (by expected close quarter). #}
with targets as (
    select "Department" as department, "Quarter" as quarter, "Bookings Target (EUR)" as bookings_target_eur
    from {{ ref('department_targets_quarterly') }}
),

bookings as (
    select department, close_quarter as quarter, sum(amount_eur) as bookings_eur, count(*) as deals_won
    from {{ ref('pipeline_deals') }} where is_won group by 1, 2
),

pipeline as (
    select
        department,
        expected_close_quarter as quarter,
        sum(amount_eur)                                                 as open_pipeline_eur,
        sum(weighted_amount_eur)                                        as weighted_pipeline_eur,
        sum(amount_eur) filter (where forecast_category = 'Commit')     as commit_eur,
        sum(amount_eur) filter (where forecast_category = 'Best Case')  as best_case_eur,
        sum(amount_eur) filter (where forecast_category = 'Pipeline')   as pipeline_eur
    from {{ ref('pipeline_deals') }} where is_open group by 1, 2
)

select
    t.department,
    t.quarter,
    t.bookings_target_eur,
    coalesce(b.bookings_eur, 0)                                         as bookings_eur,
    coalesce(b.deals_won, 0)                                            as deals_won,
    coalesce(b.bookings_eur, 0) / t.bookings_target_eur                 as target_attainment,
    coalesce(p.open_pipeline_eur, 0)                                    as open_pipeline_eur,
    coalesce(p.weighted_pipeline_eur, 0)                                as weighted_pipeline_eur,
    coalesce(p.commit_eur, 0)                                           as commit_eur,
    coalesce(p.best_case_eur, 0)                                        as best_case_eur,
    coalesce(p.pipeline_eur, 0)                                         as pipeline_eur,
    coalesce(p.open_pipeline_eur, 0) / t.bookings_target_eur            as pipeline_coverage_x
from targets t
left join bookings b using (department, quarter)
left join pipeline p using (department, quarter)
