# USDA rate snapshot

Publisher: USDA Agricultural Marketing Service (AMS).

- [Dataset and field descriptions](https://agtransport.usda.gov/Barge/Downbound-Grain-Barge-Rates/deqi-uken)
- [Complete CSV export](https://agtransport.usda.gov/api/views/deqi-uken/rows.csv?accessType=DOWNLOAD)
- [USDA explanation and benchmark table](https://www.ams.usda.gov/sites/default/files/media/Explanation%20of%20Barge%20Rates.pdf)
- [Grain Transportation Report defining a ton as 2,000 pounds](https://www.ams.usda.gov/sites/default/files/media/GTR04272023.pdf)

The full export retrieved November 15, 2026 contained 8,351 rows. It is saved in gitignored `data/raw/usda.csv`. The bundled `sample.csv` contains 371 unchanged source rows from November 11, 2025 through November 10, 2026. Selection includes every row within 366 days of the newest source observation. All seven locations and 21 blank quotes are retained. This is a historical snapshot, not a claim of live pricing.

`sample.json` records retrieval time, source URL, row counts, selection rule, units, observation range, full-export SHA-256 and sample SHA-256. `python -m barge_freight --refresh` downloads the complete export again and validates it before publishing a replacement sample. No application token is needed. Source schema changes stop the refresh instead of guessing column mappings.

`benchmarks.csv` is the canonical reference table in USD per short ton at 100% of tariff. The USDA PDF prints benchmark cents (619, 532, 399, 464, 469, 446, 314); its worked example makes clear that 619 means $6.19. The source CSV's name **Lower Illinois** maps to **ILLINOIS** in that PDF. These are documented geographic aliases, not separate markets. All other dataset origin labels are kept exactly.

USDA's dataset description gives a second worked example: 271% for St. Louis × $3.99 ÷ 100 = $10.8129, displayed as $10.81 per ton. The calculator preserves $10.8129 for shipment multiplication; multiplying an already rounded $10.81 by tonnage would introduce a rounding difference.

Public USDA data is separate from the MIT-licensed application code. This project is not affiliated with or endorsed by USDA. The benchmark table is a historical pricing convention; it is not an inflation adjustment, tax or customs duty.

`tests/fixtures/usda-2026-11-15.csv` preserves the same 371 source rows and checksum as the initial sample described above. Arithmetic and browser regression tests use this frozen fixture so later public-data refreshes do not remove their observation dates. A separate test validates the refreshable sample's hash, coverage, row count and date range against its own metadata.
