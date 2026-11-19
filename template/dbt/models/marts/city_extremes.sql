{{ config(materialized='table') }}

with daily as (

    select * from {{ ref('daily_city_weather') }}

),

ranked as (

    select
        city,
        observation_date,
        max_temperature_c,
        min_temperature_c,
        total_precipitation_mm,
        row_number() over (
            partition by city
            order by max_temperature_c desc, observation_date
        ) as hottest_rank,
        row_number() over (
            partition by city
            order by min_temperature_c asc, observation_date
        ) as coldest_rank,
        row_number() over (
            partition by city
            order by total_precipitation_mm desc, observation_date
        ) as wettest_rank
    from daily

),

hottest as (

    select
        city,
        observation_date as hottest_date,
        max_temperature_c as hottest_temperature_c
    from ranked
    where hottest_rank = 1

),

coldest as (

    select
        city,
        observation_date as coldest_date,
        min_temperature_c as coldest_temperature_c
    from ranked
    where coldest_rank = 1

),

wettest as (

    select
        city,
        observation_date as wettest_date,
        total_precipitation_mm as wettest_precipitation_mm
    from ranked
    where wettest_rank = 1

)

select
    hottest.city,
    hottest.hottest_date,
    hottest.hottest_temperature_c,
    coldest.coldest_date,
    coldest.coldest_temperature_c,
    wettest.wettest_date,
    wettest.wettest_precipitation_mm
from hottest
join coldest on hottest.city = coldest.city
join wettest on hottest.city = wettest.city
