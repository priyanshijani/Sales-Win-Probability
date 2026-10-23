select
    employee_id,
    full_name,
    name_key,
    email,
    role,
    department,
    sales_manager,
    territory,
    hire_date,
    leave_date,
    annual_quota_eur,
    leave_date is null or leave_date > date '{{ var("snapshot_date") }}'  as is_active
from {{ ref('stg_crm__sales_roster') }}
