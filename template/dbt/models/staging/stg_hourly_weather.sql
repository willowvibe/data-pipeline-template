{{ config(materialized='view') }}

with source as (

    select * from {{ source('raw', 'hourly_weather') }}

),

typed as (

    select
        cast(city as varchar) as city,
        cast(observed_at as timestamp) as observed_at,
        cast(temperature_c as double precision) as temperature_c,
        cast(humidity_pct as double precision) as humidity_pct,
        cast(precipitation_mm as double precision) as precipitation_mm,
        cast(wind_kmh as double precision) as wind_kmh,
        cast(loaded_at as timestamp) as loaded_at
    from source

),

current_rows as (

    select *
    from typed
    where observed_at <= now()

),

deduped as (

    select
        *,
        row_number() over (
            partition by city, observed_at
            order by loaded_at desc
        ) as row_number
    from current_rows

)

select
    city,
    observed_at,
    temperature_c,
    humidity_pct,
    precipitation_mm,
    wind_kmh,
    loaded_at
from deduped
where row_number = 1
