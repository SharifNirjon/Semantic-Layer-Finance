select distinct on (product_id)
    product_id, product_code, product_name, category, is_casa, interest_rate as annual_rate
from {{ source('raw', 'products') }}
order by product_id
