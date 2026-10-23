{# Rank the versions of each deal (latest = 1) and flag CRM test records. Nothing is dropped here. #}
select
    *,
    row_number() over (partition by opportunity_id order by last_modified desc, source_file desc) as version_rank,
    regexp_matches(lower(opportunity_name), '(^|[^a-z])test([^a-z]|$)')
        or lower(coalesce(owner_name, '')) = 'crm admin'
        or lower(coalesce(owner_email, '')) like 'crm.admin%'
        or account_id = 'ACC-00000'                                      as is_test_record
from {{ ref('stg_crm__opportunities') }}
