-- Outliers must be excluded from EUR metrics.
select opportunity_id, amount_eur from {{ ref('pipeline_deals') }}
where amount_eur > {{ var('outlier_threshold_eur') }}
