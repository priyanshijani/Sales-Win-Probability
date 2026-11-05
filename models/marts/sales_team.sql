{# One row per account executive, with quota prorated to the days they were active in the current fiscal year. #}
{% set snap = "date '" ~ var("snapshot_date") ~ "'" %}
with ae as (
    select * from {{ ref('int_sales_team') }} where role = 'Account Executive'
),

bookings as (
    select owner_email, sum(amount_eur) as bookings_ytd_eur
    from {{ ref('pipeline_deals') }}
    where is_won and year(actual_close_date) = year({{ snap }})
    group by 1
)

select
    ae.employee_id,
    ae.full_name,
    ae.email                                                            as owner_email,
    ae.department,
    ae.sales_manager,
    ae.territory,
    ae.hire_date,
    ae.leave_date,
    ae.is_active,
    ae.annual_quota_eur,
    greatest(0, date_diff('day',
        greatest(ae.hire_date, make_date(year({{ snap }}), 1, 1)),
        least(coalesce(ae.leave_date, {{ snap }}), {{ snap }})) + 1)    as active_days_ytd,
    ae.annual_quota_eur * greatest(0, date_diff('day',
        greatest(ae.hire_date, make_date(year({{ snap }}), 1, 1)),
        least(coalesce(ae.leave_date, {{ snap }}), {{ snap }})) + 1) / 365 as prorated_quota_ytd_eur,
    coalesce(b.bookings_ytd_eur, 0)                                     as bookings_ytd_eur
from ae
left join bookings b on b.owner_email = ae.email
