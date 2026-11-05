-- Fails the build (and lists the offending checks) if any reconciliation check is not PASS.
select * from {{ ref('dq_reconciliation') }} where status <> 'PASS'
