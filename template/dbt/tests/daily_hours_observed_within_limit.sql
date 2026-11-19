with violations as (

    select
        city,
        observation_date,
        hours_observed
    from {{ ref('daily_city_weather') }}
    where hours_observed > 24

)

select * from violations
