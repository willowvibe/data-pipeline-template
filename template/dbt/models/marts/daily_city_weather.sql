{{ config(materialized='table') }}

select
    city,
    cast(observed_at as date) as observation_date,
    min(temperature_c) as min_temperature_c,
    max(temperature_c) as max_temperature_c,
    avg(temperature_c) as avg_temperature_c,
    sum(precipitation_mm) as total_precipitation_mm,
    max(wind_kmh) as max_wind_kmh,
    count(*) as hours_observed
from {{ ref('stg_hourly_weather') }}
group by city, cast(observed_at as date)
