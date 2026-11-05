select
    domain,
    lower(trim(raw_value)) as alias_key,
    standard_value
from {{ ref('value_aliases') }}
