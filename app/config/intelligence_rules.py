"""Centralized farm-intelligence thresholds and decision rules.

All magic numbers for moisture, rain, pest, nutrient, and health analysis
live here so engines stay configuration-driven.
"""

from typing import Any, Dict

# ---------------------------------------------------------------------------
# Freshness (age relative to the domain's scheduled refresh interval)
# ---------------------------------------------------------------------------
FRESHNESS_FRESH_MAX_RATIO = 1.0
FRESHNESS_AGING_MAX_RATIO = 2.0
FRESHNESS_STALE_MAX_RATIO = 4.0

# ---------------------------------------------------------------------------
# Soil moisture (%)
# ---------------------------------------------------------------------------
MOISTURE_SATURATED_PCT = 75.0
MOISTURE_OPTIMAL_LOW_PCT = 50.0
MOISTURE_DRY_PCT = 40.0
MOISTURE_CRITICAL_DRY_PCT = 30.0
MOISTURE_DROP_ANOMALY_PCT = 15.0

# ---------------------------------------------------------------------------
# Rain / forecast
# ---------------------------------------------------------------------------
RAIN_LIKELY_PCT = 50.0
RAIN_HIGH_PCT = 70.0
RAIN_LIGHT_MM = 2.0

# ---------------------------------------------------------------------------
# Field health / NDVI score (0-100)
# ---------------------------------------------------------------------------
FIELD_SCORE_EXCELLENT = 80.0
FIELD_SCORE_MODERATE = 55.0
FIELD_SCORE_STRESS = 40.0
FIELD_SCORE_DROP_ANOMALY = 12.0

# ---------------------------------------------------------------------------
# Pest pixel percentages
# ---------------------------------------------------------------------------
PEST_WATCH_PCT = 8.0
PEST_ALERT_PCT = 18.0
PEST_SPIKE_ANOMALY_PCT = 10.0

# ---------------------------------------------------------------------------
# Growth / canopy stress pixels
# ---------------------------------------------------------------------------
GROWTH_STRESS_WATCH_PCT = 15.0
GROWTH_STRESS_ALERT_PCT = 30.0

# ---------------------------------------------------------------------------
# Satellite soil-moisture layer (less-moisture pixels)
# ---------------------------------------------------------------------------
LAYER_MOISTURE_DRY_PIXEL_PCT = 35.0
LAYER_MOISTURE_EXCESS_PIXEL_PCT = 30.0

# ---------------------------------------------------------------------------
# Temperature swing anomaly (°C)
# ---------------------------------------------------------------------------
TEMP_SWING_ANOMALY_C = 8.0

# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------
TREND_STABLE_MAX_DELTA_RATIO = 0.05
TREND_VOLATILE_REVERSAL_COUNT = 2
TREND_MIN_POINTS = 3

# ---------------------------------------------------------------------------
# Confidence weights
# ---------------------------------------------------------------------------
CONFIDENCE_STALE_PENALTY = 1
CONFIDENCE_MISSING_CRITICAL_PENALTY = 2
CONFIDENCE_CONFLICT_PENALTY = 1
CONFIDENCE_NO_TREND_PENALTY = 0  # trends are optional; do not over-penalize

CRITICAL_DOMAINS_BY_TOPIC: Dict[str, list[str]] = {
    "irrigation": ["soil_and_irrigation", "cropo_weather"],
    "soil": ["soil_and_irrigation"],
    "weather": ["cropo_weather"],
    "pest": ["daily_report"],
    "nutrient": ["daily_report"],
    "crop_health": ["field_scores"],
    "forecast": ["cropo_weather"],
    "harvest": ["daily_report", "plots_info"],
    "plot_info": ["plots_info"],
}

DECISION_LABELS: Dict[str, Dict[str, str]] = {
    "en": {
        "IRRIGATE_NOW": "Irrigate now",
        "IRRIGATE_LIGHTLY": "Apply a light irrigation cycle",
        "WAIT_FOR_RAIN": "Wait for expected rain before irrigating",
        "MONITOR": "Monitor conditions; no urgent action",
        "INSPECT_FIELD": "Walk the field and inspect affected zones",
        "CHECK_PESTS": "Scout for pests in flagged zones",
        "CHECK_NUTRIENTS": "Review nutrient / fertilizer plan",
        "INSUFFICIENT_DATA": "Not enough fresh data to recommend a farm action",
    },
    "hi": {
        "IRRIGATE_NOW": "अभी सिंचाई करें",
        "IRRIGATE_LIGHTLY": "हल्की सिंचाई करें",
        "WAIT_FOR_RAIN": "संभावित बारिश का इंतज़ार करें",
        "MONITOR": "निगरानी रखें; अभी ज़रूरी कार्रवाई नहीं",
        "INSPECT_FIELD": "खेत का निरीक्षण करें",
        "CHECK_PESTS": "कीट प्रभावित क्षेत्रों की जाँच करें",
        "CHECK_NUTRIENTS": "पोषक तत्व / खाद योजना जाँचें",
        "INSUFFICIENT_DATA": "सिफारिश के लिए पर्याप्त ताज़ा डेटा नहीं है",
    },
    "mr": {
        "IRRIGATE_NOW": "आता सिंचन करा",
        "IRRIGATE_LIGHTLY": "हलके सिंचन करा",
        "WAIT_FOR_RAIN": "अपेक्षित पावसाची वाट पाहा",
        "MONITOR": "निरीक्षण करा; तातडीची कारवाई नाही",
        "INSPECT_FIELD": "शेताची पाहणी करा",
        "CHECK_PESTS": "कीड बाधित भाग तपासा",
        "CHECK_NUTRIENTS": "अन्नद्रव्य / खत योजना तपासा",
        "INSUFFICIENT_DATA": "शिफारसीसाठी पुरेसा ताजा डेटा नाही",
    },
    "kn": {
        "IRRIGATE_NOW": "ಈಗ ನೀರಾವರಿ ಮಾಡಿ",
        "IRRIGATE_LIGHTLY": "ಹಗುರ ನೀರಾವರಿ ಮಾಡಿ",
        "WAIT_FOR_RAIN": "ನಿರೀಕ್ಷಿತ ಮಳೆಗಾಗಿ ಕಾಯಿರಿ",
        "MONITOR": "ಪರಿಸ್ಥಿತಿ ಗಮನಿಸಿ; ತುರ್ತು ಕ್ರಮ ಬೇಡ",
        "INSPECT_FIELD": "ಜಮೀನನ್ನು ಪರಿಶೀಲಿಸಿ",
        "CHECK_PESTS": "ಕೀಟ ಬಾಧಿತ ಭಾಗಗಳನ್ನು ಪರಿಶೀಲಿಸಿ",
        "CHECK_NUTRIENTS": "ಪೋಷಕಾಂಶ / ಗೊಬ್ಬರ ಯೋಜನೆ ಪರಿಶೀಲಿಸಿ",
        "INSUFFICIENT_DATA": "ಶಿಫಾರಸಿಗೆ ಸಾಕಷ್ಟು ತಾಜಾ ಡೇಟಾ ಇಲ್ಲ",
    },
}

FARMER_TERMS: Dict[str, Dict[str, str]] = {
    "en": {
        "soil_moisture": "soil moisture",
        "irrigation": "irrigation",
        "weather": "weather",
        "forecast": "forecast",
        "field_score": "field health score",
        "crop_health": "crop health",
    },
    "hi": {
        "soil_moisture": "मिट्टी की नमी",
        "irrigation": "सिंचाई",
        "weather": "मौसम",
        "forecast": "पूर्वानुमान",
        "field_score": "फसल स्वास्थ्य स्कोर",
        "crop_health": "फसल स्वास्थ्य",
    },
    "mr": {
        "soil_moisture": "जमिनीतील ओलावा",
        "irrigation": "सिंचन",
        "weather": "हवामान",
        "forecast": "अंदाज",
        "field_score": "पीक आरोग्य स्कोअर",
        "crop_health": "पीक आरोग्य",
    },
    "kn": {
        "soil_moisture": "ಮಣ್ಣಿನ ತೇವಾಂಶ",
        "irrigation": "ನೀರಾವರಿ",
        "weather": "ಹವಾಮಾನ",
        "forecast": "ಮುನ್ಸೂಚನೆ",
        "field_score": "ಬೆಳೆ ಆರೋಗ್ಯ ಸ್ಕೋರ್",
        "crop_health": "ಬೆಳೆಯ ಆರೋಗ್ಯ",
    },
}


def decision_label(decision: str, language: str = "en") -> str:
    pack = DECISION_LABELS.get(language) or DECISION_LABELS["en"]
    return pack.get(decision, decision)


def farmer_term(key: str, language: str = "en") -> str:
    pack = FARMER_TERMS.get(language) or FARMER_TERMS["en"]
    return pack.get(key, key)


def as_dict() -> Dict[str, Any]:
    """Expose thresholds for debug/tests without importing every constant."""
    return {
        "moisture_dry_pct": MOISTURE_DRY_PCT,
        "moisture_saturated_pct": MOISTURE_SATURATED_PCT,
        "rain_likely_pct": RAIN_LIKELY_PCT,
        "pest_alert_pct": PEST_ALERT_PCT,
        "field_score_stress": FIELD_SCORE_STRESS,
    }
