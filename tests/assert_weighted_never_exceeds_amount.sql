select opportunity_id from {{ ref('pipeline_deals') }}
where weighted_amount_eur > amount_eur + 0.01
