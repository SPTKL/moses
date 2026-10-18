-- Port of products/pluto/pluto_build/sql/landuse.sql (two ordered updates).
-- The runner supplies exact Decimal zero predicates for PostgreSQL numeric.
with mapped as (
    select p.* replace (
        case when b.bldgclass is not null then b.landuse else p.landuse end as landuse
    )
    from {{ source('pluto_inputs', 'pluto') }} as p
    left join {{ source('pluto_inputs', 'pluto_input_landuse_bldgclass') }} as b
        on p.bldgclass = b.bldgclass
)
select * exclude (_moses_numbldgs_zero, _moses_bldgarea_zero) replace (
    case when (areasource is null or areasource = '0')
        and landuse = '11'
        and _moses_numbldgs_zero
        and (_moses_bldgarea_zero or bldgarea is null)
    then '4' else areasource end as areasource
)
from mapped
