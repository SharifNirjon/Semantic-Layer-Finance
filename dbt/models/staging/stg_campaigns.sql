select distinct on (campaign_id)
    campaign_id, campaign_name, channel as campaign_channel, cost, target_segment, start_date, end_date
from {{ source('raw', 'campaigns') }}
order by campaign_id
