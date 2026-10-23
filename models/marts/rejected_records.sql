{# Nothing is silently deleted: every raw CRM row that does not become an opportunity is listed with the reason. #}
select
    opportunity_id,
    source_file,
    crm_version,
    last_modified,
    opportunity_name,
    case when version_rank > 1 then 'DUPLICATE_OLDER_VERSION' else 'TEST_RECORD' end as reject_reason
from {{ ref('int_opportunity_versions') }}
where version_rank > 1 or is_test_record
