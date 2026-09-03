"""API Registry Configuration.

Single source of truth for all external APIs pre-fetched by the background scheduler.
Contains ONLY declarative configuration dictionaries:
- name: Unique identifier for the data domain
- base_url_setting: The settings attribute holding the base URL
- endpoint: Path on the target API
- auth_header: Header name for authentication
- auth_setting: The settings attribute holding the API key/token
- interval_seconds: How frequently the scheduler fires the fetcher (in seconds)
- cache_key: The exact Redis key where normalized data is stored
- fetcher_module: Import path for the fetcher module
- fetcher_function: Name of the async fetcher function inside the module
- keywords: Keywords used by the online intent router to map user queries to this domain
- description: Human-readable description of the domain data
"""

from typing import Any, Dict, List

API_REGISTRY: List[Dict[str, Any]] = [
    {
        "name": "plots_info",
        "base_url_setting": "CROPO_API_BASE_URL",
        "endpoint": "/plots",
        "auth_header": "Authorization",
        "auth_setting": "CROPO_API_KEY",
        "interval_seconds": 1800,  # 30 mins
        "cache_key": "data:plots_info:latest",
        "fetcher_module": "app.fetchers.plots_info",
        "fetcher_function": "fetch_plots_info",
        "keywords": [
            "plot",
            "plots",
            "field",
            "fields",
            "acres",
            "acreage",
            "mango",
            "grape",
            "tomato",
            "wheat",
            "crop type",
            "crop variety",
            "variety",
            "plantation date",
            "irrigation type",
            "plot info",
            "plot 1",
            "plot 2",
        ],
        "description": "Active farm plots metadata including crop types, varieties, acreage, plantation dates, and irrigation methods.",
    },
    {
        "name": "cropo_weather",
        "base_url_setting": "CROPO_API_BASE_URL",
        "endpoint": "/current-temperature",
        "auth_header": "Authorization",
        "auth_setting": "CROPO_API_KEY",
        "interval_seconds": 600,  # 10 mins
        "cache_key": "data:cropo_weather:latest",
        "fetcher_module": "app.fetchers.cropo_weather",
        "fetcher_function": "fetch_cropo_weather",
        "keywords": [
            "weather",
            "temperature",
            "humidity",
            "rain",
            "rainfall",
            "forecast",
            "climate",
            "temp",
            "wind",
            "precipitation",
            "current weather",
            "current temperature",
        ],
        "description": "Live weather telemetry, temperature, humidity, rainfall, and atmospheric conditions.",
    },
    {
        "name": "soil_and_irrigation",
        "base_url_setting": "CROPO_API_BASE_URL",
        "endpoint": "/irrigation-and-soil-moisture/{plot_name}",
        "auth_header": "Authorization",
        "auth_setting": "CROPO_API_KEY",
        "interval_seconds": 900,  # 15 mins
        "cache_key": "data:soil_and_irrigation:latest",
        "fetcher_module": "app.fetchers.soil_irrigation",
        "fetcher_function": "fetch_soil_and_irrigation",
        "keywords": [
            "soil",
            "moisture",
            "soil moisture",
            "water",
            "irrigation",
            "water remain",
            "water balance",
            "water uptake",
            "drip",
            "irrigate",
            "soil status",
            "irrigation schedule",
            "eto",
            "et0",
            "evapotranspiration",
            "hourly et",
        ],
        "description": "Soil moisture measurements, daily water retention balance, and irrigation schedules across plots.",
    },
    {
        "name": "field_scores",
        "base_url_setting": "CROPO_API_BASE_URL",
        "endpoint": "/field_score",
        "auth_header": "Authorization",
        "auth_setting": "CROPO_API_KEY",
        "interval_seconds": 1200,  # 20 mins
        "cache_key": "data:field_scores:latest",
        "fetcher_module": "app.fetchers.field_score",
        "fetcher_function": "fetch_field_scores",
        "keywords": [
            "field score",
            "field scores",
            "health score",
            "crop health",
            "score",
            "ndvi",
            "ndmi",
            "ndwi",
            "vegetation",
            "vigor",
            "satellite",
            "pixel status",
        ],
        "description": "Remote sensing field health scores (0-100%), NDVI vegetation vigor, and ETo status.",
    },
    {
        "name": "daily_report",
        "base_url_setting": "CROPO_API_BASE_URL",
        "endpoint": "/daily-report",
        "auth_header": "Authorization",
        "auth_setting": "CROPO_API_KEY",
        "interval_seconds": 1800,  # 30 mins
        "cache_key": "data:daily_report:latest",
        "fetcher_module": "app.fetchers.daily_report",
        "fetcher_function": "fetch_daily_reports",
        "keywords": [
            "daily report",
            "report",
            "daily summary",
            "farm report",
            "plot report",
            "daily status",
            "overall report",
            "comprehensive report",
            "full report",
            "agronomic report",
            "field report",
            "summary report",
            "layer",
            "layers",
            "8 layer",
            "8 layers",
            "satellite layer",
            "water uptake",
            "pest detection",
            "pest",
            "npk",
            "nitrogen",
            "phosphorus",
            "potassium",
            "fertilizer",
            "fertilize",
            "fertiliser",
            "manure",
            "biomass",
            "growth stage",
            "pixel status",
            "pixel summary",
            "canopy health",
            "soil nutrition",
        ],
        "description": "Comprehensive daily report with 8 satellite intelligence layers: agro stats, growth, soil moisture map, water uptake, pest detection, NPK, weather, and forecast.",
    },
]


def get_api_by_name(name: str) -> Dict[str, Any] | None:
    """Retrieve an API configuration entry by domain name."""
    for api in API_REGISTRY:
        if api["name"] == name:
            return api
    return None
