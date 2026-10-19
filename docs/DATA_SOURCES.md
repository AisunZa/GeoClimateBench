# Data sources, citation and data-acquisition guidance

## Primary real-world source 1: ERA5-Land

- Provider: European Centre for Medium-Range Weather Forecasts (ECMWF) via Copernicus Climate Data Store (CDS).
- Dataset: **ERA5-Land hourly data from 1950 to present**.
- Dataset URL: https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land
- Catalogue DOI: https://doi.org/10.24381/cds.e2161bac
- Variable: `2m_temperature` / `t2m`, two-meter air temperature, kelvin (K).
- Intended use: time- and grid-resolved model/reanalysis temperatures.
- Acquisition: CDS account, acceptance of relevant terms; see current CDS API and data-extraction instructions. No API key is stored in this repository. **No ERA5 dataset is bundled.**

The sample conversion entry point supports ordinary NetCDF files with a scalar hourly time coordinate, latitude, longitude, and Kelvin temperature. CDS files may arrive as GRIB, split forecast-step coordinates, or different NetCDF conventions and require manual inspection first. Do not silently concatenate incompatible grids, duplicates, or disordered timestamps.

## Primary real-world source 2: DWD CDC

- Provider: Deutscher Wetterdienst (German Weather Service), Climate Data Center (CDC).
- Catalogue: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/historical/
- Format description: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/DESCRIPTION_obsgermany-climate-daily-kl_en.pdf
- Product: **daily KL** station archives, generally with `produkt_klima_tag_*.txt` semicolon-separated tables.
- Fields used: `STATIONS_ID` (station ID), `MESS_DATUM` (`YYYYMMDD`), `TXK` (daily maximum 2m temperature, °C). Sentinel `-999` indicates missing.
- Station latitude/longitude must be taken from the **official station metadata** for the corresponding ID. Values entered in README command examples are placeholders.

Quality control flags (`QN_4`) are present in CDC data and deserve a station-specific scientific treatment when publishing real results. The prototype parser does not filter using DWD quality codes. Its comparison is a structural numerical check, not a fully calibrated homogenized product.

## Default bundled demonstration

The demo produces **entirely synthetic** 1991–2020 baseline and 2022 target data from deterministic Python functions. The generated files are `data/hourly_synthetic.nc` and `data/stations_synthetic.csv`. They are not direct copies, transformations, or samples of ERA5 or DWD. This is deliberate: a credible offline benchmark must not invent observational provenance.

The precomputed `example_results/` folder contains only results of this same **synthetic** run, not real scientific findings.

## Real-world reproducibility checklist

When adding real data in a future version, record:

1. Official citation and dataset version or retrieval date.
2. Exact spatial bbox, resolution, station ID and coordinate metadata.
3. Variables, units, missing-value codes, calendar and clock conventions.
4. Relevant station quality-control codes and station reporting periods.
5. Temporal coverage of each baseline year and missing-grid exclusions.
6. The source file SHA256 checksums, software versions, and decision log for any manual fixes.
7. Domain of validity and statistical limitations of the comparison.

This will let a reviewer distinguish a reproducible scientific calculation from a polished but unverifiable result.
