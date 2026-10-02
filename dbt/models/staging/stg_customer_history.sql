select distinct on (customer_id, valid_from)
    customer_id, segment, home_branch_id as branch_id, valid_from,
    coalesce(valid_to, date '9999-12-31') as valid_to
from {{ source('raw', 'customer_attribute_history') }}
order by customer_id, valid_from
