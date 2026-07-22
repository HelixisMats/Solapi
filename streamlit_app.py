"""
streamlit_app.py — Helixis LC Monitor
Tabs: Live (gauges) | Historik | SMHI & Analys
"""

import streamlit as st
from supabase import create_client
from streamlit_echarts import st_echarts
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os, requests

def send_alert_email(age_min: float):
    """Send email alert when data stops arriving. Uses Gmail SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    try:
        gmail_user = st.secrets.get("ALERT_GMAIL_USER", "")
        gmail_pass = st.secrets.get("ALERT_GMAIL_APP_PASSWORD", "")
        if not gmail_user or not gmail_pass:
            return  # Not configured — fail silently
        msg = MIMEText(
            f"⚠️ Helixis LC Monitor — No data received\n\n"
            f"Last data: {age_min:.0f} minutes ago\n"
            f"System may have lost MQTT connection.\n\n"
            f"Check the MQTT broker and sensor gateway at Eket, Örkelljunga.",
            "plain", "utf-8"
        )
        msg["Subject"] = f"⚠️ Helixis: No sensor data for {age_min:.0f} min"
        msg["From"]    = gmail_user
        msg["To"]      = "mats@helixis.se, eugene.nedilko@helixis.se"
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
    except Exception:
        pass  # Never crash the app due to email failure

st.set_page_config(page_title="Helixis LC Monitor", page_icon="🌀",
                   layout="wide", initial_sidebar_state="collapsed")

SWE    = ZoneInfo("Europe/Stockholm")
BG     = "#FFFFFF"; BG2 = "#F5F6FA"; BORDER = "#DDE0EB"
TEXT   = "#1C2033"; MUTED = "#8A90A8"; BLUE = "#1F4FE0"
TEAL   = "#167A5E"; AMBER = "#B87200"; RUST = "#A83030"; SLATE = "#2E5EA0"
LGRAY  = "#E4E7F0"
SITE_LAT, SITE_LON = 56.248, 13.192

LANG = {
    "en": {
        "live":"Live","history":"History","smhi":"SMHI","about":"About",
        "energy":"Energy","energy_today":"Energy today","heat_total":"Heat energy (total)",
        "delta_t":"ΔT Fwd−Ret",
        "collector_r":"Collector R","collector_l":"Collector L",
        "forward":"Forward","return":"Return","tank":"Tank",
        "flow":"Flow","power":"Thermal power","irradiance":"Solar irradiance",
        "pressure":"System pressure","wind":"Wind speed",
        "recv_r":"Receiver tube right","recv_l":"Receiver tube left",
        "max_power":"Max 9.2 kW @ 1000 W/m²","op_range":"Operating range 0–6 bar",
        "near_max":"⚠ Near max 6 bar","htf":"Heat-transfer fluid",
        "temperatures":"Temperatures","flow_env":"Flow, Power & Environment",
        "clear":"Clear sunshine","sunny":"Sunny","partly":"Partly cloudy",
        "cloudy":"Cloudy","overcast":"Overcast","night":"Night / no sun",
        "recv_r_sub":"Receiver tube right","recv_l_sub":"Receiver tube left",
        "fwd_sub":"Forward pipe","ret_sub":"Return pipe","tank_sub":"Storage tank",
        "htf_sub":"Heat-transfer fluid","max_power_sub":"Max 9.2 kW @ 1000 W/m²",
        "op_range_sub":"Operating range 0–6 bar","near_max_sub":"⚠ Near max 6 bar",
        "irr_excellent":"Excellent","irr_moderate":"Moderate","irr_low":"Low / night",
        "section_flow":"Flow, Power & Environment","display_mode":"Display mode",
        "no_data":"No data received.",
        "section_solar":"Solar, Power & Weather",
        "section_temps_pressure":"Temperatures & System pressure",
        "section_dt_flow":"ΔT & Flow","section_summary":"Summary for period",
        "section_energy":"Energy","energy_today_trap":"Energy today (trapezoid)",
        "heat_sensor_total":"Heat energy sensor (total)",
        "pressure_lbl":"Pressure (bar)","flow_lbl":"Flow (m³/h)",
        "power_lbl":"Thermal power (kW)","irr_lbl":"Irradiance (W/m²)","wind_lbl":"Wind (m/s)",
        "trap_help":"Calculated via trapezoid integration. ΔE=(P₁+P₂)/2×Δt — more accurate than sensor.",
        "heat_help":"Accumulated from energy sensor since last reset.",
        "loading_hist":"Loading history…","no_data_interval":"No data for selected interval.",
        "raw_export":"Raw data & export","download_csv":"Download CSV",
        "analysis_period":"Analysis period",
        "loading_smhi":"Loading SMHI station data…","loading_strang":"Loading STRÅNG model data…",
    },
    "sv": {
        "live":"Live","history":"Historik","smhi":"SMHI","about":"Om",
        "energy":"Energi","energy_today":"Energi idag","heat_total":"Värmeenergi (total)",
        "delta_t":"ΔT Fwd−Ret",
        "collector_r":"Collector R","collector_l":"Collector L",
        "forward":"Framledning","return":"Retur","tank":"Tank",
        "flow":"Flöde","power":"Termisk effekt","irradiance":"Solinstrålning",
        "pressure":"Systemtryck","wind":"Vindhastighet",
        "recv_r":"Mottagarrör höger","recv_l":"Mottagarrör vänster",
        "max_power":"Max 9.2 kW @ 1000 W/m²","op_range":"Driftområde 0–6 bar",
        "near_max":"⚠ Nära max 6 bar","htf":"Värmevätskeflöde",
        "temperatures":"Temperaturer","flow_env":"Flöde, Effekt & Miljö",
        "clear":"Klarsolsken","sunny":"Soligt","partly":"Halvklart",
        "cloudy":"Molnigt","overcast":"Mulet","night":"Natt / ingen sol",
        "recv_r_sub":"Mottagarrör höger","recv_l_sub":"Mottagarrör vänster",
        "fwd_sub":"Framledning","ret_sub":"Retur","tank_sub":"Lagertank",
        "htf_sub":"Värmevätskeflöde","max_power_sub":"Max 9.2 kW @ 1000 W/m²",
        "op_range_sub":"Driftområde 0–6 bar","near_max_sub":"⚠ Nära max 6 bar",
        "irr_excellent":"Utmärkt","irr_moderate":"Måttlig","irr_low":"Låg / natt",
        "section_flow":"Flöde, Effekt & Miljö","display_mode":"Visningsläge",
        "no_data":"Ingen data mottagen.",
        "section_solar":"Sol, Effekt & Väder",
        "section_temps_pressure":"Temperaturer & Systemtryck",
        "section_dt_flow":"ΔT & Flöde","section_summary":"Sammanfattning för perioden",
        "section_energy":"Energi","energy_today_trap":"Energi idag (trapets)",
        "heat_sensor_total":"Värmeenergisensor (total)",
        "pressure_lbl":"Tryck (bar)","flow_lbl":"Flöde (m³/h)",
        "power_lbl":"Termisk effekt (kW)","irr_lbl":"Instrålning (W/m²)","wind_lbl":"Vind (m/s)",
        "trap_help":"Beräknad med trapetsintegration. ΔE=(P₁+P₂)/2×Δt — mer exakt än sensorn.",
        "heat_help":"Ackumulerat värde från energisensorn sedan senaste nollställning.",
        "loading_hist":"Hämtar historik…","no_data_interval":"Ingen data för valt intervall.",
        "raw_export":"Rådata & export","download_csv":"Ladda ner CSV",
        "analysis_period":"Analysperiod",
        "loading_smhi":"Hämtar SMHI stationsdata…","loading_strang":"Hämtar STRÅNG modelldata…",
    },
}

# SMHI stations closest to Örkelljunga
# Ängelholm 63600: temp(1), wind(4), cloudcover(16)
# Malmö 52350: global radiation(11) — closest active station with param 11
SMHI = {
    "temperature": ("1",  "63600"),
    "wind_speed":  ("4",  "63600"),
    "irradiance":  ("11", "64565"),   # Växjö Sol
    "humidity":    ("6",  "63600"),   # Relative humidity
}

st.markdown(f"""<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  header[data-testid="stHeader"]{{background:transparent!important;height:0!important;}}
  #MainMenu,footer{{visibility:hidden;}}
  html,body,[class*="css"]{{font-family:'Inter',-apple-system,sans-serif!important;background:{BG};color:{TEXT};}}
  .block-container{{padding-top:1.2rem!important;padding-bottom:1.5rem;background:{BG};max-width:1400px;}}
  .stApp{{background:{BG};}}
  section[data-testid="stSidebar"]{{background:{BG2};border-right:1px solid {BORDER};}}

  /* Metric tiles */
  div[data-testid="metric-container"]{{background:{BG2};border:1px solid {BORDER};border-radius:8px;padding:14px 18px;}}
  div[data-testid="metric-container"] label{{font-size:.72rem!important;color:{TEXT}!important;text-transform:uppercase;letter-spacing:.08em;font-weight:700!important;}}
  div[data-testid="metric-container"] [data-testid="stMetricValue"]{{color:{TEXT}!important;font-size:1.5rem!important;font-weight:700!important;}}

  /* Section titles */
  .section-title{{font-size:.68rem;font-weight:700;color:{TEXT};text-transform:uppercase;
    letter-spacing:.1em;margin:20px 0 10px;border-left:3px solid {BLUE};padding-left:10px;}}

  /* Status */
  .status-dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle;}}
  .ts-text{{font-size:.85rem;color:{TEXT};vertical-align:middle;font-weight:500;}}

  /* Tabs — compact for mobile */
  .stTabs [data-baseweb="tab-list"]{{gap:0px!important;}}
  .stTabs [data-baseweb="tab"]{{
    font-size:.78rem!important;font-weight:700!important;
    padding:6px 8px!important;white-space:nowrap;
    color:{TEXT}!important;
  }}
  .stTabs [aria-selected="true"]{{
    color:{BLUE}!important;border-bottom:2px solid {BLUE}!important;
  }}

  /* Plotly toolbar hidden */
  .modebar{{display:none!important;}}
</style>
""", unsafe_allow_html=True)

# ── DB ────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
db = get_db()

# ── Sensor data ───────────────────────────────────────────────
@st.cache_data(ttl=25)
def fetch_live() -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    try:
        res = db.table("sensor_readings").select("created_at,sensor,value") \
            .gte("created_at", since).order("created_at", desc=False).execute()
        if not res.data: return pd.DataFrame()
        df = pd.DataFrame(res.data)
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
        return df.sort_values("created_at")
    except Exception as e:
        st.error(f"DB: {e}"); return pd.DataFrame()

@st.cache_data(ttl=120)
def fetch_history(hours_back: int) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    rows, psize, offset = [], 1000, 0
    try:
        while True:
            res = db.table("sensor_readings").select("created_at,sensor,value") \
                .gte("created_at", since).order("created_at", desc=False) \
                .range(offset, offset+psize-1).execute()
            batch = res.data
            if not batch: break
            rows.extend(batch)
            if len(batch) < psize: break
            offset += psize
    except Exception as e:
        st.error(f"DB: {e}"); return pd.DataFrame()
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df.sort_values("created_at")

@st.cache_data(ttl=1800)
def fetch_history_range(date_from, date_to) -> pd.DataFrame:
    """Fetch a specific date range. Cached 30 min — fast for historical analysis."""
    rows, psize, offset = [], 1000, 0
    try:
        while True:
            res = db.table("sensor_readings").select("created_at,sensor,value")                 .gte("created_at", date_from.isoformat())                 .lte("created_at", date_to.isoformat())                 .order("created_at", desc=False)                 .range(offset, offset+psize-1).execute()
            batch = res.data
            if not batch: break
            rows.extend(batch)
            if len(batch) < psize: break
            offset += psize
    except Exception as e:
        st.error(f"DB: {e}"); return pd.DataFrame()
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df.sort_values("created_at")

@st.cache_data(ttl=3600)
def fetch_daily_summary(days: int = 90) -> pd.DataFrame:
    """
    Fetch daily aggregates for overview chart — one row per day per sensor.
    Only pulls power + irradiance. Much lighter than raw data.
    Cached 1 hour — used only for the coarse date-selection overview.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows, psize, offset = [], 1000, 0
    try:
        while True:
            res = db.table("sensor_readings") \
                .select("created_at,sensor,value") \
                .in_("sensor", ["power", "irradiance"]) \
                .gte("created_at", since) \
                .order("created_at", desc=False) \
                .range(offset, offset + psize - 1).execute()
            batch = res.data
            if not batch: break
            rows.extend(batch)
            if len(batch) < psize: break
            offset += psize
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["date"] = df["created_at"].dt.tz_convert(ZoneInfo("Europe/Stockholm")).dt.date
    # Daily energy (kWh) via trapezoid per day, daily peak irradiance
    out = []
    for date, grp in df.groupby("date"):
        pwr = grp[grp["sensor"] == "power"].sort_values("created_at")
        irr = grp[grp["sensor"] == "irradiance"]
        if len(pwr) >= 2:
            import numpy as np
            times = pwr["created_at"].astype("int64").values / 1e9 / 3600
            fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
            kwh = float(max(0.0, fn(pwr["value"].values.astype(float), times)))
        else:
            kwh = 0.0
        peak_irr = float(irr["value"].max()) if not irr.empty else 0.0
        out.append({"date": date, "kwh": round(kwh, 2), "peak_irr": round(peak_irr, 0)})
    return pd.DataFrame(out).sort_values("date")


@st.cache_data(ttl=60)
def fetch_today_power() -> pd.DataFrame:
    """Fetch all power readings from midnight today — used for energy integration."""
    now_swe   = datetime.now(SWE)
    today_utc = now_swe.replace(hour=0, minute=0, second=0, microsecond=0)                        .astimezone(timezone.utc)
    rows, psize, offset = [], 1000, 0
    try:
        while True:
            res = db.table("sensor_readings")                 .select("created_at,sensor,value")                 .eq("sensor", "power")                 .gte("created_at", today_utc.isoformat())                 .order("created_at", desc=False)                 .range(offset, offset + psize - 1).execute()
            batch = res.data
            if not batch: break
            rows.extend(batch)
            if len(batch) < psize: break
            offset += psize
    except Exception:
        return pd.DataFrame()
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df.sort_values("created_at")

@st.cache_data(ttl=1800)
def fetch_strang(days_back: int = 1):
    """
    Fetch DNI+GHI from SMHI STRÅNG via the new Open Data API.
    New URL: opendata-download-metanalys.smhi.se/api/category/strang1g/...
    Parameter 116=GHI, 118=DNI
    Time format: YYYYMMDDhh  (hour appended)
    Returns (DataFrame, errors_dict).
    """
    now_swe = datetime.now(SWE)
    # from = yesterday 00:00, to = today current hour
    from_dt = (now_swe - timedelta(days=days_back)).strftime("%Y%m%d") + "00"
    to_dt   = now_swe.strftime("%Y%m%d%H")
    base    = "https://opendata-download-metanalys.smhi.se/api/category/strang1g/version/1"
    rows, errors = [], {}
    for par, name in [("116", "ghi_strang"), ("118", "dni_strang")]:
        url = (f"{base}/geotype/point"
               f"/lon/{SITE_LON}/lat/{SITE_LAT}"
               f"/parameter/{par}/data.json"
               f"?from={from_dt}&to={to_dt}&interval=hourly")
        try:
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                errors[name] = f"HTTP {r.status_code} · {url}"
                continue
            data = r.json()
            # Response is a list of {date_time, value} or wrapped in timeSeries
            items = data if isinstance(data, list) else data.get("timeSeries", [])
            if not items:
                errors[name] = f"Empty JSON response · keys: {list(data.keys()) if isinstance(data, dict) else 'list'}"
                continue
            parsed = 0
            for item in items:
                try:
                    # date_time is epoch ms or ISO string
                    dt_raw = item.get("date_time") or item.get("dateTime") or item.get("t")
                    val    = item.get("value") or item.get("v")
                    if dt_raw is None or val is None:
                        continue
                    if isinstance(dt_raw, (int, float)):
                        ts = pd.to_datetime(dt_raw, unit="ms", utc=True)
                    else:
                        ts = pd.to_datetime(dt_raw, utc=True)
                    rows.append({"created_at": ts, "sensor": name, "value": float(val)})
                    parsed += 1
                except Exception:
                    continue
            if parsed == 0:
                errors[name] = f"Could not parse response. Sample: {str(items[:2])[:200]}"
        except requests.exceptions.ConnectionError as e:
            errors[name] = f"Connection error: {e}"
        except Exception as e:
            errors[name] = str(e)
    df = pd.DataFrame(rows).sort_values("created_at") if rows else pd.DataFrame()
    return df, errors

# ── SMHI fetcher + Supabase storage ──────────────────────────
@st.cache_data(ttl=600)
def fetch_smhi_and_store() -> tuple[dict, dict]:
    """Fetch SMHI latest-day data. Returns (data_dict, error_dict)."""
    # Correct SMHI station IDs for southern Sweden
    # Parameter docs: https://opendata.smhi.se/apidocs/metobs/parameter.html
    SMHI_PARAMS = {
        "temperature": ("1",  "62040"),   # Helsingborg lufttemperatur
        "wind_speed":  ("4",  "62040"),   # Helsingborg vindhastighet
        "irradiance":  ("11", "64565"),   # Växjö Sol — globalstrålning (~60km)
        "humidity":    ("6",  "62040"),   # Helsingborg luftfuktighet
    }
    result, errors = {}, {}
    for key, (param, station) in SMHI_PARAMS.items():
        url = (f"https://opendata-download-metobs.smhi.se/api/version/latest"
               f"/parameter/{param}/station/{station}/period/latest-day/data.json")
        try:
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                errors[key] = f"HTTP {r.status_code} · station {station} · param {param}"
                result[key] = None
                continue
            data = r.json()
            rows = []
            for entry in data.get("value", []):
                try:
                    ts  = pd.to_datetime(entry["date"], unit="ms", utc=True)
                    val = float(entry["value"])
                    rows.append({"created_at": ts, "value": val})
                except Exception:
                    continue
            if not rows:
                errors[key] = "Inga värden i API-svaret"
                result[key] = None
                continue
            df = pd.DataFrame(rows).sort_values("created_at")
            result[key] = df
            # Store in Supabase
            try:
                to_insert = [
                    {"created_at": row["created_at"].isoformat(),
                     "sensor": f"smhi_{key}", "value": row["value"]}
                    for _, row in df.iterrows()
                ]
                db.table("smhi_readings").upsert(
                    to_insert, on_conflict="created_at,sensor"
                ).execute()
            except Exception:
                pass
        except requests.exceptions.ConnectionError as e:
            errors[key] = f"Nätverksfel: {e}"
            result[key] = None
        except Exception as e:
            errors[key] = str(e)
            result[key] = None
    return result, errors

@st.cache_data(ttl=300)
def fetch_smhi_history(hours_back: int) -> pd.DataFrame:
    """Read stored SMHI data from Supabase for historical charts."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    try:
        res = db.table("smhi_readings").select("created_at,sensor,value") \
            .gte("created_at", since).order("created_at", desc=False).execute()
        if not res.data: return pd.DataFrame()
        df = pd.DataFrame(res.data)
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
        return df
    except Exception:
        return pd.DataFrame()

# ── Helpers ───────────────────────────────────────────────────
def naive_swe(s):
    """Return timestamps as tz-naive Swedish local wall-clock for Plotly.

    Data is stored in UTC. Plotly.js renders datetimes in UTC and ignores the
    timezone offset, so a tz-aware timestamp would display 2h behind (the stored
    UTC time). We convert to the site's local time (Örkelljunga / Europe/Stockholm)
    and drop the tz, so Plotly shows the correct local wall-clock for every viewer
    regardless of where they are. Safe on tz-naive input too."""
    try:
        return s.dt.tz_convert(SWE).dt.tz_localize(None)
    except (TypeError, AttributeError):
        return s  # already tz-naive

def latest_val(df, sensor):
    sub = df[df["sensor"] == sensor]
    return float(sub["value"].iloc[-1]) if not sub.empty else None

def fmt(val, decimals=1, unit=""):
    return f"{val:.{decimals}f} {unit}".strip() if val is not None else "—"

def mwh_to_kwh(val):
    """Convert heat_energy sensor (MWh) to kWh for display."""
    return val * 1000 if val is not None else None

def metric_tile(label, val, unit, mn, mx, color, decimals=1, warn=None):
    display = fmt(val, decimals, unit)
    pct = 0
    if val is not None and mx > mn:
        pct = max(0, min(100, round((val - mn) / (mx - mn) * 100)))
    warn_html = (f"<span style='color:{RUST};font-size:.7rem;margin-left:6px'>⚠</span>"
                 if warn and val is not None and val >= warn else "")
    return f"""
<div style='background:{BG2};border-radius:8px;padding:12px 14px;height:100%'>
  <div style='font-size:.68rem;font-weight:600;color:{TEXT};text-transform:uppercase;
              letter-spacing:.08em;margin-bottom:4px'>{label}</div>
  <div style='font-size:1.25rem;font-weight:700;color:{color};line-height:1.1'>
    {display}{warn_html}
  </div>
  <div style='height:3px;border-radius:2px;background:{BORDER};margin-top:8px'>
    <div style='height:100%;width:{pct}%;border-radius:2px;background:{color};
                transition:width .4s'></div>
  </div>
</div>"""

def render_tiles(specs):
    cols = st.columns(len(specs))
    for col, (label, val, unit, mn, mx, color, dec, warn) in zip(cols, specs):
        col.markdown(metric_tile(label, val, unit, mn, mx, color, dec, warn),
                     unsafe_allow_html=True)

def sky_condition(irr, T):
    if irr is None:    return "—",           "❓", MUTED
    if irr >= 1000:    return T["clear"],    "☀️",  AMBER   # >1000 fully possible in Sweden
    if irr >= 700:     return T["clear"],    "☀️",  AMBER
    if irr >= 500:     return T["sunny"],    "🌤",  AMBER
    if irr >= 300:     return T["partly"],   "⛅",  SLATE
    if irr >= 100:     return T["cloudy"],   "🌥",  MUTED
    if irr >= 20:      return T["overcast"], "☁️",  MUTED
    return                    T["night"],    "🌙",  MUTED

def integrate_power(df) -> float | None:
    """Trapezoid integration of power → kWh. Handles both full and pre-filtered DataFrames."""
    if df is None or df.empty:
        return None
    # Filter to power sensor if multi-sensor df, otherwise use as-is
    if "sensor" in df.columns:
        sub = df[df["sensor"] == "power"]
    else:
        sub = df  # already pre-filtered (e.g. from fetch_today_power)
    # Ensure created_at exists
    if "created_at" not in sub.columns:
        return None
    sub = sub.sort_values("created_at").dropna(subset=["created_at"])
    if len(sub) < 2:
        return None
    # Use "value" column if present, else first numeric column
    val_col = "value" if "value" in sub.columns else sub.select_dtypes("number").columns[0]
    times = sub["created_at"].astype("int64").values / 1e9 / 3600
    power = sub[val_col].values.astype(float)
    try:
        import numpy as np
        fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
        return float(max(0.0, fn(power, times)))
    except Exception:
        total = 0.0
        for i in range(1, len(times)):
            total += (power[i] + power[i-1]) / 2 * (times[i] - times[i-1])
        return max(0.0, total)

def linechart(df, sensors, colors, ylabel, height=300, extra_traces=None):
    names = {"temp_right_coll":"Collector R","temp_left_coll":"Collector L",
             "temp_tank":"Tank","temp_forward":"Forward","temp_return":"Return",
             "temp_difference":"ΔT","power":"Power","flow":"Flow",
             "irradiance":"Irradiance","wind":"Wind","heat_energy":"Heat energy"}
    fig = go.Figure()
    for s, c in zip(sensors, colors):
        sub = df[df["sensor"]==s]
        if sub.empty: continue
        fig.add_trace(go.Scatter(x=sub["created_at"],y=sub["value"],
            name=names.get(s,s),mode="lines",line=dict(width=1.8,color=c)))
    for t in (extra_traces or []):
        fig.add_trace(t)
    fig.update_layout(height=height,margin=dict(l=0,r=0,t=10,b=0),yaxis_title=ylabel,
        legend=dict(orientation="h",yanchor="bottom",y=1.02,font=dict(size=10,color=MUTED,family="Inter")),
        hovermode="x unified",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED,family="Inter"))
    fig.update_xaxes(showgrid=False,color=MUTED)
    fig.update_yaxes(gridcolor=BORDER,color=MUTED)
    return fig

# ── Gauge functions ───────────────────────────────────────────
def echarts_gauge(label, val, mn, mx, unit, green_end=None, warn_start=None, mode="performance"):
    """
    ECharts dial gauge.
    mode="performance"  — single green arc (higher = better, no danger zones)
    mode="limit"        — green / amber / red (pressure, temps near max)
    mode="temp"         — cool blue → green → warm red gradient across full range
    """
    if val is None: val = mn
    decimals = 0 if unit in ("W/m²", "°C") else (3 if unit == "m³/h" else 2)

    if mode == "temp":
        # Smooth 5-stop gradient: cold blue → teal → green → amber → red
        colors = [
            [0.20, "#5B8FD4"],  # cold blue
            [0.40, "#4CAF50"],  # comfortable green
            [0.65, "#8BC34A"],  # warm green
            [0.85, "#FF9800"],  # hot amber
            [1.00, "#F44336"],  # danger red
        ]
    elif mode == "limit":
        if green_end  is None: green_end  = mn + (mx - mn) * 0.75
        if warn_start is None: warn_start = mn + (mx - mn) * 0.90
        safe    = max(0.001, (green_end  - mn) / (mx - mn))
        caution = max(safe + 0.001, (warn_start - mn) / (mx - mn))
        colors = [
            [safe,    "#4CAF50"],
            [caution, "#FF9800"],
            [1.00,    "#F44336"],
        ]
    else:  # "performance" — solid green, no warning
        colors = [[1.0, "#4CAF50"]]

    return {
        "series": [{
            "type": "gauge",
            "startAngle": 215, "endAngle": -35,
            "min": mn, "max": mx,
            "splitNumber": 5,
            "radius": "90%", "center": ["50%", "58%"],
            "axisLine": {"lineStyle": {"width": 16, "color": colors}},
            "pointer": {"length": "62%", "width": 5, "itemStyle": {"color": "auto"}},
            "axisTick":  {"distance": -20, "length": 6,  "lineStyle": {"color": "#fff", "width": 1.5}},
            "splitLine": {"distance": -24, "length": 14, "lineStyle": {"color": "#fff", "width": 2.5}},
            "axisLabel": {"color": "inherit", "distance": 26, "fontSize": 10},
            "detail": {
                "valueAnimation": True,
                "formatter": "{value} " + unit,
                "color": "inherit", "fontSize": 20, "fontWeight": "bold",
                "offsetCenter": [0, "30%"],
            },
            "title": {"show": True, "offsetCenter": [0, "65%"],
                      "fontSize": 12, "fontWeight": "bold", "color": "#333"},
            "data": [{"value": round(float(val), decimals), "name": label}],
        }]
    }


def render_echarts_gauge(label, val, mn, mx, unit,
                         green_end=None, warn_start=None,
                         mode="performance", key=None, height=220):
    opt = echarts_gauge(label, val, mn, mx, unit, green_end, warn_start, mode)
    st_echarts(options=opt, height=f"{height}px",
               key=key or f"g_{label}_{mn}_{mx}")

# ── Header ────────────────────────────────────────────────────
hcols = st.columns([3, 3])
with hcols[0]:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=160)
    else:
        st.markdown(f"<div style='font-size:1.4rem;font-weight:800;color:{TEXT}'>HELIXIS</div>",
                    unsafe_allow_html=True)

st.markdown(f"<hr style='border:none;border-top:1px solid {BORDER};margin:6px 0 4px'>",
            unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────
lang = st.sidebar.radio("Language / Språk", ["English", "Svenska"],
                        horizontal=True, label_visibility="collapsed")
lang = "en" if lang == "English" else "sv"
T = LANG[lang]

# ── Access control ────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

with st.sidebar:
    st.markdown(f"<hr style='border:none;border-top:1px solid {BORDER};margin:8px 0'>",
                unsafe_allow_html=True)
    if st.session_state.authenticated:
        st.markdown(f"<div style='font-size:.75rem;color:{TEAL};margin-bottom:6px'>"
                    f"✓ Internal access</div>", unsafe_allow_html=True)
        if st.button("Log out", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()
    else:
        with st.expander("🔒 Internal login"):
            pwd = st.text_input("Password", type="password", label_visibility="collapsed",
                                placeholder="Enter internal password…")
            if st.button("Login", use_container_width=True):
                if pwd == st.secrets.get("ADMIN_PASSWORD", ""):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect password")

is_internal = st.session_state.authenticated

_tab_labels = [f"🔴 {T['live']}", f"📈 {T['history']}", f"ℹ️ {T['about']}"]
if is_internal:
    _tab_labels.insert(2, f"🌤 {T['smhi']}")

_tabs = st.tabs(_tab_labels)
tab_live = _tabs[0]
tab_hist = _tabs[1]
if is_internal:
    tab_smhi = _tabs[2]
    tab_om   = _tabs[3]
else:
    tab_smhi = None
    tab_om   = _tabs[2]

# ════════════════════════════════════════════════════════════════
# LIVE TAB
# ════════════════════════════════════════════════════════════════
with tab_live:

    view_mode = st.radio(T["display_mode"], ["🎯 Gauges", "📋 Kompakt"],
                         horizontal=True, label_visibility="collapsed")

    @st.fragment(run_every=30)
    def live_dashboard():
        df = fetch_live()
        if df.empty:
            st.warning(T["no_data"]); return

        v        = {s: latest_val(df,s) for s in df["sensor"].unique()}
        last_ts  = df["created_at"].max()
        age_min  = (datetime.now(timezone.utc)-last_ts).total_seconds()/60
        is_live  = age_min < 15
        last_swe = last_ts.astimezone(SWE)
        irr, pres = v.get("irradiance"), v.get("pressure")
        irr_color = AMBER if (irr and irr>600) else (SLATE if (irr and irr>200) else MUTED)
        pcolor    = RUST if (pres and pres>=5) else SLATE

        dot = TEAL if is_live else RUST
        st.markdown(
            f'<span class="status-dot" style="background:{dot}"></span>'
            f'<span class="ts-text">{last_swe.strftime("%H:%M:%S")} '
            f'{"· LIVE" if is_live else f"· {age_min:.0f} min sedan"}</span>',
            unsafe_allow_html=True)

        # Email alert if data has been missing for 30–31 min (fires once per gap)
        # Uses a narrow window to avoid repeat emails every 30s
        if not is_live and 30 <= age_min < 31:
            alert_key = f"alert_sent_{last_ts.date()}"
            if not st.session_state.get(alert_key):
                send_alert_email(age_min)
                st.session_state[alert_key] = True
        elif is_live:
            # Reset alert state when data returns
            for k in list(st.session_state.keys()):
                if k.startswith("alert_sent_"):
                    del st.session_state[k]

        df_today_pwr  = fetch_today_power()
        energy_today  = integrate_power(df_today_pwr)

        sky_label, sky_icon, sky_color = sky_condition(irr, T)
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;margin:6px 0 10px'>"
            f"<span style='font-size:1.8rem;line-height:1'>{sky_icon}</span>"
            f"<span style='font-size:1.05rem;font-weight:600;color:{sky_color}'>{sky_label}</span>"
            f"<span style='font-size:.8rem;color:{MUTED};margin-left:4px'>"
            f"{'· ' + fmt(irr, 0, 'W/m²') if irr is not None else ''}"
            f"</span></div>",
            unsafe_allow_html=True,
        )

        if view_mode == "🎯 Gauges":
            # ── Temperatures (semi gauges) ──
            st.markdown(f'<div class="section-title">{T["temperatures"]}</div>',
                        unsafe_allow_html=True)
            tc = st.columns(6)
            temp_specs = [
                ("collector_r","temp_right_coll", 20,160,"g_cr"),
                ("collector_l","temp_left_coll",  20,160,"g_cl"),
                ("forward",    "temp_forward",    20,120,"g_fw"),
                ("return",     "temp_return",     10,100,"g_rt"),
                ("tank",       "temp_tank",       10,100,"g_tk"),
            ]
            for col,(lbl_key,sensor,mn,mx,gkey) in zip(tc,temp_specs):
                with col:
                    render_echarts_gauge(T[lbl_key], v.get(sensor), mn, mx, "°C",
                        mode="temp", key=gkey)
            # Outside temperature from SMHI (last stored value)
            with tc[5]:
                smhi_now, _ = fetch_smhi_and_store()
                outside_temp = None
                df_ot = smhi_now.get("temperature")
                if isinstance(df_ot, pd.DataFrame) and not df_ot.empty:
                    outside_temp = float(df_ot["value"].iloc[-1])
                render_echarts_gauge("Outside (SMHI)", outside_temp, -25, 40, "°C",
                    mode="temp", key="g_outside")

            # ── Flow, Power, Irradiance, Pressure (semi gauges) ──
            st.markdown(f'<div class="section-title">{T["section_flow"]}</div>',
                        unsafe_allow_html=True)
            g1,g2,g3,g4 = st.columns(4)
            with g1:
                render_echarts_gauge(T["flow"], v.get("flow"), 0, 1, "m³/h",
                    mode="performance", key="g_flow")
            with g2:
                render_echarts_gauge(T["power"], v.get("power"), 0, 9.2, "kW",
                    mode="performance", key="g_power")
            with g3:
                render_echarts_gauge(T["irradiance"], irr, 0, 1500, "W/m²",
                    mode="performance", key="g_irr")
            with g4:
                render_echarts_gauge(T["pressure"], pres, 0, 6, "bar",
                    green_end=4.5, warn_start=5.2, mode="limit", key="g_pres")

            # ── Energy (tiles + bar charts) ──
            st.markdown(f'<div class="section-title">{T["energy"]}</div>',
                        unsafe_allow_html=True)
            render_tiles([
                (T["energy_today"], energy_today,             "kWh", 0, 30,   TEAL, 3, None),
                (T["heat_total"],   mwh_to_kwh(v.get("heat_energy")), "kWh", 0, 9999, BLUE, 3, None),
                (T["delta_t"],      v.get("temp_difference"), "°C",  0, 50,   BLUE, 2, None),
            ])

            # ── Hourly & Daily energy bar charts ──────────────
            df_7d = fetch_history(168)  # 7 days for daily bars
            if not df_7d.empty:
                pwr_all = df_7d[df_7d["sensor"]=="power"][["created_at","value"]].copy()
                pwr_all = pwr_all.sort_values("created_at")
                pwr_all["dt_h"] = pwr_all["created_at"].diff().dt.total_seconds().fillna(0) / 3600
                pwr_all["e_kwh"] = pwr_all["value"] * pwr_all["dt_h"]

                # Hourly — today only
                pwr_all["ts_swe"] = pwr_all["created_at"].dt.tz_convert(SWE)
                today_str = pd.Timestamp.now(tz=SWE).date()
                pwr_today = pwr_all[pwr_all["ts_swe"].dt.date == today_str].copy()

                ch1, ch2 = st.columns(2)

                with ch1:
                    st.markdown(f"<div style='font-size:.75rem;font-weight:600;color:{MUTED};"
                                f"text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px'>"
                                f"Hourly energy today (kWh)</div>", unsafe_allow_html=True)
                    if not pwr_today.empty:
                        hourly = pwr_today.groupby(pwr_today["ts_swe"].dt.hour)["e_kwh"].sum().reset_index()
                        hourly.columns = ["hour","kwh"]
                        hourly["label"] = hourly["hour"].apply(lambda h: f"{h:02d}:00")
                        fig_h = go.Figure(go.Bar(
                            x=hourly["label"], y=hourly["kwh"].round(3),
                            marker_color=TEAL, text=hourly["kwh"].round(2),
                            textposition="outside", textfont=dict(size=9, color=MUTED)))
                        fig_h.update_layout(
                            height=220, margin=dict(l=0,r=0,t=10,b=30),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            yaxis=dict(gridcolor=BORDER, color=MUTED, title="kWh"),
                            xaxis=dict(color=MUTED, showgrid=False),
                            font=dict(family="Inter", color=MUTED))
                        st.plotly_chart(fig_h, use_container_width=True,
                            config={"displayModeBar": False})
                    else:
                        st.caption("No data for today yet")

                with ch2:
                    st.markdown(f"<div style='font-size:.75rem;font-weight:600;color:{MUTED};"
                                f"text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px'>"
                                f"Daily energy — last 7 days (kWh)</div>", unsafe_allow_html=True)
                    daily = pwr_all.groupby(pwr_all["ts_swe"].dt.date)["e_kwh"].sum().reset_index()
                    daily.columns = ["date","kwh"]
                    daily["label"] = pd.to_datetime(daily["date"]).dt.strftime("%b %d")
                    fig_d = go.Figure(go.Bar(
                        x=daily["label"], y=daily["kwh"].round(1),
                        marker_color=BLUE, text=daily["kwh"].round(1),
                        textposition="outside", textfont=dict(size=9, color=MUTED)))
                    fig_d.update_layout(
                        height=220, margin=dict(l=0,r=0,t=10,b=30),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        yaxis=dict(gridcolor=BORDER, color=MUTED, title="kWh"),
                        xaxis=dict(color=MUTED, showgrid=False),
                        font=dict(family="Inter", color=MUTED))
                    st.plotly_chart(fig_d, use_container_width=True,
                        config={"displayModeBar": False})

        else:
            # ── Compact tile view ──
            def tile(label,val,unit,mn,mx,color,dec=1,warn=None):
                display = fmt(val,dec,unit)
                pct = max(0,min(100,round((val-mn)/(mx-mn)*100))) if val is not None and mx>mn else 0
                wh = f"<span style='color:{RUST};font-size:.7rem;margin-left:4px'>⚠</span>" \
                     if warn and val and val>=warn else ""
                return f"""<div style='background:{BG2};border-radius:8px;padding:12px 14px'>
  <div style='font-size:.65rem;font-weight:500;color:{MUTED};text-transform:uppercase;
    letter-spacing:.08em;margin-bottom:4px'>{label}</div>
  <div style='font-size:1.2rem;font-weight:600;color:{color}'>{display}{wh}</div>
  <div style='height:3px;border-radius:2px;background:{BORDER};margin-top:7px'>
    <div style='height:100%;width:{pct}%;background:{color};border-radius:2px'></div>
  </div></div>"""

            st.markdown(f'<div class="section-title">{T["temperatures"]}</div>', unsafe_allow_html=True)
            cols = st.columns(5)
            for col,(lbl,s,col_,mn,mx) in zip(cols,[
                ("Collector R","temp_right_coll",RUST,20,160),
                ("Collector L","temp_left_coll",AMBER,20,160),
                ("Forward","temp_forward",RUST,20,120),
                ("Return","temp_return",SLATE,10,100),
                ("Tank","temp_tank",TEAL,10,100)]):
                col.markdown(tile(lbl,v.get(s),"°C",mn,mx,col_,1),unsafe_allow_html=True)

            st.markdown(f'<div class="section-title">{T["section_flow"]}</div>',
                        unsafe_allow_html=True)
            cols2 = st.columns(6)
            for col,(lbl,s,u,mn,mx,col_,dec,warn) in zip(cols2,[
                (T["flow"],"flow","m³/h",0,1,SLATE,3,None),
                (T["power"],"power","kW",0,9.2,RUST,2,None),
                (T["irradiance"],"irradiance","W/m²",0,1500,irr_color,0,None),
                (T["pressure"],"pressure","bar",0,6,pcolor,2,5.0),
                (T["wind"],"wind","m/s",0,20,SLATE,2,None),
                ("ΔT","temp_difference","°C",0,50,BLUE,2,None)]):
                col.markdown(tile(lbl,v.get(s),u,mn,mx,col_,dec,warn),unsafe_allow_html=True)

            st.markdown(f'<div class="section-title">{T["section_energy"]}</div>', unsafe_allow_html=True)
            e1,e2 = st.columns(2)
            e1.metric(T["energy_today_trap"], fmt(energy_today,3,"kWh"))
            e2.metric(T["heat_sensor_total"], fmt(mwh_to_kwh(v.get("heat_energy")),3,"kWh"))

        # ── Sol & Effekt — senaste två dagarna med data ───────
        st.markdown('<div class="section-title">Sol & Effekt — senaste två dagarna</div>',
                    unsafe_allow_html=True)
        df_48h = fetch_history(168)  # 7 dagar — hittar senaste dagarna oavsett gap
        if df_48h.empty:
            st.caption("Ingen data i databasen.")
        else:
            df_48h["swe"] = df_48h["created_at"].dt.tz_convert(SWE)
            df_48h["date_d"] = df_48h["swe"].dt.date
            # Hitta de två senaste dagarna som faktiskt har data
            available_days = sorted(df_48h["date_d"].unique(), reverse=True)
            if len(available_days) == 0:
                st.caption("Ingen data tillgänglig.")
            else:
                day_a = available_days[0]                                  # senaste
                day_b = available_days[1] if len(available_days) > 1 else None  # näst senaste
                label_a = "Idag" if day_a == datetime.now(SWE).date() else str(day_a)
                label_b = ("Igår" if day_b and day_b == datetime.now(SWE).date() - timedelta(days=1)
                           else str(day_b)) if day_b else None

                fig_cmp = go.Figure()
                has_traces = False
                for sensor, color, name, yaxis in [
                    ("irradiance", AMBER, T["irr_lbl"],   "y"),
                    ("power",      RUST,  T["power_lbl"], "y2"),
                ]:
                    sub = df_48h[df_48h["sensor"] == sensor].copy()
                    if sub.empty:
                        continue
                    for day, dash, opacity, lbl in [
                        (day_a, "solid", 1.0,  label_a),
                        (day_b, "dot",   0.5,  label_b),
                    ]:
                        if day is None:
                            continue
                        day_sub = sub[sub["date_d"] == day].copy()
                        if day_sub.empty:
                            continue
                        day_sub["time_str"] = day_sub["swe"].dt.strftime("%H:%M")
                        fig_cmp.add_trace(go.Scatter(
                            x=day_sub["time_str"], y=day_sub["value"],
                            name=f"{name} — {lbl}", mode="lines",
                            line=dict(width=1.8, color=color, dash=dash),
                            opacity=opacity, yaxis=yaxis,
                            hovertemplate=f"<b>%{{x}}</b><br>%{{y:.1f}}<extra>{name} {lbl}</extra>",
                        ))
                        has_traces = True

                if has_traces:
                    fig_cmp.update_layout(
                        height=300, margin=dict(l=0, r=70, t=10, b=0),
                        hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                    font=dict(size=10, color=MUTED, family="Inter")),
                        xaxis=dict(showgrid=False, color=MUTED, tickfont=dict(size=10)),
                        yaxis=dict(title=dict(text="W/m²", font=dict(color=AMBER)),
                                   tickfont=dict(color=AMBER), gridcolor=BORDER),
                        yaxis2=dict(title=dict(text="kW", font=dict(color=RUST)),
                                    tickfont=dict(color=RUST), overlaying="y",
                                    side="right", showgrid=False),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color=MUTED, family="Inter"),
                    )
                    st.plotly_chart(fig_cmp, use_container_width=True,
                                    config={"scrollZoom": True, "displayModeBar": True,
                                            "modeBarButtonsToRemove": ["select2d","lasso2d","autoScale2d"]})
                else:
                    st.caption(f"Data finns men inga irradiance/power-värden för {label_a} eller {label_b}.")

        # ── Senaste dygnet — temperaturer, ΔT, flöde & tryck (24h) ──
        # Kontinuerlig tidslinje för alla övriga värden. Lokal tid (naive_swe).
        st.markdown('<div class="section-title">Senaste dygnet — temperaturer & system</div>',
                    unsafe_allow_html=True)
        if df_48h.empty:
            st.caption("Ingen data i databasen.")
        else:
            cutoff24 = datetime.now(timezone.utc) - timedelta(hours=24)
            df_24 = df_48h[df_48h["created_at"] >= cutoff24].copy()
            if df_24.empty:
                st.caption("Ingen data senaste dygnet.")
            else:
                # Chart 1 — Temperaturer
                temp_names = {"temp_right_coll":T["collector_r"],"temp_left_coll":T["collector_l"],
                              "temp_forward":T["forward"],"temp_return":T["return"],"temp_tank":T["tank"]}
                temp_cmap  = {"temp_right_coll":RUST,"temp_left_coll":AMBER,"temp_forward":"#C1440E",
                              "temp_return":SLATE,"temp_tank":TEAL}
                fig24_t = go.Figure()
                for s in ["temp_right_coll","temp_left_coll","temp_forward","temp_return","temp_tank"]:
                    sub = df_24[df_24["sensor"] == s]
                    if not sub.empty:
                        fig24_t.add_trace(go.Scatter(
                            x=naive_swe(sub["created_at"]), y=sub["value"],
                            name=temp_names[s], mode="lines",
                            line=dict(width=1.6, color=temp_cmap[s])))
                fig24_t.update_layout(
                    height=260, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                               tickfont=dict(color=TEXT), gridcolor=BORDER),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"))
                fig24_t.update_xaxes(showgrid=False, color=MUTED)
                st.markdown(f"<div style='font-size:.72rem;font-weight:600;color:{MUTED};"
                            f"text-transform:uppercase;letter-spacing:.08em;margin:4px 0'>"
                            f"{T['temperatures']}</div>", unsafe_allow_html=True)
                st.plotly_chart(fig24_t, use_container_width=True,
                                config={"displayModeBar": False}, key="live24_temp")

                # Chart 2 — ΔT, Flöde & Tryck
                fig24_d = go.Figure()
                sub_dt = df_24[df_24["sensor"] == "temp_difference"]
                if not sub_dt.empty:
                    fig24_d.add_trace(go.Scatter(
                        x=naive_swe(sub_dt["created_at"]), y=sub_dt["value"],
                        name="ΔT (°C)", mode="lines", line=dict(width=1.6, color=TEXT), yaxis="y"))
                sub_fl = df_24[df_24["sensor"] == "flow"]
                if not sub_fl.empty:
                    fig24_d.add_trace(go.Scatter(
                        x=naive_swe(sub_fl["created_at"]), y=sub_fl["value"],
                        name=T["flow_lbl"], mode="lines", line=dict(width=1.6, color=SLATE), yaxis="y2"))
                sub_pr = df_24[df_24["sensor"] == "pressure"]
                if not sub_pr.empty:
                    fig24_d.add_trace(go.Scatter(
                        x=naive_swe(sub_pr["created_at"]), y=sub_pr["value"],
                        name=T["pressure_lbl"], mode="lines",
                        line=dict(width=1.5, color=TEAL, dash="dot"), yaxis="y3"))
                fig24_d.update_layout(
                    height=240, margin=dict(l=0, r=90, t=10, b=0), hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                               tickfont=dict(color=TEXT), gridcolor=BORDER),
                    yaxis2=dict(title=dict(text="m³/h", font=dict(color=SLATE)),
                                tickfont=dict(color=SLATE), overlaying="y", side="right",
                                showgrid=False, anchor="x"),
                    yaxis3=dict(title=dict(text="bar", font=dict(color=TEAL)),
                                tickfont=dict(color=TEAL), overlaying="y", side="right",
                                showgrid=False, anchor="free", position=1.0, range=[0, 8]),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"))
                fig24_d.update_xaxes(showgrid=False, color=MUTED)
                st.markdown(f"<div style='font-size:.72rem;font-weight:600;color:{MUTED};"
                            f"text-transform:uppercase;letter-spacing:.08em;margin:10px 0 4px'>"
                            f"{T['section_dt_flow']}</div>", unsafe_allow_html=True)
                st.plotly_chart(fig24_d, use_container_width=True,
                                config={"displayModeBar": False}, key="live24_dtflow")

    live_dashboard()

# ════════════════════════════════════════════════════════════════
# HISTORIK TAB
# ════════════════════════════════════════════════════════════════
with tab_hist:
    # ── Översikt — välj period ────────────────────────────────
    today = datetime.now(SWE).date()

    df_daily = fetch_daily_summary(days=90)
    if not df_daily.empty:
        st.markdown('<div class="section-title">Översikt — klicka för att välja period</div>',
                    unsafe_allow_html=True)
        fig_ov = go.Figure()
        fig_ov.add_trace(go.Bar(
            x=df_daily["date"].astype(str), y=df_daily["kwh"],
            name="Energi (kWh)", marker_color=TEAL,
            hovertemplate="<b>%{x}</b><br>%{y:.2f} kWh<extra></extra>",
        ))
        fig_ov.add_trace(go.Scatter(
            x=df_daily["date"].astype(str), y=df_daily["peak_irr"] / 150,
            name="Toppinstrålning", mode="lines",
            line=dict(color=AMBER, width=1.5),
            yaxis="y2",
            hovertemplate="<b>%{x}</b><br>%{customdata:.0f} W/m²<extra></extra>",
            customdata=df_daily["peak_irr"],
        ))
        fig_ov.update_layout(
            height=160, margin=dict(l=0, r=0, t=6, b=0),
            hovermode="x unified", barmode="overlay",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=9, color=MUTED, family="Inter")),
            yaxis=dict(title="kWh", gridcolor=BORDER, color=MUTED,
                       tickfont=dict(size=9), titlefont=dict(size=9)),
            yaxis2=dict(overlaying="y", side="right", showgrid=False,
                        showticklabels=False),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_ov.update_xaxes(showgrid=False, color=MUTED, tickfont=dict(size=9),
                             tickangle=-45)
        st.plotly_chart(fig_ov, use_container_width=True,
                        config={"displayModeBar": False, "scrollZoom": False})
        st.caption("Gula linjen = toppinstrålning (W/m²). Blå staplar = daglig energi (kWh). "
                   "Välj period med datumväljarna nedan.")

    # ── Datumintervall ────────────────────────────────────────
    col_from, col_to = st.columns(2)
    with col_from:
        date_from = st.date_input("Från", value=today - timedelta(days=7),
                                  max_value=today, key="hist_from")
    with col_to:
        date_to = st.date_input("Till", value=today,
                                min_value=date_from, max_value=today, key="hist_to")

    # Convert to UTC datetimes covering full days in Swedish time
    dt_from = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=SWE).astimezone(timezone.utc)
    dt_to   = datetime.combine(date_to,   datetime.max.time()).replace(tzinfo=SWE).astimezone(timezone.utc)
    hours_back = max(1, int((dt_to - dt_from).total_seconds() / 3600) + 1)

    with st.spinner(T["loading_hist"]):
        df_hist   = fetch_history_range(dt_from, dt_to)
        df_smhi_h = fetch_smhi_history(hours_back)

    # Data lagras i UTC. Plotly ritar datum i UTC och struntar i tidszons-offset,
    # så vi konverterar till platsens lokala tid (Örkelljunga) och tar bort tz —
    # då visar alla grafer nedan lokal tid. Varje graf läser från dessa två frames.
    if not df_hist.empty:
        df_hist = df_hist.copy()
        df_hist["created_at"] = naive_swe(df_hist["created_at"])
    if not df_smhi_h.empty:
        df_smhi_h = df_smhi_h.copy()
        df_smhi_h["created_at"] = naive_swe(df_smhi_h["created_at"])

    if df_hist.empty:
        st.warning(T["no_data_interval"])
    else:
        cmap = {
            "temp_right_coll": RUST,  "temp_left_coll": AMBER,
            "temp_forward":    RUST,  "temp_return":    SLATE,
            "temp_tank":       TEAL,  "power":          RUST,
            "flow":            SLATE, "irradiance":     AMBER,
            "wind":            SLATE, "temp_difference": TEXT,
        }

        # ── 1. Sol, Effekt & Väder (kombinerad graf med dubbel y-axel) ──
        st.markdown('<div class="section-title">Sol, Effekt & Väder</div>',
                    unsafe_allow_html=True)
        fig_solar = go.Figure()
        # Vänster axel: instrålning W/m²
        # Höger axel: effekt kW och vind m/s (liknande skala 0-10)
        for sensor, color, name, yaxis, dash in [
            ("irradiance", AMBER, T["irr_lbl"],  "y",  "solid"),
            ("power",      RUST,  T["power_lbl"], "y2", "solid"),
            ("wind",       SLATE, T["wind_lbl"],         "y2", "dot"),
        ]:
            sub = df_hist[df_hist["sensor"] == sensor]
            if not sub.empty:
                fig_solar.add_trace(go.Scatter(
                    x=sub["created_at"], y=sub["value"],
                    name=name, mode="lines",
                    line=dict(width=1.8, color=color, dash=dash),
                    yaxis=yaxis,
                ))
        # Overlay outside temp (SMHI) on solar chart — shows temp effect on performance
        if not df_smhi_h.empty:
            sub_ot = df_smhi_h[df_smhi_h["sensor"] == "smhi_temperature"]
            if not sub_ot.empty:
                fig_solar.add_trace(go.Scatter(
                    x=sub_ot["created_at"], y=sub_ot["value"],
                    name="Outside temp °C (SMHI)", mode="lines",
                    line=dict(width=1.5, color="#7B5EA7", dash="dot"),
                    yaxis="y3"))
        fig_solar.update_layout(
            height=340, margin=dict(l=0, r=90, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="W/m²", font=dict(color=AMBER)),
                       tickfont=dict(color=AMBER), gridcolor=BORDER),
            yaxis2=dict(title=dict(text="kW / m/s", font=dict(color=RUST)),
                        tickfont=dict(color=RUST), overlaying="y", side="right",
                        showgrid=False),
            yaxis3=dict(title=dict(text="°C", font=dict(color="#7B5EA7")),
                        tickfont=dict(color="#7B5EA7"), overlaying="y",
                        side="right", anchor="free", position=1.0,
                        showgrid=False),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_solar.update_xaxes(showgrid=False, color=MUTED)
        st.plotly_chart(fig_solar, use_container_width=True, config={"scrollZoom":True,"displayModeBar":True,"modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"]})

        # ── 2. Temperaturer & Tryck ──────────────────────────
        st.markdown('<div class="section-title">Temperaturer & Systemtryck</div>',
                    unsafe_allow_html=True)
        temp_sensors = ["temp_right_coll","temp_left_coll","temp_forward","temp_return","temp_tank"]
        fig_temp = go.Figure()
        for s in temp_sensors:
            sub = df_hist[df_hist["sensor"] == s]
            if not sub.empty:
                names_map = {"temp_right_coll":"Collector R","temp_left_coll":"Collector L",
                             "temp_forward":"Forward","temp_return":"Return","temp_tank":"Tank"}
                fig_temp.add_trace(go.Scatter(x=sub["created_at"], y=sub["value"],
                    name=names_map[s], mode="lines",
                    line=dict(width=1.8, color=cmap[s]), yaxis="y"))
        # Outside temperature from SMHI (Helsingborg station)
        if not df_smhi_h.empty:
            sub_ot = df_smhi_h[df_smhi_h["sensor"] == "smhi_temperature"]
            if not sub_ot.empty:
                fig_temp.add_trace(go.Scatter(
                    x=sub_ot["created_at"], y=sub_ot["value"],
                    name="Outside temp (SMHI)", mode="lines",
                    line=dict(width=2, color="#7B5EA7", dash="dash"), yaxis="y"))
        fig_temp.update_layout(
            height=320, margin=dict(l=0, r=10, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                       tickfont=dict(color=TEXT), gridcolor=BORDER),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_temp.update_xaxes(showgrid=False, color=MUTED)
        st.plotly_chart(fig_temp, use_container_width=True, config={"scrollZoom":True,"displayModeBar":True,"modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"]})

        # ── 3. ΔT, Flöde & Tryck ──────────────────────────────
        st.markdown('<div class="section-title">ΔT, Flöde & Systemtryck</div>',
                    unsafe_allow_html=True)
        fig_dt = go.Figure()
        # Left axis: ΔT
        sub_dt = df_hist[df_hist["sensor"] == "temp_difference"]
        if not sub_dt.empty:
            fig_dt.add_trace(go.Scatter(
                x=sub_dt["created_at"], y=sub_dt["value"],
                name="ΔT (°C)", mode="lines",
                line=dict(width=1.8, color=TEXT), yaxis="y"))
        # Right axis (inner): Flow m³/h
        sub_fl = df_hist[df_hist["sensor"] == "flow"]
        if not sub_fl.empty:
            fig_dt.add_trace(go.Scatter(
                x=sub_fl["created_at"], y=sub_fl["value"],
                name=T["flow_lbl"], mode="lines",
                line=dict(width=1.8, color=SLATE), yaxis="y2"))
        # Right axis (outer): Pressure bar
        sub_pr = df_hist[df_hist["sensor"] == "pressure"]
        if not sub_pr.empty:
            fig_dt.add_trace(go.Scatter(
                x=sub_pr["created_at"], y=sub_pr["value"],
                name=T["pressure_lbl"], mode="lines",
                line=dict(width=1.5, color=TEAL, dash="dot"), yaxis="y3"))
        fig_dt.update_layout(
            height=280, margin=dict(l=0, r=90, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                       tickfont=dict(color=TEXT), gridcolor=BORDER),
            yaxis2=dict(title=dict(text="m³/h", font=dict(color=SLATE)),
                        tickfont=dict(color=SLATE), overlaying="y", side="right",
                        showgrid=False, anchor="x"),
            yaxis3=dict(title=dict(text="bar", font=dict(color=TEAL)),
                        tickfont=dict(color=TEAL), overlaying="y", side="right",
                        showgrid=False, anchor="free", position=1.0,
                        range=[0, 8]),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_dt.update_xaxes(showgrid=False, color=MUTED)
        st.plotly_chart(fig_dt, use_container_width=True, config={"scrollZoom":True,"displayModeBar":True,"modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"]})

        # ── 4. Sammanfattning & Energi ────────────────────────
        st.markdown('<div class="section-title">Sammanfattning för perioden</div>',
                    unsafe_allow_html=True)
        all_sensors = temp_sensors + ["power","flow","irradiance","wind","pressure","temp_difference"]
        piv = df_hist[df_hist["sensor"].isin(all_sensors)] \
            .groupby("sensor")["value"].agg(["min","max","mean"]).round(2).reset_index()
        piv.columns = ["Sensor","Min","Max","Medel"]
        sensor_order = all_sensors
        piv["_ord"] = piv["Sensor"].apply(lambda s: sensor_order.index(s)
                                           if s in sensor_order else 99)
        st.dataframe(piv.sort_values("_ord").drop(columns="_ord"),
                     use_container_width=True, hide_index=True)

        # Energy today always uses full-day data — same source as Live tab
        ep_today = integrate_power(fetch_today_power())
        ep_window = integrate_power(df_hist)   # energy in selected window only

        st.markdown(f'<div class="section-title">{T["section_energy"]}</div>', unsafe_allow_html=True)
        ec1, ec2, ec3 = st.columns(3)
        ec1.metric(T["energy_today_trap"], fmt(ep_today, 3, "kWh"),
            help=T["trap_help"])
        ec2.metric(f"{T['energy_today_trap']} ({T['history']} window)",
            fmt(ep_window, 3, "kWh"),
            help="Energy in the selected history window only (not necessarily from midnight).")
        ec2.metric(T["heat_sensor_total"],
                   fmt(mwh_to_kwh(latest_val(df_hist,"heat_energy")), 3, "kWh"),
                   help=T["heat_help"])

        # ── Temporary: Three-method power correlation ────────────
        with st.expander("🔬 Power correlation: 3 methods (temporary analysis)", expanded=True):
            st.markdown(f"""
**M1 — Power sensor:** Direct `power` reading, kW.
**M2 — Flow×ΔT (physics):** `P = flow/3600 × ρ × cp × (T_fwd − T_ret)`, kW.
**M3 — Heat energy counter:** Cumulative kWh delta since first sample (MWh×1000). Reset date unknown.

**Instantaneous power chart** compares M1 vs M2. **Cumulative energy chart** compares all three from t₀.
If M1 ≈ M2 → controller calculates power internally from flow×ΔT (not independent).
Ratio M1/M2 reveals the actual cp of the fluid.
""")
            RHO = 1000
            CP_DEFAULT = 3800

            # cp slider — always visible so it drives both charts
            cp_val = st.slider("cp (J/kg·K) — adjust to match M1 vs M2",
                               min_value=3400, max_value=4200, value=CP_DEFAULT, step=50,
                               help="Pure water=4186 · 30% glycol≈3800 · 50% glycol≈3500")

            sensors_needed = ["power", "flow", "temp_forward", "temp_return", "heat_energy"]
            dfs = {}
            for s in sensors_needed:
                sub = df_hist[df_hist["sensor"] == s][["created_at","value"]].copy()
                sub = sub.rename(columns={"value": s}).set_index("created_at")
                dfs[s] = sub

            if all(s in dfs and not dfs[s].empty for s in ["flow","temp_forward","temp_return"]):
                base = dfs["flow"]
                for s in ["temp_forward","temp_return","power","heat_energy"]:
                    if s in dfs and not dfs[s].empty:
                        base = pd.merge_asof(
                            base.sort_index().reset_index(),
                            dfs[s].sort_index().reset_index(),
                            on="created_at", tolerance=pd.Timedelta("2min")
                        ).set_index("created_at")
                base = base.dropna(subset=["flow","temp_forward","temp_return"])

                # M2 with selected cp
                base["p_physics"] = (
                    base["flow"] / 3600 * RHO * cp_val *
                    (base["temp_forward"] - base["temp_return"])
                ) / 1000

                # M3: cumulative delta from t₀ in kWh
                if "heat_energy" in base.columns and not base["heat_energy"].dropna().empty:
                    e0 = float(base["heat_energy"].dropna().iloc[0])
                    base["heat_kwh_delta"] = (base["heat_energy"] - e0) * 1000

                # ── Instantaneous power chart (M1 vs M2) ──────────
                st.markdown(f'<div class="section-title">Instantaneous power — M1 vs M2 (kW)</div>',
                            unsafe_allow_html=True)
                fig_pwr = go.Figure()
                if "power" in base.columns:
                    fig_pwr.add_trace(go.Scatter(
                        x=base.index, y=base["power"],
                        name="M1: power sensor (kW)",
                        mode="lines", line=dict(color=RUST, width=2)))
                fig_pwr.add_trace(go.Scatter(
                    x=base.index, y=base["p_physics"],
                    name=f"M2: flow×ΔT (kW, cp={cp_val})",
                    mode="lines", line=dict(color=TEAL, width=2, dash="dot")))
                fig_pwr.update_layout(
                    height=260, margin=dict(l=0,r=0,t=10,b=0),
                    yaxis_title="kW", hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"))
                fig_pwr.update_xaxes(showgrid=False, color=MUTED)
                fig_pwr.update_yaxes(gridcolor=BORDER, color=MUTED)
                st.plotly_chart(fig_pwr, use_container_width=True, config={"scrollZoom":True,"displayModeBar":True,"modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"]})

                # ── Correlation metrics ────────────────────────────
                if "power" in base.columns:
                    both = base[["power","p_physics"]].dropna()
                    if len(both) > 10:
                        corr  = both["power"].corr(both["p_physics"])
                        ratio = (both["power"] / both["p_physics"].replace(0, float("nan"))).median()
                        implied_cp = cp_val / ratio  # if ratio=1.087 → true cp = 3800/1.087
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Correlation M1 vs M2", f"{corr:.3f}",
                            help=">0.99 = power is calculated from flow×ΔT in controller")
                        c2.metric("Median ratio M1/M2", f"{ratio:.3f}",
                            help="1.0 = perfect. Deviation = cp mismatch or calibration offset")
                        c3.metric("cp used", f"{cp_val} J/kg·K")
                        c4.metric("Implied cp if ratio=1.0", f"{implied_cp:.0f} J/kg·K",
                            help="The cp value that would make M2 exactly match M1")
                        if corr > 0.99:
                            st.info("🔗 Correlation >0.99 — power sensor is calculated from flow×ΔT "
                                    "internally. M1 and M2 are **not independent**.")
                        elif corr > 0.95:
                            st.warning("⚠️ 0.95–0.99 — likely same source, small calibration difference.")
                        else:
                            st.success("✅ <0.95 — power sensor appears to be an independent measurement.")

                # ── Cumulative energy chart (M1 + M2 + M3) ────────
                st.markdown(f'<div class="section-title">Cumulative energy from t₀ — all 3 methods (kWh)</div>',
                            unsafe_allow_html=True)

                # M1 cumulative: trapezoid of power sensor
                pwr_sub = base["power"].dropna()
                times_h  = pwr_sub.index.astype("int64") / 1e9 / 3600
                try:
                    import numpy as np
                    fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
                    cum_m1 = []
                    t_arr = times_h.values
                    p_arr = pwr_sub.values
                    t0_h  = t_arr[0]
                    for i in range(len(t_arr)):
                        cum_m1.append(float(max(0, fn(p_arr[:i+1], t_arr[:i+1]) - t0_h * 0)))
                    # simpler: running integral
                    cum_m1 = [0.0]
                    for i in range(1, len(t_arr)):
                        cum_m1.append(cum_m1[-1] + (p_arr[i]+p_arr[i-1])/2*(t_arr[i]-t_arr[i-1]))
                except Exception:
                    cum_m1 = [0.0]
                    for i in range(1, len(t_arr)):
                        cum_m1.append(cum_m1[-1] + (p_arr[i]+p_arr[i-1])/2*(t_arr[i]-t_arr[i-1]))

                # M2 cumulative: trapezoid of p_physics aligned to same index
                phy_sub = base["p_physics"].reindex(pwr_sub.index, method="nearest")
                ph_arr  = phy_sub.values
                cum_m2  = [0.0]
                for i in range(1, len(t_arr)):
                    cum_m2.append(cum_m2[-1] + (ph_arr[i]+ph_arr[i-1])/2*(t_arr[i]-t_arr[i-1]))

                fig_cum = go.Figure()
                fig_cum.add_trace(go.Scatter(
                    x=pwr_sub.index, y=cum_m1,
                    name="M1 cumulative (power sensor, kWh)",
                    mode="lines", line=dict(color=RUST, width=2)))
                fig_cum.add_trace(go.Scatter(
                    x=pwr_sub.index, y=cum_m2,
                    name=f"M2 cumulative (flow×ΔT cp={cp_val}, kWh)",
                    mode="lines", line=dict(color=TEAL, width=2, dash="dot")))

                # M3: heat_energy counter delta
                if "heat_kwh_delta" in base.columns:
                    m3_sub = base["heat_kwh_delta"].dropna()
                    if not m3_sub.empty:
                        fig_cum.add_trace(go.Scatter(
                            x=m3_sub.index, y=m3_sub.values,
                            name="M3 cumulative (heat energy counter ÷1000→kWh)",
                            mode="lines", line=dict(color=BLUE, width=2, dash="dash")))

                fig_cum.update_layout(
                    height=280, margin=dict(l=0,r=0,t=10,b=0),
                    yaxis_title="kWh", hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"))
                fig_cum.update_xaxes(showgrid=False, color=MUTED)
                fig_cum.update_yaxes(gridcolor=BORDER, color=MUTED)
                st.plotly_chart(fig_cum, use_container_width=True, config={"scrollZoom":True,"displayModeBar":True,"modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"]})

                # Three-way end-of-window summary
                m1_end = cum_m1[-1] if cum_m1 else None
                m2_end = cum_m2[-1] if cum_m2 else None
                m3_end = float(base["heat_kwh_delta"].dropna().iloc[-1])                          if "heat_kwh_delta" in base.columns and not base["heat_kwh_delta"].dropna().empty else None
                s1, s2, s3 = st.columns(3)
                s1.metric("M1 total (window)", fmt(m1_end, 3, "kWh"))
                s2.metric("M2 total (window)", fmt(m2_end, 3, "kWh"))
                s3.metric("M3 delta (window)", fmt(m3_end, 3, "kWh"),
                          help="Change in heat energy counter over this window. "
                               "Already ×1000 (MWh→kWh). Should match M1 if calibrated.")
                if m1_end and m3_end and m1_end > 0.1:
                    m3_ratio = m3_end / m1_end
                    st.caption(f"M3/M1 ratio: {m3_ratio:.3f} — "
                               f"{'good agreement ✓' if 0.9 < m3_ratio < 1.1 else 'deviation — check calibration or reset'}")
            else:
                st.info("Need flow, temp_forward and temp_return data in selected window.")

        with st.expander(f"📥 {T['raw_export']}"):
            piv2 = df_hist.pivot_table(
                index="created_at", columns="sensor",
                values="value", aggfunc="last"
            ).reset_index().sort_values("created_at", ascending=False)
            st.dataframe(piv2.head(500), use_container_width=True)
            st.download_button(f"⬇️ {T['download_csv']}", df_hist.to_csv(index=False),
                f"helixis_{hours}h.csv", "text/csv")

# ════════════════════════════════════════════════════════════════
# SMHI & ANALYS TAB  (internal only)
# ════════════════════════════════════════════════════════════════
if is_internal and tab_smhi is not None:
     with tab_smhi:

        # ── Förklaringstext ───────────────────────────────────────
        with st.expander("ℹ️ Understanding STRÅNG model data — what each parameter means", expanded=False):
            st.markdown(f"""
    #### What is STRÅNG?

    STRÅNG is SMHI's gridded solar radiation model. Unlike weather stations (which only exist
    at fixed points), STRÅNG calculates radiation values for **any coordinate in the Nordic countries**
    using atmospheric physics and satellite cloud data. Resolution: 2.5 × 2.5 km, hourly.

    No API key needed. Data is freely available from SMHI Open Data.

    ---

    #### The three radiation parameters

    | Parameter | Full name | What it measures | Sensor type |
    |---|---|---|---|
    | **GHI** | Global Horizontal Irradiance | Total solar energy hitting a flat horizontal surface — direct + diffuse | Pyranometer (flat plate) |
    | **DNI** | Direct Normal Irradiance | Solar energy arriving in a straight line from the sun, measured perpendicular to the sun's rays | Pyrheliometer (tracks sun) |
    | **DHI** | Diffuse Horizontal Irradiance | Scattered light only (clouds, atmosphere) — GHI minus the direct component | Calculated |

    **Why DNI matters for Helixis:** The LC12 concentrates sunlight using mirrors. Diffuse light
    (scattered by clouds) arrives from all directions and cannot be focused. Only DNI contributes
    to useful output. On a heavily overcast day, GHI may be 200 W/m² but DNI is near zero — the
    system produces almost nothing despite "some" sunlight.

    ---

    #### Clearness index kt

    `kt = DNI_STRÅNG / GHI_STRÅNG`

    A dimensionless ratio from 0 to ~0.9 describing sky clarity:

    | kt value | Sky condition | Helixis output |
    |---|---|---|
    | 0.75 – 0.90 | Clear sky, direct sun | Full output possible |
    | 0.50 – 0.75 | Mostly clear, thin haze | Reduced ~10–30% |
    | 0.25 – 0.50 | Partly cloudy | Significantly reduced |
    | 0.00 – 0.25 | Overcast | Near-zero output |

    **Note on kt > 1.0:** This is physically valid at low solar elevation angles. Because GHI is
    measured on a horizontal surface while DNI is measured perpendicular to the sun:

    `GHI = DNI × cos(zenith angle) + diffuse`

    When the sun is low in the sky, DNI can exceed GHI, giving kt > 1.0 from STRÅNG.
    The app does not clip kt — the on-site sensor (IMT Si-RS485TC, rated 0–1500 W/m², ±1.6%) is
    trusted directly. Values above 1000 W/m² are fully possible on clear days in Sweden.

    ---

    #### How we estimate DNI without a pyrheliometer

    Since DNI sensors cost 30,000–100,000 SEK and require daily maintenance, we use:

    `DNI_estimated = kt_STRÅNG × GHI_sensor`

    This uses STRÅNG's sky-clarity ratio applied to our own on-site measurement.
    Accuracy is typically ±10–15% on clear days, worse on partially cloudy days
    (when cloud patterns between Örkelljunga and the STRÅNG grid cell differ).

    ---

    #### Theoretical vs actual power

    `P_theoretical = DNI_estimated × 12.35 m² × 0.65 = DNI × 8.03 W per W/m²`

    The 0.65 factor is the optical efficiency (peak ~0.72, realistic with tracking error and
    mirror soiling ~0.65). The gap between theoretical and actual power reveals system losses:
    mirror soiling, tracking error, pump issues, heat exchanger efficiency, and startup losses.

    ---
    *Sources: SMHI STRÅNG Open Data · Helsingborg station 62040 (temp/wind/humidity) · Växjö station 64565 (GHI station)*
    """)

        # ── Datumväljare ──────────────────────────────────────────
        _now_swe = datetime.now(SWE)
        _today   = _now_swe.date()

        # ── Day toggle buttons — last 7 days ──────────────────
        # Session state: set of selected dates
        if "smhi_selected_days" not in st.session_state:
            # Default: all 7 days selected
            st.session_state.smhi_selected_days = {
                _today - pd.Timedelta(days=i) for i in range(7)
            }

        # Show buttons for last 14 days, grouped in rows of 7
        st.markdown(f"<div style='font-size:.72rem;font-weight:600;color:{MUTED};"
                    f"text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px'>"
                    f"Select days for analysis</div>", unsafe_allow_html=True)

        # Row 1: last 7 days
        day_cols = st.columns(7)
        for i, col in enumerate(day_cols):
            d = _today - pd.Timedelta(days=6-i)
            label = d.strftime("%a\n%d %b")
            selected = d in st.session_state.smhi_selected_days
            if col.button(label,
                          key=f"day_{d}",
                          type="primary" if selected else "secondary",
                          use_container_width=True):
                if selected:
                    st.session_state.smhi_selected_days.discard(d)
                else:
                    st.session_state.smhi_selected_days.add(d)
                st.rerun()

        # Expand to older dates
        with st.expander("← Older dates"):
            old_cols = st.columns(7)
            for i, col in enumerate(old_cols):
                d = _today - pd.Timedelta(days=13-i)
                label = d.strftime("%a\n%d %b")
                selected = d in st.session_state.smhi_selected_days
                if col.button(label,
                              key=f"day_old_{d}",
                              type="primary" if selected else "secondary",
                              use_container_width=True):
                    if selected:
                        st.session_state.smhi_selected_days.discard(d)
                    else:
                        st.session_state.smhi_selected_days.add(d)
                    st.rerun()

        # Quick actions
        qa1, qa2, qa3 = st.columns([1,1,3])
        if qa1.button("Select all", key="sel_all", use_container_width=True):
            st.session_state.smhi_selected_days = {_today - pd.Timedelta(days=i) for i in range(14)}
            st.rerun()
        if qa2.button("Clear all", key="sel_none", use_container_width=True):
            st.session_state.smhi_selected_days = set()
            st.rerun()

        # Derive date_from / date_to from selected days
        selected_days = sorted(st.session_state.smhi_selected_days)
        if not selected_days:
            st.info("Select at least one day above.")
            st.stop()
        date_from = selected_days[0]
        date_to   = selected_days[-1]

        # Convert to UTC — from = start of first day, to = end of last day
        dt_from = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=SWE).astimezone(timezone.utc)
        dt_to   = datetime.combine(date_to,   datetime.max.time()).replace(tzinfo=SWE).astimezone(timezone.utc)
        h_cmp   = max(24, int((dt_to - dt_from).total_seconds() / 3600) + 24)

        col_l, col_r = st.columns(2)
        with col_l:
            with st.spinner(T["loading_smhi"]):
                smhi_data, smhi_errors = fetch_smhi_and_store()
        with col_r:
            with st.spinner(T["loading_strang"]):
                days_back = max(1, (date_to - date_from).days + 2)
                df_strang, strang_errors = fetch_strang(days_back)

        if smhi_errors:
            with st.expander(f"⚠️ {len(smhi_errors)} SMHI-stationskälla(or) saknas"):
                for key, msg in smhi_errors.items():
                    st.warning(f"**{key}**: {msg}")

        with st.expander("📧 Test alert email", expanded=False):
            import smtplib
            from email.mime.text import MIMEText
            _gu = st.secrets.get("ALERT_GMAIL_USER", "")
            _gp = st.secrets.get("ALERT_GMAIL_APP_PASSWORD", "")
            st.caption(f"From: {_gu or '(not configured)'} → mats@helixis.se, eugene.nedilko@helixis.se")
            if st.button("Send test email now", key="test_email"):
                if not _gu or not _gp:
                    st.error("❌ ALERT_GMAIL_USER or ALERT_GMAIL_APP_PASSWORD missing in Secrets")
                else:
                    try:
                        _msg = MIMEText("Test alert from Helixis LC Monitor.", "plain", "utf-8")
                        _msg["Subject"] = "✅ Helixis alert test"
                        _msg["From"]    = _gu
                        _msg["To"]      = "mats@helixis.se, eugene.nedilko@helixis.se"
                        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as _srv:
                            _srv.login(_gu, _gp)
                            _srv.send_message(_msg)
                        st.success(f"✅ Sent from {_gu}")
                    except Exception as _e:
                        st.error(f"❌ {_e}")

        if strang_errors:
            with st.expander(f"⚠️ STRÅNG model: {len(strang_errors)} parameter(s) failed", expanded=True):
                for k, msg in strang_errors.items():
                    st.warning(f"**{k}**: {msg}")
                st.caption(f"New URL: opendata-download-metanalys.smhi.se/api/category/strang1g/version/1"
                           f"/geotype/point/lon/{SITE_LON}/lat/{SITE_LAT}/parameter/118/data.json?from=YYYYMMDDhh&to=YYYYMMDDhh&interval=hourly")
        elif not df_strang.empty:
            sensors_loaded = df_strang["sensor"].unique().tolist()
            last_ts = df_strang["created_at"].max().astimezone(SWE).strftime("%H:%M")
            st.success(f"✓ STRÅNG: {len(df_strang)} rows · {', '.join(sensors_loaded)} · latest: {last_ts}")

        # ── Väder just nu ─────────────────────────────────────────
        st.markdown('<div class="section-title">Weather conditions (SMHI stations)</div>',
                    unsafe_allow_html=True)
        smhi_defs = {
            "temperature": ("Air temp",    "°C",  -20, 40,   SLATE, 1),
            "wind_speed":  ("Wind speed",  "m/s",   0, 25,   SLATE, 1),
            "irradiance":  ("GHI (Växjö)", "W/m²",  0, 1500, AMBER, 0),
            "humidity":    ("Humidity",    "%",      0, 100,  SLATE, 0),
        }
        tile_specs = []
        for key, (label, unit, mn, mx, color, dec) in smhi_defs.items():
            df_s = smhi_data.get(key)
            val  = float(df_s["value"].iloc[-1]) if isinstance(df_s, pd.DataFrame) and not df_s.empty else None
            tile_specs.append((label, val, unit, mn, mx, color, dec, None))
        render_tiles(tile_specs)

        # ── STRÅNG — DNI & kt-faktor ──────────────────────────────
        st.markdown('<div class="section-title">STRÅNG model — DNI & clearness index kt</div>',
                    unsafe_allow_html=True)

        # Fetch only the selected date range — cached 30 min, fast for historical days
        df_cmp = fetch_history_range(dt_from, dt_to)

        # All variables initialized — safe even if STRÅNG/sensor data is missing
        APERTURE = 12.35
        kt_current = None; dni_est_current = None; p_theoretical = None
        ETA_OPT = 0.65; merged = pd.DataFrame()
        eta_clear = pd.DataFrame(); eta_df = pd.DataFrame()
        eta_median = eta_p90 = eta_p95 = eta_max = None; n_pts = 0
        # System η (forward/return) — parallel calculation
        sys_clear = pd.DataFrame()
        sys_median = sys_p90 = sys_p95 = None; sys_pts = 0
        irr_live = df_cmp[df_cmp["sensor"]=="irradiance"].sort_values("created_at")
        pwr_live = df_cmp[df_cmp["sensor"]=="power"].sort_values("created_at")
        p_actual = float(pwr_live["value"].iloc[-1]) if not pwr_live.empty else None

        # Clip STRÅNG to selected date range
        df_st = pd.DataFrame()
        if not df_strang.empty:
            df_st = df_strang[
                (df_strang["created_at"] >= dt_from) &
                (df_strang["created_at"] <= dt_to)
            ].copy()

        # Use STRÅNG DNI directly — skip kt=DNI/GHI which breaks when GHI_STRÅNG≈0
        dni_strang_df = pd.DataFrame()
        if not df_st.empty:
            dni_rows = df_st[df_st["sensor"]=="dni_strang"][["created_at","value"]].copy()
            dni_rows = dni_rows.rename(columns={"value":"dni_strang"})
            dni_strang_df = dni_rows[dni_rows["dni_strang"] > 10].sort_values("created_at")

        if not dni_strang_df.empty and not irr_live.empty:
            last_ts    = irr_live["created_at"].iloc[-1]
            ghi_last   = float(irr_live["value"].iloc[-1])
            time_diffs = (dni_strang_df["created_at"] - last_ts).abs()
            best_mask  = time_diffs <= pd.Timedelta("3h")
            if best_mask.any():
                best_idx        = time_diffs[best_mask].idxmin()
                dni_est_current = float(dni_strang_df.loc[best_idx, "dni_strang"])
                kt_current      = (dni_est_current / ghi_last) if ghi_last > 20 else None

            pwr_df = pwr_live[["created_at","value"]].rename(columns={"value":"p_meas"})
        # Collector η: T_right (outlet) − T_left (inlet) × flow
        # Pure optical efficiency — no pipe/HX losses
        CP = 4186; RHO = 1000
        tr_df = df_cmp[df_cmp["sensor"]=="temp_right_coll"][["created_at","value"]].rename(columns={"value":"t_out"})
        tl_df = df_cmp[df_cmp["sensor"]=="temp_left_coll"][["created_at","value"]].rename(columns={"value":"t_in"})
        fl_df = df_cmp[df_cmp["sensor"]=="flow"][["created_at","value"]].rename(columns={"value":"flow"})

        if not tr_df.empty and not tl_df.empty and not fl_df.empty and not dni_strang_df.empty:
            eta_df = pd.merge_asof(tr_df.sort_values("created_at"),
                                   tl_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("2min"))
            eta_df = pd.merge_asof(eta_df.sort_values("created_at"),
                                   fl_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("2min"))
            eta_df = pd.merge_asof(eta_df.sort_values("created_at"),
                                   dni_strang_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("65min"),
                                   direction="nearest")
            eta_df = eta_df.dropna(subset=["t_out","t_in","flow","dni_strang"])
            if not eta_df.empty:
                eta_df["dT_coll"] = (eta_df["t_out"] - eta_df["t_in"]).abs()
                eta_df["p_coll"]  = eta_df["flow"] / 3600 * RHO * CP * eta_df["dT_coll"] / 1000
                eta_df = eta_df.sort_values("created_at")
                eta_df["dt_h"]   = eta_df["created_at"].diff().dt.total_seconds().fillna(0) / 3600
                eta_df["e_coll"] = eta_df["p_coll"]     * eta_df["dt_h"]
                eta_df["e_in"]   = eta_df["dni_strang"] * APERTURE / 1000 * eta_df["dt_h"]
                eta_df["strang_hour"] = eta_df["created_at"].dt.floor("1h")
                hourly_eta = eta_df.groupby("strang_hour").agg(
                    e_coll=("e_coll","sum"), e_in=("e_in","sum"),
                    dni_mean=("dni_strang","mean"),
                    p_mean=("p_coll","mean"),
                    flow_mean=("flow","mean"),
                    n=("flow","count")
                ).reset_index()
                hourly_eta = hourly_eta[
                    (hourly_eta["dni_mean"]  > 300) &
                    (hourly_eta["p_mean"]    > 0.5) &
                    (hourly_eta["flow_mean"] > 0.05) &
                    (hourly_eta["n"]         > 10)
                ].copy()
                hourly_eta["eta_h"] = hourly_eta["e_coll"] / \
                    hourly_eta["e_in"].replace(0, float("nan"))
                hourly_eta = hourly_eta[
                    (hourly_eta["eta_h"] >= 0.10) &
                    (hourly_eta["eta_h"] <= 0.90)
                ]
                if not hourly_eta.empty:
                    eta_df = eta_df.merge(
                        hourly_eta[["strang_hour","eta_h"]], on="strang_hour", how="inner")
                    eta_df["eta_raw"] = eta_df["eta_h"]
                    eta_df["ghi_s"]   = eta_df["dni_strang"]
                    eta_clear = eta_df[
                        (eta_df["flow"] > 0.05) & (eta_df["p_coll"] > 0.3)
                    ].copy()
        # Compute η statistics from qualifying samples
        if not eta_clear.empty:
            eta_median = float(eta_clear["eta_raw"].median())
            eta_p90    = float(eta_clear["eta_raw"].quantile(0.90))
            eta_p95    = float(eta_clear["eta_raw"].quantile(0.95))
            eta_max    = float(eta_clear["eta_raw"].max())
            n_pts      = len(eta_clear)
            ETA_OPT    = float(max(0.10, min(0.85, eta_p90)))
            p_theoretical = (dni_est_current * APERTURE * ETA_OPT) / 1000 \
                if dni_est_current is not None else None

        # ── System η: T_forward / T_return ────────────────────
        tf_df  = df_cmp[df_cmp["sensor"]=="temp_forward"][["created_at","value"]].rename(columns={"value":"t_fwd"})
        tr2_df = df_cmp[df_cmp["sensor"]=="temp_return"][["created_at","value"]].rename(columns={"value":"t_ret"})
        fl_df2 = df_cmp[df_cmp["sensor"]=="flow"][["created_at","value"]].rename(columns={"value":"flow"})

        if not tf_df.empty and not tr2_df.empty and not fl_df2.empty and not dni_strang_df.empty:
            sys_df = pd.merge_asof(tf_df.sort_values("created_at"),
                                   tr2_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("2min"))
            sys_df = pd.merge_asof(sys_df.sort_values("created_at"),
                                   fl_df2.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("2min"))
            sys_df = pd.merge_asof(sys_df.sort_values("created_at"),
                                   dni_strang_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("65min"),
                                   direction="nearest")
            sys_df = sys_df.dropna(subset=["t_fwd","t_ret","flow","dni_strang"])
            if not sys_df.empty:
                sys_df["dT_sys"] = (sys_df["t_fwd"] - sys_df["t_ret"]).abs()
                sys_df["p_sys"]  = sys_df["flow"] / 3600 * RHO * CP * sys_df["dT_sys"] / 1000
                sys_df = sys_df.sort_values("created_at")
                sys_df["dt_h"]  = sys_df["created_at"].diff().dt.total_seconds().fillna(0) / 3600
                sys_df["e_sys"] = sys_df["p_sys"]      * sys_df["dt_h"]
                sys_df["e_in"]  = sys_df["dni_strang"] * APERTURE / 1000 * sys_df["dt_h"]
                sys_df["strang_hour"] = sys_df["created_at"].dt.floor("1h")
                h_sys = sys_df.groupby("strang_hour").agg(
                    e_sys=("e_sys","sum"), e_in=("e_in","sum"),
                    dni_mean=("dni_strang","mean"),
                    p_mean=("p_sys","mean"), flow_mean=("flow","mean"),
                    n=("flow","count")
                ).reset_index()
                h_sys = h_sys[
                    (h_sys["dni_mean"]  > 300) & (h_sys["p_mean"]    > 0.5) &
                    (h_sys["flow_mean"] > 0.05) & (h_sys["n"]        > 10)
                ].copy()
                h_sys["eta_h"] = h_sys["e_sys"] / h_sys["e_in"].replace(0, float("nan"))
                h_sys = h_sys[(h_sys["eta_h"] >= 0.05) & (h_sys["eta_h"] <= 0.90)]
                if not h_sys.empty:
                    sys_df = sys_df.merge(h_sys[["strang_hour","eta_h"]], on="strang_hour", how="inner")
                    sys_df["eta_raw"] = sys_df["eta_h"]
                    sys_clear = sys_df[(sys_df["flow"] > 0.05) & (sys_df["p_sys"] > 0.3)].copy()

        if not sys_clear.empty:
            sys_median = float(sys_clear["eta_raw"].median())
            sys_p90    = float(sys_clear["eta_raw"].quantile(0.90))
            sys_p95    = float(sys_clear["eta_raw"].quantile(0.95))
            sys_pts    = len(sys_clear)
        # ── kt tiles ──────────────────────────────────────
        kt_color = TEAL if kt_current and kt_current > 0.6 else (AMBER if kt_current and kt_current > 0.3 else MUTED)
        efficiency_pct = (p_actual / p_theoretical * 100)                 if p_theoretical and p_theoretical > 0.1 and p_actual else None

        render_tiles([
            ("Clearness index kt",    kt_current,      "",     0, 1.2,  kt_color, 2, None),
            ("DNI estimated",         dni_est_current, "W/m²", 0, 1500, AMBER,    0, None),
            ("Theoretical max power", p_theoretical,   "kW",   0, 9.2,  RUST,     2, None),
            ("Actual power",          p_actual,        "kW",   0, 9.2,  TEAL,     2, None),
        ])
        # Show what data range was actually used
        if not df_st.empty and not df_cmp.empty:
            st_t0 = df_st["created_at"].min().astimezone(SWE).strftime("%b %d %H:%M")
            st_t1 = df_st["created_at"].max().astimezone(SWE).strftime("%b %d %H:%M")
            s_t0  = df_cmp["created_at"].min().astimezone(SWE).strftime("%b %d %H:%M")
            s_t1  = df_cmp["created_at"].max().astimezone(SWE).strftime("%b %d %H:%M")
            n_sensor = len(df_cmp[df_cmp["sensor"]=="irradiance"])
            n_strang = len(df_st)
            st.caption(f"Data used — sensor: {s_t0} → {s_t1} ({n_sensor} pts) · "
                       f"STRÅNG: {st_t0} → {st_t1} ({n_strang} pts)")
        if kt_current is None:
            st.caption("⚠ kt: no STRÅNG value within ±3h of latest sensor reading. "
                       "STRÅNG is hourly — analysis uses historical η from the window.")

        # ── Optical efficiency — headline + time series ────
        st.markdown('<div class="section-title">Optical efficiency η* over time</div>',
                    unsafe_allow_html=True)

        if eta_p90 is not None and n_pts > 5 or sys_p90 is not None and sys_pts > 5:
            ec1, ec2 = st.columns(2)

            # Collector η card
            with ec1:
                eta_color = TEAL if (eta_p90 or 0) > 0.62 else (AMBER if (eta_p90 or 0) > 0.45 else RUST)
                if eta_p90 is not None and n_pts > 5:
                    st.markdown(
                        f"<div style='background:{BG2};border-radius:8px;padding:12px 16px;"
                        f"border-left:3px solid {eta_color};height:100%'>"
                        f"<div style='font-size:.65rem;font-weight:600;color:{TEXT};"
                        f"text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px'>"
                        f"η Collector (T_right − T_left)*</div>"
                        f"<div style='font-size:2.2rem;font-weight:700;color:{eta_color}'>{eta_p90:.3f}"
                        f"<span style='font-size:.8rem;font-weight:400;color:{MUTED};margin-left:6px'>p90</span></div>"
                        f"<div style='font-size:.8rem;color:{MUTED};margin-top:2px'>"
                        f"median {eta_median:.3f} · p95 {eta_p95:.3f} · n={n_pts}h</div>"
                        f"<div style='font-size:.68rem;color:{MUTED};margin-top:4px;line-height:1.4'>"
                        f"* Pure optical η — collector in/out only</div>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    st.info("Collector η: insufficient data")

            # System η card
            with ec2:
                sys_color = TEAL if (sys_p90 or 0) > 0.55 else (AMBER if (sys_p90 or 0) > 0.35 else RUST)
                if sys_p90 is not None and sys_pts > 5:
                    st.markdown(
                        f"<div style='background:{BG2};border-radius:8px;padding:12px 16px;"
                        f"border-left:3px solid {sys_color};height:100%'>"
                        f"<div style='font-size:.65rem;font-weight:600;color:{TEXT};"
                        f"text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px'>"
                        f"η System (T_forward − T_return)**</div>"
                        f"<div style='font-size:2.2rem;font-weight:700;color:{sys_color}'>{sys_p90:.3f}"
                        f"<span style='font-size:.8rem;font-weight:400;color:{MUTED};margin-left:6px'>p90</span></div>"
                        f"<div style='font-size:.8rem;color:{MUTED};margin-top:2px'>"
                        f"median {sys_median:.3f} · p95 {sys_p95:.3f} · n={sys_pts}h</div>"
                        f"<div style='font-size:.68rem;color:{MUTED};margin-top:4px;line-height:1.4'>"
                        f"** Includes pipe & HX losses — lower than collector η</div>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    st.info("System η: insufficient data")

            st.caption(f"η = flow × ΔT × cp ÷ (DNI_STRÅNG × {APERTURE} m²) · "
                       f"Hourly integration · LC12 spec η_peak ≈ 0.72")

            # Time series chart of η per measurement point
            fig_eta = go.Figure()

            # All qualifying points as scatter
            fig_eta.add_trace(go.Scatter(
                x=eta_clear["created_at"], y=eta_clear["eta_raw"],
                name="η per sample",
                mode="markers",
                marker=dict(color=SLATE, size=4, opacity=0.5),
            ))

            # Rolling median (window=10 points) as smoothed line
            eta_sorted = eta_clear.sort_values("created_at")
            eta_rolling = eta_sorted["eta_raw"].rolling(10, min_periods=3, center=True).median()
            fig_eta.add_trace(go.Scatter(
                x=eta_sorted["created_at"], y=eta_rolling,
                name="Rolling median (10 pts)",
                mode="lines",
                line=dict(color=TEAL, width=2.5),
            ))

            # Reference lines
            fig_eta.add_hline(y=eta_p90, line_dash="dot", line_color=TEAL,
                annotation_text=f"p90 = {eta_p90:.3f}",
                annotation_position="right", annotation_font_size=11)
            fig_eta.add_hline(y=0.72, line_dash="dash", line_color=MUTED,
                annotation_text="LC12 spec 0.72",
                annotation_position="right", annotation_font_size=10)

            fig_eta.update_layout(
                height=280, margin=dict(l=0, r=80, t=10, b=0),
                yaxis=dict(title="η (–)", range=[0, 0.9],
                           gridcolor=BORDER, color=MUTED,
                           tickformat=".2f"),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            font=dict(size=10, color=MUTED, family="Inter")),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=MUTED, family="Inter"))
            fig_eta.update_xaxes(showgrid=False, color=MUTED)
            st.plotly_chart(fig_eta, use_container_width=True,
                config={"scrollZoom": True, "displayModeBar": True,
                        "modeBarButtonsToRemove": ["select2d","lasso2d","autoScale2d"]})
            # System η scatter overlay
            if not sys_clear.empty:
                sys_sorted  = sys_clear.sort_values("created_at")
                sys_rolling = sys_sorted["eta_raw"].rolling(10, min_periods=3, center=True).median()
                fig_eta.add_trace(go.Scatter(
                    x=sys_sorted["created_at"], y=sys_sorted["eta_raw"],
                    name="η system (fwd/ret)",
                    mode="markers",
                    marker=dict(color=AMBER, size=4, opacity=0.4)))
                fig_eta.add_trace(go.Scatter(
                    x=sys_sorted["created_at"], y=sys_rolling,
                    name="System rolling median",
                    mode="lines",
                    line=dict(color=AMBER, width=2, dash="dash")))

            st.caption("Teal = collector η (T_right/T_left) · Amber dashed = system η (forward/return) · "
                       "Gap between the two = pipe and heat exchanger losses.")

        else:
            # Debug info — show why no samples qualified
            n_total   = len(eta_df) if not eta_df.empty else 0
            n_day     = len(eta_df[eta_df["ghi_s"] > 400]) if not eta_df.empty else 0
            n_running = len(eta_df[(eta_df["ghi_s"] > 400) & (eta_df["p_meas"] > 1.0)])                             if not eta_df.empty else 0
            st.info(f"Optical efficiency: insufficient qualifying samples. "
                    f"Overlap rows: {n_total} · GHI>400: {n_day} · GHI>400 & P>1kW: {n_running}. "
                    f"Select a window with clear sun and system running.")

        if efficiency_pct is not None:
            eff_color = TEAL if efficiency_pct > 75 else (AMBER if efficiency_pct > 40 else RUST)
            st.markdown(
                f"<div style='margin:8px 0 4px;font-size:.9rem;color:{TEXT}'>"
                f"Instantaneous system performance: <b style='color:{eff_color}'>{efficiency_pct:.0f}%</b> "
                f"of theoretical maximum"
                f"<span style='font-size:.75rem;color:{MUTED};margin-left:8px'>"
                f"({fmt(p_actual,2,'kW')} measured vs {fmt(p_theoretical,2,'kW')} theoretical)</span>"
                f"</div>",
                unsafe_allow_html=True
            )

        # ── Graf: GHI sensor vs STRÅNG GHI + DNI ──────────────────
        # ── Single combined chart: GHI sensor + DNI STRÅNG + Power + η ──
        st.markdown('<div class="section-title">Irradiance, power & optical efficiency — combined view</div>',
                    unsafe_allow_html=True)
        st.caption("Only periods with GHI > 100 W/m² or Power > 0.5 kW shown. "
                   "DNI from STRÅNG model (hourly). η = P / (DNI × 12.35 m²).")

        # Build combined dataframe: sensor irradiance + power + STRÅNG DNI
        irr_all = df_cmp[df_cmp["sensor"]=="irradiance"][["created_at","value"]].rename(columns={"value":"ghi"})
        pwr_all = df_cmp[df_cmp["sensor"]=="power"][["created_at","value"]].rename(columns={"value":"power"})

        if not irr_all.empty and not pwr_all.empty:
            combo = pd.merge_asof(irr_all.sort_values("created_at"),
                                  pwr_all.sort_values("created_at"),
                                  on="created_at", tolerance=pd.Timedelta("5min"))
            if not dni_strang_df.empty:
                combo = pd.merge_asof(combo.sort_values("created_at"),
                                      dni_strang_df.sort_values("created_at"),
                                      on="created_at", tolerance=pd.Timedelta("65min"),
                                      direction="nearest")
            else:
                combo["dni_strang"] = None

            # Filter: only show where sun is up or system running
            mask = (combo["ghi"] > 100) | (combo["power"] > 0.5)
            combo = combo[mask].copy()

            # Compute η per point where DNI available and meaningful
            if "dni_strang" in combo.columns:
                denom = (combo["dni_strang"] * 12.35 / 1000).replace(0, float("nan"))
                combo["eta_pt"] = (combo["power"] / denom).where(
                    (combo["dni_strang"] > 200) & (combo["power"] > 0.5))
                combo.loc[combo["eta_pt"] > 0.95, "eta_pt"] = float("nan")  # clip outliers

            if not combo.empty:
                fig_combo = go.Figure()

                # Left axis: irradiance W/m²
                fig_combo.add_trace(go.Scatter(
                    x=combo["created_at"], y=combo["ghi"],
                    name="GHI sensor (W/m²)", mode="lines",
                    line=dict(color=AMBER, width=2), yaxis="y"))

                if "dni_strang" in combo.columns:
                    fig_combo.add_trace(go.Scatter(
                        x=combo["created_at"], y=combo["dni_strang"],
                        name="DNI STRÅNG (W/m²)", mode="lines",
                        line=dict(color=RUST, width=1.5, dash="dash"), yaxis="y"))

                # Right axis: power kW
                fig_combo.add_trace(go.Scatter(
                    x=combo["created_at"], y=combo["power"],
                    name="Thermal power (kW)", mode="lines",
                    line=dict(color=TEAL, width=2.5), yaxis="y2"))

                # Right axis: η (0–1) — also on y2 scaled 0–10 to align with kW
                if "eta_pt" in combo.columns:
                    fig_combo.add_trace(go.Scatter(
                        x=combo["created_at"],
                        y=combo["eta_pt"] * 10,  # scale: η×10 so 0.65 → 6.5 kW-equiv
                        name="η × 10 (right axis)", mode="markers",
                        marker=dict(color=BLUE, size=3, opacity=0.6), yaxis="y2"))

                _eta_disp = f"η_p90 = {eta_p90:.3f}" if eta_p90 else "η not yet computed"
                fig_combo.update_layout(
                    height=380, margin=dict(l=0, r=60, t=10, b=0),
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    yaxis=dict(title=dict(text="W/m²", font=dict(color=AMBER)),
                               tickfont=dict(color=AMBER), gridcolor=BORDER, rangemode="tozero"),
                    yaxis2=dict(title=dict(text="kW  |  η×10", font=dict(color=TEAL)),
                                tickfont=dict(color=TEAL), overlaying="y", side="right",
                                showgrid=False, rangemode="tozero"),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"),
                    annotations=[dict(
                        text=_eta_disp, x=1, y=1.08, xref="paper", yref="paper",
                        showarrow=False, font=dict(size=11, color=TEAL)
                    )]
                )
                fig_combo.update_xaxes(showgrid=False, color=MUTED)
                st.plotly_chart(fig_combo, use_container_width=True,
                    config={"scrollZoom":True,"displayModeBar":True,
                            "modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"]})
                st.caption("η×10 plotted on power axis so 0.65 → 6.5 on right scale. "
                           "Gap between DNI-based theoretical and actual power = system losses.")

        # ── kt-tidsserie ──────────────────────────────────────────
        if not df_st.empty and not dni_strang_df.empty:
            st.markdown('<div class="section-title">Clearness index kt over time</div>',
                        unsafe_allow_html=True)
            # Compute kt = DNI_STRÅNG / GHI_sensor — only when sun is clearly up
            # Filter GHI > 150 to avoid division noise at dawn/dusk
            kt_combo = pd.merge_asof(
                irr_all[irr_all["ghi"] > 150].sort_values("created_at"),
                dni_strang_df.sort_values("created_at"),
                on="created_at", tolerance=pd.Timedelta("65min"), direction="nearest")
            kt_combo = kt_combo.dropna()
            # kt physically 0–1.5 max; clip and filter outliers
            kt_combo["kt"] = kt_combo["dni_strang"] / kt_combo["ghi"]
            kt_combo = kt_combo[(kt_combo["kt"] >= 0) & (kt_combo["kt"] <= 1.5)]
            fig_kt = go.Figure()
            fig_kt.add_trace(go.Scatter(
                x=kt_combo["created_at"], y=kt_combo["kt"],
                name="kt = DNI_STRÅNG / GHI_sensor", mode="lines",
                line=dict(color=TEAL, width=2),
                fill="tozeroy", fillcolor="rgba(22,122,94,0.1)"))
            fig_kt.add_hline(y=0.7, line_dash="dot", line_color=AMBER,
                             annotation_text="Clear sky (kt=0.7)")
            fig_kt.update_layout(
                height=200, margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(title="kt", range=[0, 1.5], gridcolor=BORDER, color=MUTED),
                hovermode="x unified",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=MUTED, family="Inter"))
            fig_kt.update_xaxes(showgrid=False, color=MUTED)
            st.plotly_chart(fig_kt, use_container_width=True, config={"scrollZoom":True,"displayModeBar":True,"modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"]})
            st.caption("kt > 0.7 = clear sky, direct sunlight optimal for concentrating systems. "
                       "kt < 0.3 = heavy cloud cover, DNI too low for meaningful CSP output.")

# ── Om systemet tab ──────────────────────────────────────────
with tab_om:
    c_sys, c_map = st.columns([1, 1])
    with c_sys:
        st.markdown(f"<div class='section-title'>Systemspecifikation</div>",
                    unsafe_allow_html=True)
        st.markdown(f"""<div style='font-size:.85rem;color:{MUTED};line-height:2.1'>
<b style='color:{TEXT}'>Helixis LC12 HW</b><br>
Linear Concentrator — CSP<br>
Aperture: 12.35 m² · 380 kg<br>
Peak output: 9.2 kW @ 1000 W/m²<br>
Max temp: 160°C · Max pressure: 6 bar
</div>""", unsafe_allow_html=True)

        st.markdown(f"<div class='section-title' style='margin-top:24px'>Geografisk placering</div>",
                    unsafe_allow_html=True)
        st.markdown(f"""<div style='font-size:.85rem;color:{MUTED};line-height:2.1'>
<b style='color:{TEXT}'>Eket, Örkelljunga</b><br>
Koordinater: 56.248°N · 13.192°E<br>
Höjd ö.h.: ~130 m<br>
Region: Skåne
</div>""", unsafe_allow_html=True)

    with c_map:
        st.markdown(f"<div class='section-title'>Flygfoto — Eket</div>",
                    unsafe_allow_html=True)
        if os.path.exists("eket_aerial.png"):
            st.image("eket_aerial.png", caption="Eket, Örkelljunga · © Google Maps",
                     use_container_width=True)
        else:
            st.info("Lägg till eket_aerial.png i repot för att visa flygfoto.")

# ── Sidebar (minimal) ─────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='color:{TEXT};font-weight:600;font-size:.9rem;margin-bottom:8px'>Helixis LC12</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:.72rem;color:{MUTED}'>Eket · Örkelljunga · 56.248°N</div>",
                unsafe_allow_html=True)