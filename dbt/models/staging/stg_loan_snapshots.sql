select distinct on (loan_id, month_end)
    loan_id, account_id, month_end, outstanding, days_past_due, classification
from {{ source('raw', 'loan_monthly_snapshots') }}
order by loan_id, month_end
