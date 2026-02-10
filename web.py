#!/usr/bin/env python3

import matplotlib
import uvicorn

matplotlib.use("Agg")  # Use non-interactive backend
import base64
import io
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mpl_toolkits.basemap import Basemap

from database import get_all_ip_data, get_stats, init_database

WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))

app = FastAPI(title="IP Geolocation Heatmap")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize database on startup
init_database()


def create_heatmap_image(df: pd.DataFrame) -> str:
    """Generate heatmap and return as base64 encoded image"""
    # Source - https://stackoverflow.com/a/52184457
    # Posted by Thomas Kühn
    # Retrieved 2026-02-01, License - CC BY-SA 4.0

    fig, ax = plt.subplots(figsize=(16, 10))
    bmap = Basemap(
        ax=ax,
        projection="merc",
        llcrnrlon=-180,
        llcrnrlat=-60,
        urcrnrlon=180,
        urcrnrlat=80,
    )

    bmap.drawcountries()
    bmap.drawcoastlines()
    bmap.fillcontinents(color="lightgray", lake_color="lightblue", alpha=0.3)

    # Convert lat/lon to map projection coordinates
    x, y = bmap(df["longitude"].values, df["latitude"].values)

    # Plot scatter with size based on user count (using sqrt for better scaling)
    # This prevents huge circles from dominating the map

    min_size = 50
    max_size = 500
    sizes = np.sqrt(df["user_count"]) * 50
    sizes = np.clip(sizes, min_size, max_size)  # Cap sizes between 50 and 500

    ax.scatter(x, y, s=sizes, c="red", alpha=0.6, edgecolors="black", linewidth=1)

    plt.title("Shared IP Addresses Heatmap", fontsize=18, pad=20)

    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)

    # Encode to base64
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    return img_base64


@app.get("/", response_class=HTMLResponse)
async def show_heatmap(request: Request):
    """Display the heatmap with statistics"""

    # Get data
    ip_data = get_all_ip_data()
    stats = get_stats()

    if not ip_data:
        return templates.TemplateResponse("no_data.html", {"request": request})

    # Create heatmap
    df = pd.DataFrame(ip_data)
    img_base64 = create_heatmap_image(df)

    # Render template with data
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": stats,
            "heatmap_image": img_base64,
            "ip_data": ip_data,
        },
    )


if __name__ == "__main__":
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)
