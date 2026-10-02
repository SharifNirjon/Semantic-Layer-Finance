select distinct on (account_id)
    account_id, customer_id, product_id, branch_id as opening_branch_id, open_date, close_date, status
from {{ source('raw', 'accounts') }}
order by account_id
