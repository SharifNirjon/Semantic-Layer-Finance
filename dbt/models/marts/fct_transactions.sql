{{ config(indexes=[{'columns': ['posting_date', 'branch_id']}, {'columns': ['month_end']}]) }}
{# Business date = posting_date. value_date is retained for reference only. #}
select
    t.txn_id,
    t.posting_date,
    t.value_date,
    (date_trunc('month', t.posting_date) + interval '1 month - 1 day')::date as month_end,
    t.account_id,
    t.customer_id,
    c.customer_key,
    case when t.channel = 'ATM' then 'ATM' else initcap(t.channel) end as channel,
    t.amount,
    t.direction,
    case when t.channel in ('mobile', 'internet') then 1 else 0 end as is_digital,
    a.product_name,
    c.branch_id,
    c.branch_name,
    c.region,
    c.segment
from {{ ref('stg_transactions') }} t
join {{ ref('dim_account') }} a using (account_id)
join {{ ref('dim_customer') }} c
  on c.customer_id = t.customer_id and t.posting_date >= c.valid_from and t.posting_date < c.valid_to
