{{ config(indexes=[{'columns': ['month_end', 'branch_id']}]) }}
{# Customer-month grain. Active = at least one transaction in the window (var active_window_days) up to month end. #}
with months as (select distinct month_end from {{ ref('stg_account_snapshots') }}),
cm as (
    select c.customer_id, c.acquisition_channel, c.acquisition_date, c.churn_date, m.month_end,
           date_trunc('month', m.month_end)::date as month_start
    from {{ ref('stg_customers') }} c
    join months m
      on c.acquisition_date <= m.month_end
     and (c.churn_date is null or c.churn_date >= date_trunc('month', m.month_end)::date)
),
active as (
    select distinct t.customer_id, m.month_end
    from {{ ref('stg_transactions') }} t
    join months m
      on t.posting_date > m.month_end - {{ var('active_window_days') }} and t.posting_date <= m.month_end
),
held as (
    select cm.customer_id, cm.month_end, count(distinct a.product_id) as n_products
    from cm
    join {{ ref('stg_accounts') }} a
      on a.customer_id = cm.customer_id and a.open_date <= cm.month_end
     and (a.close_date is null or a.close_date > cm.month_end)
    group by 1, 2
)
select
    cm.customer_id,
    d.customer_key,
    cm.month_end,
    d.branch_id,
    d.branch_name,
    d.region,
    d.segment,
    cm.acquisition_channel,
    (cm.acquisition_date < cm.month_start)::int as opening_customers,
    (cm.acquisition_date >= cm.month_start)::int as new_customers,
    (cm.churn_date between cm.month_start and cm.month_end)::int as churned_customers,
    (cm.churn_date is null or cm.churn_date > cm.month_end)::int as customers,
    ((cm.churn_date is null or cm.churn_date > cm.month_end) and a.customer_id is not null)::int as active_customers,
    case when cm.churn_date is null or cm.churn_date > cm.month_end then coalesce(h.n_products, 0) else 0 end
        as products_held,
    case when (cm.churn_date is null or cm.churn_date > cm.month_end) and coalesce(h.n_products, 0) >= 2
         then 1 else 0 end as multi_product_customers
from cm
join {{ ref('dim_customer') }} d
  on d.customer_id = cm.customer_id and cm.month_end >= d.valid_from and cm.month_end < d.valid_to
left join active a on a.customer_id = cm.customer_id and a.month_end = cm.month_end
left join held h on h.customer_id = cm.customer_id and h.month_end = cm.month_end
