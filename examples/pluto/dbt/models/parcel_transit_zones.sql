{{ config(materialized='table', alias='transit') }}
-- Business process: parcel_transit_zones
WITH
contiguous_tax_blocks AS NOT MATERIALIZED (
  -- models/int_tz__tax_blocks.sql
  /* Create sub-blocks from tax blocks, handling non-contiguous blocks */
  /* Splits blocks into contiguous parts and assigns lots to their sub-block */
  WITH unified_tax_blocks AS (
    SELECT
      borough,
      block,
      MOSES_UNION_AGG(p.geom) AS geom,
      ARRAY_AGG(bbl) AS all_bbls
    FROM {{ ref('parcel_zoning_districts') }} AS p
    GROUP BY
      p.borough,
      p.block
  ), contiguous_block_parts AS (
    SELECT
      borough,
      block,
      all_bbls,
      (
        UNNEST(ST_DUMP(geom))
      ).geom AS geom
    FROM unified_tax_blocks
  ), numbered_sub_blocks AS (
    SELECT
      borough,
      block,
      all_bbls,
      geom,
      ROW_NUMBER() OVER (PARTITION BY borough, block ORDER BY ST_AREA(geom) DESC NULLS FIRST) AS sub_block
    FROM contiguous_block_parts
  ), lots_assigned_to_sub_blocks AS (
    SELECT
      np.borough,
      np.block,
      np.sub_block,
      np.geom,
      ARRAY_AGG(p.bbl) AS bbls
    FROM numbered_sub_blocks AS np
    INNER JOIN {{ ref('parcel_zoning_districts') }} AS p
      ON np.borough = p.borough
      AND np.block = p.block
      AND ST_WITHIN(ST_POINTONSURFACE(p.geom), np.geom)
    GROUP BY
      np.borough,
      np.block,
      np.sub_block,
      np.geom
  )
  SELECT
    borough,
    block,
    sub_block,
    borough || '-' || block || '-' || sub_block AS block_id,
    geom,
    bbls
  FROM lots_assigned_to_sub_blocks
),
transit_zone_polygon_parts AS MATERIALIZED (
  -- models/int_tz__atomic_geoms.sql
  /* Decompose transit zone multipolygons into atomic parts for performance */
  /* Breaking apart multipolygons reduces spatial calculation time from >10 min to ~1 min */
  WITH individual_zone_polygons AS (
    SELECT
      transit_zone,
      (
        UNNEST(ST_DUMP(geom))
      ).geom AS wkb_geometry
    FROM ({{ pluto_input('stg__dcp_transit_zones') }}) AS stg__dcp_transit_zones
  )
  SELECT
    transit_zone,
    wkb_geometry,
    ROW_NUMBER() OVER (ORDER BY transit_zone) AS decomposed_id
  FROM individual_zone_polygons
),
ranked_block_zone_coverage AS MATERIALIZED (
  -- models/int_tz__block_to_tz_ranked.sql
  /* Calculate transit zone coverage per block with ranking */
  WITH block_zone_overlap_percentages AS (
    SELECT
      tb.borough,
      tb.block,
      tb.sub_block,
      tb.geom,
      tb.bbls,
      t.transit_zone,
      ST_AREA(ST_INTERSECTION(tb.geom, MOSES_UNION_AGG(t.wkb_geometry))) / ST_AREA(tb.geom) * 100.0 AS pct_covered
    FROM contiguous_tax_blocks AS tb
    INNER JOIN transit_zone_polygon_parts AS t
      ON ST_INTERSECTS(tb.geom, t.wkb_geometry)
    GROUP BY
      tb.borough,
      tb.block,
      tb.sub_block,
      tb.geom,
      tb.bbls,
      t.transit_zone
  )
  SELECT
    'block' AS assignment_type,
    borough || '-' || block || '-' || sub_block AS id,
    borough,
    block,
    geom,
    sub_block,
    bbls,
    transit_zone,
    pct_covered,
    ROW_NUMBER() OVER (PARTITION BY borough, block, sub_block ORDER BY pct_covered DESC NULLS FIRST) AS tz_rank
  FROM block_zone_overlap_percentages
),
ranked_lot_zone_coverage AS NOT MATERIALIZED (
  -- models/int_tz__bbl_to_tz_ranked.sql
  /* Lot-level assignments for ambiguous blocks */
  /* Only for blocks where multiple transit zones have >10% coverage */
  WITH lots_in_ambiguous_blocks AS (
    SELECT
      UNNEST(bbls) AS bbl,
      borough,
      block,
      sub_block
    FROM ranked_block_zone_coverage AS tza
    WHERE
      tza.tz_rank > 1 AND tza.pct_covered > 10
  ), lot_zone_overlap_percentages AS (
    SELECT
      p.bbl,
      p.borough,
      p.block,
      t.transit_zone,
      p.geom,
      ST_AREA(ST_INTERSECTION(p.geom, MOSES_UNION_AGG(t.wkb_geometry))) / ST_AREA(p.geom) * 100.0 AS pct_covered
    FROM {{ ref('parcel_zoning_districts') }} AS p
    INNER JOIN lots_in_ambiguous_blocks AS ab
      ON p.bbl = ab.bbl
    INNER JOIN transit_zone_polygon_parts AS t
      ON ST_INTERSECTS(p.geom, t.wkb_geometry)
    GROUP BY
      p.bbl,
      p.borough,
      p.block,
      t.transit_zone,
      p.geom
  ), lot_zones_with_priority AS (
    SELECT
      lt.*,
      tzr.tz_rank AS priority_rank
    FROM lot_zone_overlap_percentages AS lt
    LEFT JOIN ({{ pluto_input('dcp_transit_zone_ranks') }}) AS tzr
      ON lt.transit_zone = tzr.tz_name
  ), eligible_lot_zones AS (
    SELECT
      ltr.*,
      NOT COALESCE(
        EXISTS(
          SELECT
            1
          FROM lot_zones_with_priority AS inner_ltr
          WHERE
            inner_ltr.bbl = ltr.bbl AND inner_ltr.priority_rank < 4
        )
        AND ltr.priority_rank = 4,
        FALSE
      ) AS include_zone
    FROM lot_zones_with_priority AS ltr
  )
  SELECT
    'lot' AS assignment_type,
    MOSES_TEXT(bbl) AS id,
    borough,
    block,
    geom,
    1 AS sub_block,
    [bbl] AS bbls,
    transit_zone,
    pct_covered,
    ROW_NUMBER() OVER (PARTITION BY bbl ORDER BY pct_covered DESC NULLS FIRST) AS tz_rank
  FROM eligible_lot_zones
  WHERE
    include_zone = TRUE
),
transit_zone_footprint AS NOT MATERIALIZED (
  -- models/int_tz__union_coverage.sql
  /* Union of all transit zones to identify land coverage */
  /* Lots outside this union are in water and should have NULL transit zones */
  SELECT
    MOSES_UNION_AGG(geom) AS geom
  FROM ({{ pluto_input('stg__dcp_transit_zones') }}) AS stg__dcp_transit_zones
),
transit_zone_by_lot AS NOT MATERIALIZED (
  -- models/int_pluto__transitzone.sql
  /* Final transit zone assignment per BBL */
  /* Uses block-level for unambiguous blocks, lot-level for ambiguous ones */
  /* Nulls out transit zones for lots in water (outside all transit zone coverage) */
  WITH preferred_zone_assignments AS (
    /* Block-level assignments for non-ambiguous blocks */
    SELECT
      UNNEST(bbls) AS bbl,
      transit_zone
    FROM ranked_block_zone_coverage AS block_tz
    WHERE
      block_tz.tz_rank = 1
      AND /* Only assign blocks that are not ambiguous (no second-ranked transit zone) */ NOT EXISTS(
        SELECT
          1
        FROM ranked_block_zone_coverage AS ambiguous
        WHERE
          ambiguous.id = block_tz.id
          AND ambiguous.tz_rank = 2
          AND ambiguous.pct_covered > 10
      )
    UNION ALL
    /* Lot-level assignments for ambiguous blocks */
    SELECT
      bbls[1] AS bbl,
      transit_zone
    FROM ranked_lot_zone_coverage AS int_tz__bbl_to_tz_ranked
    WHERE
      tz_rank = 1
  ), lots_with_transit_zone_coverage AS (
    SELECT
      p.bbl
    FROM {{ ref('parcel_zoning_districts') }} AS p
    INNER JOIN transit_zone_footprint AS tz
      ON ST_INTERSECTS(p.geom, tz.geom)
  )
  SELECT
    a.bbl,
    CASE WHEN lic.bbl IS NOT NULL THEN a.transit_zone END AS trnstzone
  FROM preferred_zone_assignments AS a
  LEFT JOIN lots_with_transit_zone_coverage AS lic
    ON a.bbl = lic.bbl
)
SELECT * FROM transit_zone_by_lot
