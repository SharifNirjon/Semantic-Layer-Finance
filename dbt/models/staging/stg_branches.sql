select distinct on (branch_id)
    branch_id, trim(branch_name) as branch_name, trim(region) as region, opened_date
from {{ source('raw', 'branches') }}
order by branch_id
