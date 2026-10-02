select branch_id, branch_name, region, opened_date from {{ ref('stg_branches') }}
