select distinct on (loan_id)
    loan_id, account_id, customer_id, product_id, branch_id as origination_branch_id, principal, interest_rate,
    term_months, disbursed_date, sector
from {{ source('raw', 'loans') }}
order by loan_id
