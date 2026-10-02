{{ config(indexes=[{'columns': ['customer_id', 'valid_from']}]) }}
{# SCD Type 2: one row per customer per (segment, branch) validity interval; valid_to is exclusive. #}
select
    md5(h.customer_id::text || h.valid_from::text) as customer_sk,
    h.customer_id,
    {{ customer_hash('h.customer_id') }} as customer_key,
    h.segment,
    h.branch_id,
    b.branch_name,
    b.region,
    h.valid_from,
    h.valid_to,
    h.valid_to = date '9999-12-31' as is_current,
    c.acquisition_channel,
    c.acquisition_date,
    c.status,
    c.churn_date
from {{ ref('stg_customer_history') }} h
join {{ ref('stg_customers') }} c using (customer_id)
join {{ ref('dim_branch') }} b on b.branch_id = h.branch_id
