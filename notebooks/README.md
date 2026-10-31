# Notebooks

Each notebook answers one research question from `docs/methodology.md` and
nothing else. Notebooks read from `data/processed/` and write figures to
`reports/figures/`. They do not mutate data in place.

| Notebook | Research question | Status |
|---|---|---|
| `01_osm_inventory.ipynb` | Inventory construction: extract, deduplicate, assign identifiers, map | Not started |
| `02_spatial_structure.ipynb` | RQ1 - elevation band and distance to the mountain front | Not started |
| `03_field_measurements.ipynb` | RQ2, RQ3 - thermal signature and seasonality | Blocked on field data |
| `04_accessibility.ipynb` | RQ5 - walking-distance population coverage | Not started |

RQ4 (water quality and land use) joins `03` and a land-use layer and will get
its own notebook once enough chemistry rows exist to make it meaningful.

## Conventions

- Clear all outputs before committing. A notebook diff with embedded images is
  unreviewable, and the figures belong in `reports/figures/` where they can be
  referenced from the README.
- The first cell loads data and prints the row count and the `confidence`
  breakdown, so that every run states what sample it is working from.
- Any figure built from a mix of `verified` and `reported` points says so in its
  caption. See `data/README.md` section 2.
- Analysis that depends on an Overpass extract records the extract's
  `.meta.json` timestamp in the notebook, because OSM changes continuously and a
  result is only reproducible against the extract it came from.
