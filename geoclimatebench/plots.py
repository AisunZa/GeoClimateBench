"""Produce lightweight publication-style figures (not cartographic maps)."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr


def create_plots(daily: xr.Dataset, extremes: xr.Dataset, outdir: str | Path) -> None:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    synthetic = "SYNTHETIC" in daily.attrs.get("source_type", "").upper()
    title_prefix = "Synthetic example" if synthetic else "Supplied input (not independently verified)"
    fig, ax = plt.subplots(figsize=(7.5, 5))
    z = extremes.heatwave_days.values
    art = ax.pcolormesh(extremes.longitude.values, extremes.latitude.values, z, cmap="YlOrRd", shading="nearest", vmin=0, vmax=max(1, int(z.max())))
    fig.colorbar(art, ax=ax, label="Heatwave days in selected month")
    ax.set(xlabel="Longitude (°E)", ylabel="Latitude (°N)", title=f"{title_prefix} • selected month heatwave-day count")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out / "heatwave_days.png", dpi=170)
    plt.close(fig)

    # Reference point used only for a transparent illustrative time series.
    ilat = int(np.argmin(np.abs(daily.latitude.values - 52.0)))
    ilon = int(np.argmin(np.abs(daily.longitude.values - 13.5)))
    lat, lon = float(daily.latitude.values[ilat]), float(daily.longitude.values[ilon])
    month = daily.tmax_c.sel(time=extremes.time)
    x = pd.DatetimeIndex(extremes.time.values)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(x, month.sel(latitude=lat, longitude=lon), label="Synthetic grid daily max (°C)", lw=2)
    ax.plot(x, extremes.threshold_c.sel(latitude=lat, longitude=lon), label="1991–2020 baseline p90 threshold", ls="--", lw=1.8)
    flags = extremes.heatwave_day.sel(latitude=lat, longitude=lon).values.astype(bool)
    ax.scatter(x[flags], month.sel(latitude=lat, longitude=lon).values[flags], color="crimson", label="Heatwave day", s=24, zorder=5)
    ax.set(xlabel="Date (UTC)", ylabel="Temperature (°C)", title=f"{title_prefix} • heatwave classification ({lat}°N, {lon}°E)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out / "heatwave_timeseries.png", dpi=170)
    plt.close(fig)
