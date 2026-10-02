{{ config(indexes=[{'columns': ['month_end', 'branch_id']}, {'columns': ['account_id']}]) }}
select
    s.account_id,
    a.account_key,
    s.month_end,
    a.customer_id,
    a.product_id,
    a.product_name,
    a.category,
    a.is_casa,
    c.branch_id,
    c.branch_name,
    c.region,
    c.segment,
    s.closing_balance,
    s.avg_daily_balance,
    s.interest_accrued,
    case when a.category = 'Deposit' then s.closing_balance else 0 end as deposit_balance,
    case when a.category = 'Deposit' and a.is_casa then s.closing_balance else 0 end as casa_balance,
    case when a.category = 'Deposit' then s.avg_daily_balance else 0 end as avg_deposit_balance,
    case when a.category = 'Loan' then s.closing_balance else 0 end as loan_balance,
    case when a.category = 'Loan' then s.avg_daily_balance else 0 end as avg_loan_balance,
    case when a.category = 'Loan' then s.interest_accrued else 0 end as interest_income,
    case when a.category = 'Deposit' then s.interest_accrued else 0 end as interest_expense
from {{ ref('stg_account_snapshots') }} s
join {{ ref('dim_account') }} a using (account_id)
join {{ ref('dim_customer') }} c
  on c.customer_id = a.customer_id and s.month_end >= c.valid_from and s.month_end < c.valid_to
