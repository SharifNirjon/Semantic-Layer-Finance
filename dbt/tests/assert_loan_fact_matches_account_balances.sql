{# Loan-level outstanding must equal loan-account balances in the snapshot fact, per month. #}
with a as (select month_end, sum(loan_balance) as bal from {{ ref('fct_account_snapshot') }} group by 1),
l as (select month_end, sum(outstanding) as bal from {{ ref('fct_loans') }} group by 1)
select a.month_end, a.bal as account_bal, l.bal as loan_bal
from a join l using (month_end)
where abs(a.bal - l.bal) > 1
