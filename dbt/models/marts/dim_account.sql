select
    a.account_id,
    {{ customer_hash('a.account_id') }} as account_key,
    a.customer_id,
    a.product_id,
    p.product_name,
    p.category,
    p.is_casa,
    a.opening_branch_id as branch_id,
    b.branch_name,
    b.region,
    a.open_date,
    a.close_date,
    a.status
from {{ ref('stg_accounts') }} a
join {{ ref('dim_product') }} p using (product_id)
join {{ ref('dim_branch') }} b on b.branch_id = a.opening_branch_id
