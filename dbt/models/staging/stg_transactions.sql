select
    txn_id, account_id, customer_id, channel, amount, direction, posting_date, value_date
from {{ source('raw', 'transactions') }}
