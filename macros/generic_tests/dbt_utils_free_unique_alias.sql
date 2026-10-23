{# Each (domain, raw spelling) must map to exactly one standard value, otherwise the alias lookup is ambiguous. #}
{% test dbt_utils_free_unique_alias(model) %}
select domain, alias_key, count(distinct standard_value) as n_targets
from {{ model }}
group by 1, 2
having count(distinct standard_value) > 1
{% endtest %}
