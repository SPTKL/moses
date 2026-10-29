{{ config(materialized='table') }}
-- Business process: property_attributes
WITH
parcel_environmental_designations AS NOT MATERIALIZED (
  -- pluto_build/sql/edesignation.sql statement 1
  /* set the E Designation number */
  /* if there is more than one enumber for one lot take the enumber from the lowest ceqr_num and ulurp_num */
  /* **change to using csv file** */
  WITH preferred_environmental_designations AS (
    SELECT
      bbl,
      enumber
    FROM (
      SELECT
        bbl,
        enumber,
        ROW_NUMBER() OVER (PARTITION BY bbl ORDER BY ceqr_num, ulurp_num, enumber) AS row_number
      FROM ({{ pluto_input('stg__dcp_edesignation') }}) AS stg__dcp_edesignation
    ) AS x
    WHERE
      x.row_number = 1
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.enumber)
        ELSE "a"."edesignum"
      END AS "edesignum"
    )
  FROM {{ ref('parcel_cama') }} AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM preferred_environmental_designations AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY MOSES_TEXT(b.bbl)) = 1
  ) AS "b"
    ON (
      a.bbl = MOSES_TEXT(b.bbl)
    )
),
parcel_owner_types AS NOT MATERIALIZED (
  -- pluto_build/sql/ownertype.sql statement 1
  -- set the owner type code based on data from COLP
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ownership)
        ELSE "a"."ownertype"
      END AS "ownertype"
    )
  FROM parcel_environmental_designations AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ({{ pluto_input('stg__dcp_colp') }}) AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY CAST(b.bbl AS DECIMAL(38, 12))) = 1
  ) AS "b"
    ON (
      CAST(a.bbl AS DECIMAL(38, 12)) = CAST(b.bbl AS DECIMAL(38, 12))
    )
),
default_owner_types AS NOT MATERIALIZED (
  -- pluto_build/sql/ownertype.sql statement 2
  -- set X as owner type
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN a.exempttot = a.assesstot AND a.ownertype IS NULL
        THEN MOSES_TEXT('X')
        ELSE "a"."ownertype"
      END AS "ownertype"
    )
  FROM parcel_owner_types AS "a"
),
parcel_addresses AS NOT MATERIALIZED (
  -- pluto_build/sql/address.sql statement 1
  -- when the address is still null populate the address
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(CONCAT(b.housenum_hi, ' ', b.street_name))
        ELSE "a"."address"
      END AS "address"
    )
  FROM default_owner_types AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('tax_lot_attributes') }} AS b
    WHERE
      (
        b.housenum_hi IS NOT NULL
      ) AND (
        b.street_name IS NOT NULL
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.primebbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    ) AND (
      (
        a.address IS NULL
      ) = "b".__matched
    )
),
normalized_addresses AS NOT MATERIALIZED (
  -- pluto_build/sql/address.sql statement 2
  -- remove extra spaces from the address
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN a.address IS NOT NULL AND REGEXP_MATCHES(REPLACE(a.address, '-', ''), '[0-9]')
        THEN MOSES_TEXT(TRIM(REGEXP_REPLACE(a.address, '\s+', ' ', 'g')))
        ELSE "a"."address"
      END AS "address"
    )
  FROM parcel_addresses AS "a"
)
SELECT * FROM normalized_addresses
