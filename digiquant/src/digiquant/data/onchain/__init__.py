"""On-chain data providers — Polars-only, fail-soft.

Public surface:
    - hyperdash.HyperdashScraper / CohortPositioningProvider
    - hyperdash.get_onchain_cohort_positioning
    - hyperdash.cohort_summary_to_positioning (HTTP-free parser/divergence)
    - bitview.BitviewClient / fetch_bitview_series
    - bitview.series_data_to_frame (HTTP-free SeriesData parser)
"""
