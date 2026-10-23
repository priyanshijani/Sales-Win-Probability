{# Three date formats are mixed in the CRM; European day-first is assumed for slash dates. #}
{% macro parse_date(col) %}
  cast(try_strptime(left(trim({{ col }}), 10), ['%Y-%m-%d', '%d/%m/%Y', '%d.%m.%Y']) as date)
{% endmacro %}

{% macro parse_ts(col) %}
  try_strptime(trim({{ col }}), [
    '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%d/%m/%Y %H:%M', '%d.%m.%Y %H:%M',
    '%Y-%m-%d', '%d/%m/%Y', '%d.%m.%Y'])
{% endmacro %}

{# "€125,000", "125 000", "PLN 331,000", "125,000.00" -> 125000 #}
{% macro parse_amount(col) %}
  try_cast(regexp_replace(regexp_replace({{ col }}, '[^0-9.,-]', '', 'g'), ',', '', 'g') as double)
{% endmacro %}

{# Currency can hide inside the amount text when the currency column is blank #}
{% macro currency_from_amount_text(col) %}
  case
    when {{ col }} like '%€%' then 'EUR'
    when {{ col }} like '%£%' then 'GBP'
    else nullif(regexp_extract({{ col }}, '^([A-Za-z]{3})', 1), '')
  end
{% endmacro %}

{# Rep-typed probability: "75", "75%", "0.75", "1.0" -> 0-100 #}
{% macro parse_probability(col) %}
  case
    when {{ col }} is null then null
    when {{ col }} like '%.%' and try_cast(replace({{ col }}, '%', '') as double) <= 1
      then try_cast(replace({{ col }}, '%', '') as double) * 100
    else try_cast(replace({{ col }}, '%', '') as double)
  end
{% endmacro %}

{% macro opp_id(col) %}
  'OPP-' || lpad(regexp_replace(trim({{ col }}), '[^0-9]', '', 'g'), 6, '0')
{% endmacro %}

{# lower-case, accent-free, single-spaced key for matching names #}
{% macro name_key(col) %}
  regexp_replace(strip_accents(lower(trim({{ col }}))), '\s+', ' ', 'g')
{% endmacro %}

{# Governed alias lookup (data/reference/value_aliases.csv). Unmapped values come back NULL and fail tests. #}
{% macro alias(domain, col) %}
  (select max(a.standard_value) from {{ ref('stg_value_aliases') }} a
   where a.domain = '{{ domain }}' and a.alias_key = lower(trim({{ col }})))
{% endmacro %}
