select distinct on (account_id, month_end)
    account_id, month_end, closing_balance, avg_daily_balance, interest_accrued
from {{ source('raw', 'account_monthly_snapshots') }}
order by account_id, month_end
