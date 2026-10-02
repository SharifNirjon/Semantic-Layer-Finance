select distinct on (customer_id)
    customer_id,
    segment as current_segment,
    acquisition_channel,
    acquisition_date,
    home_branch_id as current_branch_id,
    status,
    churn_date
from {{ source('raw', 'customers') }}
order by customer_id
