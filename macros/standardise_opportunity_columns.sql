{#
  Replaces the Alteryx batch macro. Reads IT's field mapping (a seed) and builds one
  COALESCE per standard field across the v1 and v2 CRM column names.
  New schema version? Add rows to data/reference/crm_field_mapping_v1_v2.csv - no SQL changes.
#}
{% macro standardise_opportunity_columns(relation) %}
  {% if execute %}
    {% set mapping = run_query(
        "select standard_field, string_agg(source_field, '|' order by crm_version) as sources
         from " ~ ref('crm_field_mapping_v1_v2') ~ " group by 1 order by 1") %}
    {% for row in mapping.rows %}
      {%- set parts = [] -%}
      {%- for src in row[1].split('|') -%}
        {%- do parts.append("nullif(trim(\"" ~ src ~ "\"), '')") -%}
      {%- endfor %}
      coalesce({{ parts | join(', ') }}) as {{ row[0] }},
    {% endfor %}
  {% endif %}
{% endmacro %}
