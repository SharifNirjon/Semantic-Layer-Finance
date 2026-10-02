select distinct on (response_id)
    response_id, campaign_id, customer_id, responded, converted_product, response_date
from {{ source('raw', 'campaign_responses') }}
order by response_id
