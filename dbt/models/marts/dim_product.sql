select product_id, product_code, product_name, category, is_casa, category = 'Deposit' as is_deposit,
       annual_rate
from {{ ref('stg_products') }}
