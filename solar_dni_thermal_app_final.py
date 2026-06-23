
import streamlit as st
import pandas as pd
import numpy as np
import math
import requests
import io
import os
from datetime import datetime, timedelta, date
from report_generator import generate_report

st.set_page_config(layout="wide")

# -------------------------------------------------
# Spot Price Constants & Helpers
# -------------------------------------------------

ENTSOE_API_KEY = "55dfa98f-792a-45fd-8170-89febe6fdbaa"

def _add_spot_log(msg):
    if "spot_log" not in st.session_state:
        st.session_state["spot_log"] = []
    st.session_state["spot_log"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def fetch_spotprices_entsoe(api_key: str, area: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch spot prices from ENTSO-E Transparency Platform."""
    import time
    if not api_key:
        api_key = ENTSOE_API_KEY
    try:
        from entsoe import EntsoePandasClient
    except ImportError:
        raise ImportError("entsoe-py not installed.")
    area_codes = {'SE1': 'SE_1', 'SE2': 'SE_2', 'SE3': 'SE_3', 'SE4': 'SE_4'}
    if area not in area_codes:
        raise ValueError(f"Invalid area: {area}")
    client = EntsoePandasClient(api_key=api_key)
    start = pd.Timestamp(start_date, tz='Europe/Stockholm')
    end   = pd.Timestamp(end_date,   tz='Europe/Stockholm') + pd.Timedelta(days=1)

    # Retry up to 3 times with backoff — ENTSO-E occasionally returns 503
    last_err = None
    for attempt in range(3):
        try:
            prices = client.query_day_ahead_prices(area_codes[area], start=start, end=end)
            break
        except Exception as e:
            last_err = e
            if "503" in str(e) or "502" in str(e) or "504" in str(e):
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
            raise RuntimeError(
                f"ENTSO-E API error: {e}  \n\n"
                "**Tip:** ENTSO-E occasionally goes down for maintenance. "
                "Wait a minute and try again, or upload the `spotpriser_2023_2026.csv` "
                "file from the battery simulation app instead."
            )
    else:
        raise RuntimeError(
            f"ENTSO-E returned a server error after 3 attempts: {last_err}  \n\n"
            "The ENTSO-E Transparency Platform appears to be temporarily unavailable. "
            "Please try again in a few minutes, or upload the `spotpriser_2023_2026.csv` file instead."
        )

    df = prices.reset_index()
    df.columns = ['Tid', 'spotpris_eur_mwh']
    try:
        r = requests.get(
            f"https://api.riksbank.se/swea/v1/CrossRates/SEKEURPMI/{start_date}/{end_date}",
            timeout=15
        )
        if r.status_code == 200:
            rate_map = {pd.Timestamp(d['date']).date(): float(d['value']) for d in r.json()}
            df['EUR_SEK'] = df['Tid'].dt.date.map(rate_map)
            df['EUR_SEK'] = df['EUR_SEK'].ffill().bfill()
        else:
            df['EUR_SEK'] = 11.20
    except Exception:
        df['EUR_SEK'] = 11.20
    df['spotpris'] = df['spotpris_eur_mwh'] * df['EUR_SEK'] / 1000
    df['Tid'] = df['Tid'].dt.tz_localize(None)
    return df[['Tid', 'spotpris']].copy()


def _extend_spot_with_live_data(spot_df_full: pd.DataFrame) -> pd.DataFrame:
    """Extend spot data with live ENTSO-E data up to today/tomorrow."""
    now    = datetime.now()
    today  = now.date()
    target = today + timedelta(days=1) if now.hour >= 13 else today
    actual_last = spot_df_full['Tid'].max().date()
    if st.session_state.get('spot_live_extended_to') == str(target) and actual_last >= target:
        return spot_df_full
    if actual_last >= target:
        st.session_state['spot_live_extended_to'] = str(target)
        return spot_df_full
    fetch_from = actual_last + timedelta(days=1)
    fetch_to   = target
    _add_spot_log(f"Fetching missing spot prices {fetch_from} to {fetch_to} via ENTSO-E...")
    last_rate = float(spot_df_full['EUR_SEK'].iloc[-1]) if 'EUR_SEK' in spot_df_full.columns else 11.20
    fx_series = {}
    try:
        fx_resp = requests.get(
            f"https://api.frankfurter.app/{fetch_from}..{fetch_to}?from=EUR&to=SEK", timeout=15
        )
        fx_resp.raise_for_status()
        fx_rates = fx_resp.json().get("rates", {})
        d = fetch_from
        while d <= fetch_to:
            if str(d) in fx_rates:
                last_rate = fx_rates[str(d)].get('SEK', last_rate)
            fx_series[d] = last_rate
            d += timedelta(days=1)
    except Exception:
        d = fetch_from
        while d <= fetch_to:
            fx_series[d] = last_rate
            d += timedelta(days=1)
    try:
        from entsoe import EntsoePandasClient
        import pytz
        tz_se = pytz.timezone("Europe/Stockholm")
        client = EntsoePandasClient(api_key=ENTSOE_API_KEY)
        _start_ts = pd.Timestamp(str(fetch_from), tz=tz_se)
        _end_ts   = pd.Timestamp(str(fetch_to) + " 23:59", tz=tz_se)
        _area_codes = {
            "SE1": "10Y1001A1001A44P", "SE2": "10Y1001A1001A45N",
            "SE3": "10Y1001A1001A46L", "SE4": "10Y1001A1001A47J"
        }
        new_rows_list = []
        for a, bid_zone in _area_codes.items():
            try:
                prices = client.query_day_ahead_prices(bid_zone, start=_start_ts, end=_end_ts)
                prices = prices.tz_convert(tz_se).tz_localize(None)
                prices = prices[prices.index > spot_df_full['Tid'].max()]
                for ts, eur_mwh in prices.items():
                    fx   = fx_series.get(ts.date(), last_rate)
                    kr   = round(eur_mwh * fx / 1000.0, 4)
                    new_rows_list.append({'Tid': ts, 'area': a, 'kr_kwh': kr,
                                          'ore_kwh': round(kr * 100, 2), 'EUR_SEK': fx})
            except Exception:
                pass
        if not new_rows_list:
            st.session_state['spot_live_fetch_error'] = f"ENTSO-E returned no rows for {fetch_from}–{fetch_to}"
            return spot_df_full
        _df = pd.DataFrame(new_rows_list)
        pivot = _df.pivot_table(index='Tid', columns='area', values=['kr_kwh','ore_kwh'], aggfunc='first')
        pivot.columns = [f"{a}_{m}" for m, a in pivot.columns]
        pivot = pivot.reset_index()
        pivot['EUR_SEK'] = pivot['Tid'].apply(lambda t: fx_series.get(t.date(), last_rate))
        col_order = ['Tid','SE1_ore_kwh','SE1_kr_kwh','SE2_ore_kwh','SE2_kr_kwh',
                     'SE3_ore_kwh','SE3_kr_kwh','SE4_ore_kwh','SE4_kr_kwh','EUR_SEK']
        for c in col_order:
            if c not in pivot.columns:
                pivot[c] = float('nan')
        new_rows = pivot[col_order]
        extended = pd.concat([spot_df_full, new_rows], ignore_index=True).sort_values('Tid').reset_index(drop=True)
        _add_spot_log(f"ENTSO-E: added {len(new_rows)} hours. Now covers up to {extended['Tid'].max().date()}.")
        st.session_state['spot_live_extended_to'] = str(target)
        st.session_state.pop('spot_live_fetch_error', None)
        return extended
    except Exception as e:
        st.session_state['spot_live_fetch_error'] = f"ENTSO-E error: {e}"
        return spot_df_full


def _load_preinstalled_spotprices(area: str, start_date, end_date, force_reload: bool = False):
    """Load spot price data from session cache, then filter to area/dates."""
    full_cache_key = 'spot_full_extended'
    if force_reload:
        st.session_state.pop(full_cache_key, None)

    spot_df_full = st.session_state.get(full_cache_key)
    if spot_df_full is None:
        # No data in cache — nothing to return; user must upload or fetch via ENTSO-E
        st.session_state['spot_load_error'] = (
            "No spot price data loaded yet. "
            "Upload the `spotpriser_2023_2026.csv` file or fetch directly from ENTSO-E below."
        )
        return None

    st.session_state.pop('spot_load_error', None)
    spot_df_full = _extend_spot_with_live_data(spot_df_full)
    st.session_state[full_cache_key] = spot_df_full

    price_col = f"{area}_kr_kwh"
    if price_col not in spot_df_full.columns:
        price_col_ore = f"{area}_ore_kwh"
        if price_col_ore in spot_df_full.columns:
            spot_df_full[price_col] = spot_df_full[price_col_ore] / 100
        else:
            return None
    if 'EUR_SEK' in spot_df_full.columns:
        st.session_state['spot_eur_sek_rate'] = spot_df_full['EUR_SEK'].mean()
    spot_df = spot_df_full[['Tid', price_col]].copy()
    spot_df.columns = ['Tid', 'spotpris']
    spot_df = spot_df[
        (spot_df['Tid'].dt.date >= start_date) &
        (spot_df['Tid'].dt.date <= end_date)
    ]
    return spot_df if not spot_df.empty else None


def _ingest_spot_csv(uploaded_file) -> pd.DataFrame:
    """Parse an uploaded spot price CSV (same format as spotpriser_2023_2026.csv)."""
    df = pd.read_csv(uploaded_file, sep=',', decimal='.', parse_dates=['Tid'])
    return df
    spot_df.columns = ['Tid', 'spotpris']
    spot_df = spot_df[
        (spot_df['Tid'].dt.date >= start_date) &
        (spot_df['Tid'].dt.date <= end_date)
    ]
    return spot_df if not spot_df.empty else None

# -------------------------------------------------
# Authentication
# -------------------------------------------------

def check_password():
    """
    Password authentication for the app.
    Returns True if correct password, otherwise False.
    """
    
    def password_entered():
        """Checks if entered password is correct."""
        username = st.session_state.get("username", "")
        password = st.session_state.get("password", "")
        
        # Check if secrets exist
        if "passwords" not in st.secrets:
            st.session_state["password_correct"] = True
            st.session_state["current_user"] = "demo"
            return
        
        # Check username and password
        if username in st.secrets["passwords"]:
            if password == st.secrets["passwords"][username]:
                st.session_state["password_correct"] = True
                st.session_state["current_user"] = username
                # Remove password from session state
                if "password" in st.session_state:
                    del st.session_state["password"]
                if "username" in st.session_state:
                    del st.session_state["username"]
            else:
                st.session_state["password_correct"] = False
        else:
            st.session_state["password_correct"] = False
    
    # First run - show login
    if "password_correct" not in st.session_state:
        st.markdown("## 🔐 Login - Helixis Solar Calculator")
        st.markdown("Enter your credentials to continue.")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input("Username", key="username", placeholder="Enter username")
            st.text_input("Password", type="password", key="password", placeholder="Enter password")
            st.button("🔓 Login", on_click=password_entered, type="primary", use_container_width=True)
        
        st.markdown("---")
        st.info("💡 **Demo mode**: If no passwords are configured, you can access the system directly.")
        return False
    
    # Incorrect password
    elif not st.session_state["password_correct"]:
        st.markdown("## 🔐 Login - Helixis Solar Calculator")
        st.markdown("Enter your credentials to continue.")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input("Username", key="username", placeholder="Enter username")
            st.text_input("Password", type="password", key="password", placeholder="Enter password")
            st.button("🔓 Login", on_click=password_entered, type="primary", use_container_width=True)
            st.error("❌ Incorrect username or password")
        return False
    
    # Correct password
    else:
        return True


# -------------------------------------------------
# Constants
# -------------------------------------------------

DAYS_IN_MONTH = {
    "Jan": 31, "Feb": 28, "Mar": 31, "Apr": 30,
    "May": 31, "Jun": 30, "Jul": 31, "Aug": 31,
    "Sep": 30, "Oct": 31, "Nov": 30, "Dec": 31,
}

MONTHS = list(DAYS_IN_MONTH.keys())

# Active mirror (aperture) areas per concentrator model
APERTURE_10 = 10.0   # LC10  (active mirror area 10 m²)
APERTURE_20 = 20.0   # LC20  (active mirror area 20 m²)
DESIGN_DNI_W_M2 = 1000.0

# -------------------------------------------------
# Excel Parsing
# -------------------------------------------------

def parse_hourly_profiles(xls_file):
    df = pd.read_excel(xls_file, sheet_name="Hourly_profiles", header=None)
    months = list(df.iloc[4, 1:13])
    hours = df.iloc[5:29, 0].tolist()
    values_24x12 = df.iloc[5:29, 1:13].astype(float)
    values_24x12.index = hours
    values_24x12.columns = months
    sum_daily = df.loc[df.iloc[:, 0] == "Sum"].iloc[0, 1:13].astype(float)
    sum_daily.index = months
    return values_24x12, sum_daily

# -------------------------------------------------
# Energy Calculations
# -------------------------------------------------

def compute_energy_from_profiles(sum_daily_wh):
    monthly_kwh_m2 = {
        m: (daily_wh / 1000.0) * DAYS_IN_MONTH[m]
        for m, daily_wh in sum_daily_wh.items()
    }
    monthly_kwh_m2 = pd.Series(monthly_kwh_m2)
    return monthly_kwh_m2, monthly_kwh_m2.sum()


def compute_thermal_outputs(
    hour_matrix_wh,
    monthly_kwh_m2,
    annual_kwh_m2,
    mirror_area_m2,
    eta_opt,
    thermal_loss_frac
):
    solar_factor = eta_opt
    loop_factor = (1 - thermal_loss_frac)

    hourly_direct_kw = hour_matrix_wh / 1000.0 * mirror_area_m2 * solar_factor
    hourly_system_kw = hourly_direct_kw * loop_factor

    daily_direct_kwh = hour_matrix_wh.sum(axis=0) / 1000.0 * mirror_area_m2 * solar_factor
    daily_system_kwh = daily_direct_kwh * loop_factor

    monthly_direct_kwh = monthly_kwh_m2 * mirror_area_m2 * solar_factor
    monthly_system_kwh = monthly_direct_kwh * loop_factor

    annual_direct_kwh = annual_kwh_m2 * mirror_area_m2 * solar_factor
    annual_system_kwh = annual_direct_kwh * loop_factor

    return (
        annual_direct_kwh,
        annual_system_kwh,
        monthly_direct_kwh,
        monthly_system_kwh,
        hourly_direct_kw,
        hourly_system_kw,
        daily_direct_kwh,
        daily_system_kwh,
    )

# -------------------------------------------------
# Streamlit App
# -------------------------------------------------

# Check password before showing app
if not check_password():
    st.stop()

# Show user info in sidebar
st.sidebar.success(f"✅ Logged in as: **{st.session_state['current_user']}**")

if st.sidebar.button("🚪 Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

st.sidebar.markdown("---")

st.title("Helixis Solar Concentrator Thermal Production Estimate")

uploaded = st.file_uploader(
    "📥 Upload Excel file from GlobalSolarAtlas/Energydata.info",
    type=["xlsx"]
)

with st.sidebar:
    st.header("⚙️ System Sizing Parameters")
    base_mode = st.radio(
        "Base of calculation:",
        [
            "Peak thermal power (kW)",
            "Mirror surface (m²)",
            "Number of LC10 units",
            "Number of LC20 units",
            "Mix of units",
        ]
    )

if uploaded is not None:
    hour_matrix_wh, sum_daily_wh = parse_hourly_profiles(uploaded)
    monthly_kwh_m2, annual_kwh_m2 = compute_energy_from_profiles(sum_daily_wh)

    with st.sidebar:
        eta_opt_pct = st.slider("Optical efficiency [%]", 0, 100, 75)
        thermal_loss_pct = st.slider("Thermal losses in primary loop [%]", 0, 100, 0)

        eta_opt = eta_opt_pct / 100.0
        thermal_loss_frac = thermal_loss_pct / 100.0

        peak_dni_wh = hour_matrix_wh.max().max()
        peak_kw_per_m2 = peak_dni_wh / 1000.0 * eta_opt

        st.subheader("Sizing Input")

        n10 = 0
        n20 = 0

        if base_mode == "Peak thermal power (kW)":
            target_peak_kw = st.number_input("Target peak power [kW]", min_value=0.1, value=100.0)
            mirror_area = target_peak_kw / peak_kw_per_m2

        elif base_mode == "Mirror surface (m²)":
            mirror_area = st.number_input("Mirror area [m²]", min_value=1.0, value=APERTURE_20)
            target_peak_kw = mirror_area * peak_kw_per_m2

        elif base_mode == "Number of LC10 units":
            n10 = st.number_input("Number of LC10 units", min_value=0, value=1)
            mirror_area = n10 * APERTURE_10
            target_peak_kw = mirror_area * peak_kw_per_m2

        elif base_mode == "Number of LC20 units":
            n20 = st.number_input("Number of LC20 units", min_value=0, value=1)
            mirror_area = n20 * APERTURE_20
            target_peak_kw = mirror_area * peak_kw_per_m2

        elif base_mode == "Mix of units":
            n10 = st.number_input("Number of LC10 units", min_value=0, value=0)
            n20 = st.number_input("Number of LC20 units", min_value=0, value=1)
            mirror_area = n10 * APERTURE_10 + n20 * APERTURE_20
            target_peak_kw = mirror_area * peak_kw_per_m2

        needed_10_round = math.ceil(mirror_area / APERTURE_10)
        needed_20_round = math.ceil(mirror_area / APERTURE_20)

        design_peak_kw = mirror_area * (DESIGN_DNI_W_M2 / 1000.0) * eta_opt

        st.subheader("Calculated values")
        st.metric("Mirror area [m²]", f"{mirror_area:,.2f}")
        st.metric("Peak thermal power (from DNI) [kW]", f"{target_peak_kw:,.2f}")
        st.metric("Peak thermal power @ 1000 W/m² [kW]", f"{design_peak_kw:,.2f}")

        st.header("💰 Economic Parameters")

        price_per_kwh = st.number_input("Value of thermal energy [€/kWh]", min_value=0.0, value=0.10)

        item_cost_per_unit = st.number_input("Product cost [€ / unit]", min_value=0.0, value=15000.0)
        installation_cost = st.number_input("Estimated installation cost [€]", min_value=0.0, value=20000.0)

        # Calculate actual number of units based on sizing mode
        if base_mode == "Number of LC10 units":
            actual_n10 = n10
            actual_n20 = 0
            total_units = n10
        elif base_mode == "Number of LC20 units":
            actual_n10 = 0
            actual_n20 = n20
            total_units = n20
        elif base_mode == "Mix of units":
            actual_n10 = n10
            actual_n20 = n20
            total_units = n10 + n20
        else:
            # Peak power or Mirror surface → default to LC20 units
            actual_n10 = 0
            actual_n20 = needed_20_round
            total_units = needed_20_round

        total_product_cost = total_units * item_cost_per_unit
        system_cost = total_product_cost + installation_cost

        # LCOE lifetime input (calculation done after energy computation)
        system_lifetime_years = st.number_input("System lifetime [years]", min_value=1, value=25)

        st.metric("Total product cost [€]", f"{total_product_cost:,.0f}")
        st.metric("Total system cost [€]", f"{system_cost:,.0f}")

    (
        annual_direct_kwh,
        annual_system_kwh,
        monthly_direct_kwh,
        monthly_system_kwh,
        hourly_direct_kw,
        hourly_system_kw,
        daily_direct_kwh,
        daily_system_kwh,
    ) = compute_thermal_outputs(
        hour_matrix_wh,
        monthly_kwh_m2,
        annual_kwh_m2,
        mirror_area,
        eta_opt,
        thermal_loss_frac
    )

    # ========================================
    # LCOE CALCULATION
    # ========================================
    lifetime_energy = annual_system_kwh * system_lifetime_years if annual_system_kwh > 0 else 1
    lcoe = system_cost / lifetime_energy if lifetime_energy > 0 else float("inf")

    # ========================================
    # SUMMARY SECTION (Always visible at top)
    # ========================================
    
    st.markdown("---")
    st.subheader("📊 Summary Results")
    
    annual_value = annual_system_kwh * price_per_kwh
    payback_years = system_cost / annual_value if annual_value > 0 else float("inf")

    col1, col2, col3 = st.columns(3)
    with col1:
        if annual_system_kwh >= 10000:
            st.metric("Annual Energy [MWh/yr]", f"{annual_system_kwh/1000:,.1f}")
        else:
            st.metric("Annual Energy [kWh/yr]", f"{annual_system_kwh:,.0f}")
    with col2:
        st.metric("Annual Value [€/yr]", f"{annual_value:,.0f}")
    with col3:
        st.metric("Payback [yr]", f"{payback_years:.1f}")

    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric("LCOE [€/kWh]", f"{lcoe:.4f}")
    with col5:
        st.metric("System Cost [€]", f"{system_cost:,.0f}")
    with col6:
        st.metric("Total Units", f"{total_units}")
    
    # ========================================
    # DETAILED RESULTS IN TABS
    # ========================================
    
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "📈 Summary Report",
        "🔥 Hourly Profiles", 
        "📆 Monthly Data",
        "📊 Input DNI Data",
        "💾 Export",
        "🌾 Grain Drying",
        "⚡ Spot Prices",
        "📐 Field Layout"
    ])
    
    # ========================================
    # TAB 1: SUMMARY REPORT (Screenshot-friendly)
    # ========================================
    
    with tab1:
        st.markdown("### 📋 Complete System Summary")
        st.markdown("*Perfect for screenshots and reports*")
        
        # System Configuration
        st.markdown("#### ⚙️ System Configuration")
        col1, col2 = st.columns(2)
        
        with col1:
            unit_lines = f"            - Mirror area: {mirror_area:.2f} m²\n"
            if actual_n10 > 0:
                unit_lines += f"            - LC10 units: {actual_n10} pcs\n"
            if actual_n20 > 0:
                unit_lines += f"            - LC20 units: {actual_n20} pcs\n"
            unit_lines += f"            - Peak thermal power @ 1000 W/m²: {design_peak_kw:.1f} kW"
            st.markdown(f"""
            **Mirror Configuration:**
{unit_lines}
            """)
        
        with col2:
            st.markdown(f"""
            **Performance Parameters:**
            - Optical efficiency: {eta_opt_pct}%
            - Thermal losses: {thermal_loss_pct}%
            - Peak DNI: {hour_matrix_wh.max().max():.0f} W/m²
            - Peak thermal power (from DNI): {target_peak_kw:.1f} kW
            """)
        
        # Energy Production
        st.markdown("#### 🔥 Energy Production")
        energy_df = pd.DataFrame({
            "Month": monthly_direct_kwh.index,
            "Direct [kWh]": monthly_direct_kwh.values.round(0),
            "System [kWh]": monthly_system_kwh.values.round(0)
        })
        st.dataframe(energy_df, use_container_width=True, hide_index=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("**Annual Direct Energy**", f"{annual_direct_kwh:,.0f} kWh/year")
        with col2:
            st.metric("**Annual System Energy**", f"{annual_system_kwh:,.0f} kWh/year")
        
        # Economics
        st.markdown("#### 💰 Economic Analysis")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
            **Costs:**
            - Product cost: {total_product_cost:,.0f} €
            - Installation: {installation_cost:,.0f} €
            - **Total system cost: {system_cost:,.0f} €**
            """)
        
        with col2:
            st.markdown(f"""
            **Revenue:**
            - Energy price: {price_per_kwh:.2f} €/kWh
            - Annual production: {annual_system_kwh:,.0f} kWh
            - **Annual value: {annual_value:,.0f} €**
            """)
        
        with col3:
            st.markdown(f"""
            **Return on Investment:**
            - Payback period: **{payback_years:.1f} years**
            - LCOE ({system_lifetime_years} yr): **{lcoe:.4f} €/kWh**
            - Annual ROI: **{(annual_value/system_cost*100):.1f}%**
            - {system_lifetime_years}-year value: **{(annual_value*system_lifetime_years):,.0f} €**
            """)
    
    # ========================================
    # TAB 2: HOURLY PROFILES
    # ========================================
    
    with tab2:
        st.markdown("### 🔥 Hourly Thermal Power Profiles")
        
        # Direct Power Profile
        st.markdown("#### Direct Power into Media [kW_th]")
        st.dataframe(
            hourly_direct_kw.style
            .format("{:.1f}")
            .set_properties(**{"line-height": "0.5rem", "padding": "2px", "font-size": "11px"})
            .background_gradient(cmap="YlOrRd", axis=0),
            use_container_width=True,
            height=(len(hourly_direct_kw) + 1) * 35 + 3
        )
        
        # System Power Profile (if losses exist)
        if thermal_loss_frac > 0:
            st.markdown("#### System Power after Loop [kW_th]")
            st.dataframe(
                hourly_system_kw.style
                .format("{:.1f}")
                .set_properties(**{"line-height": "0.5rem", "padding": "2px", "font-size": "11px"})
                .background_gradient(cmap="YlOrRd", axis=0),
                use_container_width=True,
                height=(len(hourly_system_kw) + 1) * 35 + 3
            )
        
        # Daily Summary
        st.markdown("#### 📊 Daily Energy Totals [kWh/day]")
        daily_df = pd.DataFrame({
            "Month": daily_direct_kwh.index,
            "Direct [kWh]": daily_direct_kwh.values.round(1),
            "System [kWh]": daily_system_kwh.values.round(1)
        })
        st.dataframe(daily_df, use_container_width=True, hide_index=True)
    
    # ========================================
    # TAB 3: MONTHLY DATA
    # ========================================
    
    with tab3:
        st.markdown("### 📆 Monthly Production Summary")
        
        # Monthly table with more details
        monthly_detailed = pd.DataFrame({
            "Month": monthly_direct_kwh.index,
            "Direct Energy [kWh]": monthly_direct_kwh.values.round(0),
            "System Energy [kWh]": monthly_system_kwh.values.round(0),
            "Economic Value [€]": (monthly_system_kwh.values * price_per_kwh).round(0)
        })
        
        st.dataframe(monthly_detailed, use_container_width=True, hide_index=True)
        
        # Annual totals
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Annual Direct Energy", f"{annual_direct_kwh:,.0f} kWh")
        with col2:
            st.metric("Annual System Energy", f"{annual_system_kwh:,.0f} kWh")
        with col3:
            st.metric("Annual Economic Value", f"{annual_value:,.0f} €")
    
    # ========================================
    # TAB 4: INPUT DNI DATA
    # ========================================
    
    with tab4:
        st.markdown("### ☀️ Input DNI Hourly Profile [W/m²]")
        st.markdown("*Source data from Global Solar Atlas*")
        
        st.dataframe(
            hour_matrix_wh.style
            .format("{:.0f}")
            .set_properties(**{"line-height": "0.5rem", "padding": "2px", "font-size": "11px"})
            .background_gradient(cmap="YlOrBr", axis=0),
            use_container_width=True,
            height=(len(hour_matrix_wh) + 1) * 35 + 3
        )
        
        # DNI statistics
        st.markdown("#### 📊 DNI Statistics")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Peak DNI", f"{hour_matrix_wh.max().max():.0f} W/m²")
        with col2:
            st.metric("Average DNI", f"{hour_matrix_wh.mean().mean():.0f} W/m²")
        with col3:
            st.metric("Annual DNI", f"{annual_kwh_m2:.0f} kWh/m²")
        with col4:
            best_month = monthly_kwh_m2.idxmax()
            st.metric("Best Month", best_month)
    
    # ========================================
    # TAB 5: EXPORT & DOWNLOADS
    # ========================================
    
    with tab5:
        st.markdown("### 💾 Export Results")
        
        # ── PDF Report section ──
        st.markdown("#### 📄 Professional PDF Report")
        st.markdown("Generate a complete, branded PDF report with all system data, charts, and economics.")
        
        col_meta1, col_meta2 = st.columns(2)
        with col_meta1:
            project_name = st.text_input("Project name (optional)", placeholder="e.g. Industrial Heat – Seville")
        with col_meta2:
            location_text = st.text_input("Location (optional)", placeholder="e.g. Seville, Spain")
        notes_text = st.text_area("Additional notes (optional)", placeholder="Any notes to include in the report…", height=68)
        
        pdf_bytes = generate_report(
            mirror_area=mirror_area,
            # NOTE: report_generator.py still uses the old keyword names n12/n24/n36.
            # LC10 count is passed as n12, LC20 count as n24, and the retired 36 m² slot as 0.
            # Update report_generator.py to rename these (and its PDF labels) for full consistency.
            n12=actual_n10,
            n24=actual_n20,
            n36=0,
            eta_opt_pct=eta_opt_pct,
            thermal_loss_pct=thermal_loss_pct,
            design_peak_kw=design_peak_kw,
            target_peak_kw=target_peak_kw,
            annual_direct_kwh=annual_direct_kwh,
            annual_system_kwh=annual_system_kwh,
            monthly_direct_kwh=monthly_direct_kwh,
            monthly_system_kwh=monthly_system_kwh,
            daily_direct_kwh=daily_direct_kwh,
            daily_system_kwh=daily_system_kwh,
            hourly_direct_kw=hourly_direct_kw,
            hourly_system_kw=hourly_system_kw,
            hour_matrix_wh=hour_matrix_wh,
            monthly_kwh_m2=monthly_kwh_m2,
            annual_kwh_m2=annual_kwh_m2,
            price_per_kwh=price_per_kwh,
            system_cost=system_cost,
            total_product_cost=total_product_cost,
            installation_cost=installation_cost,
            annual_value=annual_value,
            payback_years=payback_years,
            lcoe=lcoe,
            system_lifetime_years=system_lifetime_years,
            project_name=project_name,
            location=location_text,
            notes=notes_text,
        )
        
        st.download_button(
            "📥 Download Full PDF Report",
            pdf_bytes,
            file_name="helixis_solar_report.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
        
        st.markdown("---")
        
        # ── CSV exports (kept from original) ──
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📊 CSV Data Exports")
            st.download_button(
                "📥 Download Monthly Data (CSV)",
                monthly_system_kwh.to_csv().encode("utf-8"),
                "helixis_monthly_production.csv",
                "text/csv",
                use_container_width=True
            )
            
            st.download_button(
                "📥 Download Hourly Power (CSV)",
                hourly_system_kw.to_csv().encode("utf-8"),
                "helixis_hourly_power.csv",
                "text/csv",
                use_container_width=True
            )
        
        with col2:
            st.markdown("#### 📝 Text Summary")
            unit_text = ""
            if actual_n10 > 0:
                unit_text += f"LC10 units: {actual_n10}\n"
            if actual_n20 > 0:
                unit_text += f"LC20 units: {actual_n20}\n"
            summary_text = f"""
HELIXIS SOLAR CONCENTRATOR - PRODUCTION ESTIMATE
================================================

SYSTEM CONFIGURATION
--------------------
Mirror area: {mirror_area:.2f} m²
{unit_text}Optical efficiency: {eta_opt_pct}%
Thermal losses: {thermal_loss_pct}%

ENERGY PRODUCTION
-----------------
Annual direct: {annual_direct_kwh:,.0f} kWh/year
Annual system: {annual_system_kwh:,.0f} kWh/year

ECONOMICS
---------
System cost: {system_cost:,.0f} €
Energy price: {price_per_kwh:.2f} €/kWh
Annual value: {annual_value:,.0f} €
Payback period: {payback_years:.1f} years
LCOE ({system_lifetime_years} yr): {lcoe:.4f} €/kWh

MONTHLY PRODUCTION (kWh)
------------------------
{monthly_system_kwh.to_string()}
            """
            
            st.download_button(
                "📄 Download Summary Report (TXT)",
                summary_text.encode("utf-8"),
                "helixis_summary_report.txt",
                "text/plain",
                use_container_width=True
            )
    
    # ========================================
    # TAB 6: TORKNING (GRAIN DRYING)
    # ========================================

    with tab6:
        st.markdown("### 🌾 Grain Drying – Solar Heat Analysis")
        st.markdown(
            "Calculate how solar heat, thermal storage and supplementary heat sources "
            "can meet the drying energy demand during the harvest season."
        )

        # ── Period selection ──────────────────────────────────────
        st.markdown("#### 📅 Drying Period")
        MONTH_ORDER = list(DAYS_IN_MONTH.keys())
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            start_month = st.selectbox(
                "Start month", MONTH_ORDER,
                index=MONTH_ORDER.index("Aug"),
                key="dry_start"
            )
        with col_p2:
            end_month = st.selectbox(
                "End month", MONTH_ORDER,
                index=MONTH_ORDER.index("Sep"),
                key="dry_end"
            )

        start_idx = MONTH_ORDER.index(start_month)
        end_idx   = MONTH_ORDER.index(end_month)
        if end_idx < start_idx:
            st.warning("⚠️ End month is before start month – please swap them.")
            selected_months = []
        else:
            selected_months = MONTH_ORDER[start_idx : end_idx + 1]
            period_days = sum(DAYS_IN_MONTH[m] for m in selected_months)
            st.info(
                f"**Selected period:** {start_month} – {end_month} "
                f"({len(selected_months)} months, {period_days} days)"
            )

        if selected_months:
            # ── Solar energy in period ───────────────────────────
            period_solar_kwh = float(monthly_system_kwh[selected_months].sum())
            period_daily_kwh = daily_system_kwh[selected_months]

            # ── Drying demand ────────────────────────────────────
            st.markdown("#### ⚡ Drying Energy Demand")
            st.caption(
                "Reference: a farm drying 10 000 tonnes/season typically requires ~1 MW "
                "thermal over 6 weeks (Aug–Sep), consuming ~1 000 MWh of heat energy."
            )
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                grain_tonnes = st.number_input(
                    "Grain to dry [tonnes]", min_value=0.1, value=10000.0, step=500.0,
                    key="dry_tonnes"
                )
            with col_d2:
                mc_in = st.number_input(
                    "Incoming moisture content [%]", min_value=1.0, max_value=40.0,
                    value=20.0, step=0.5, key="dry_mc_in"
                )
            with col_d3:
                mc_out = st.number_input(
                    "Target moisture content [%]", min_value=1.0, max_value=30.0,
                    value=14.0, step=0.5, key="dry_mc_out"
                )

            # Water to remove (wet basis)
            mc_in_f  = mc_in  / 100.0
            mc_out_f = mc_out / 100.0
            water_to_remove_kg = grain_tonnes * 1000.0 * (mc_in_f - mc_out_f) / (1.0 - mc_out_f)
            # Specific energy for hot-air grain drying ≈ 1 430 kWh/ton water gives ~1 000 MWh for 10 000 t
            specific_energy_kwh_t = st.slider(
                "Specific drying energy [kWh / tonne of water removed]",
                min_value=600, max_value=2000, value=1430, step=50,
                key="dry_specific",
                help="Typically 800–1 500 kWh/tonne of water removed. Default calibrated to ~1 000 MWh for 10 000 t at 20→14 % MC."
            )
            total_drying_kwh = (water_to_remove_kg / 1000.0) * specific_energy_kwh_t
            # Peak thermal power assuming uniform load over 6 weeks (42 days × 18 h/day)
            peak_drying_kw = total_drying_kwh / (period_days * 18) if period_days > 0 else 0

            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            with col_r1:
                st.metric("Water to remove", f"{water_to_remove_kg/1000:.1f} tonnes")
            with col_r2:
                st.metric("Total drying demand", f"{total_drying_kwh/1000:,.1f} MWh")
            with col_r3:
                st.metric("Avg. peak thermal load", f"{peak_drying_kw:,.0f} kW")
            with col_r4:
                solar_coverage_pct = min(period_solar_kwh / total_drying_kwh * 100, 100) \
                    if total_drying_kwh > 0 else 0
                st.metric("Solar heat covers", f"{solar_coverage_pct:.1f} %")

            # ── LC20 unit sizing ─────────────────────────────────
            st.markdown("#### 🔆 LC20 Unit Sizing")
            # Energy-based: how many LC20 units to cover the full drying demand
            kwh_per_lc20 = float(monthly_system_kwh[selected_months].sum() / max(mirror_area, 1)) * APERTURE_20 \
                if mirror_area > 0 else 0
            lc20_for_energy = math.ceil(total_drying_kwh / kwh_per_lc20) if kwh_per_lc20 > 0 else 0
            # Peak-power-based: units to deliver the average peak thermal load
            lc20_for_peak = math.ceil(peak_drying_kw / (APERTURE_20 * peak_kw_per_m2)) \
                if peak_kw_per_m2 > 0 else 0

            col_lc1, col_lc2, col_lc3 = st.columns(3)
            with col_lc1:
                st.metric(
                    "LC20 units – full energy cover",
                    f"{lc20_for_energy} units",
                    help="Number of LC20 units whose seasonal output equals the total drying demand."
                )
            with col_lc2:
                st.metric(
                    "LC20 units – peak power cover",
                    f"{lc20_for_peak} units",
                    help="Number of LC20 units to deliver the average thermal peak load during daylight hours."
                )
            with col_lc3:
                lc20_mirror_total = lc20_for_peak * APERTURE_20
                st.metric(
                    "Total mirror area (peak)",
                    f"{lc20_mirror_total:,.0f} m²"
                )
            st.info(
                f"💡 **Recommendation:** {lc20_for_peak} × LC20 units cover the ~{peak_drying_kw:,.0f} kW "
                f"thermal peak load. Combined with thermal storage and a backup heater/heat pump, "
                f"this can reliably supply the full {total_drying_kwh/1000:,.0f} MWh seasonal demand."
            )

            daily_demand_kwh = total_drying_kwh / period_days if period_days > 0 else 0

            # ── Dual thermal storage configuration ───────────────
            st.markdown("#### 🛢️ Thermal Storage – Water & Oil Tanks")
            st.markdown(
                "Configure two storage media. Solar concentrators, heat pumps and electric "
                "heaters each have a configurable split between the tanks. Discharge priority "
                "is applied each day to meet the drying demand."
            )

            col_wh, col_oil = st.columns(2)
            with col_wh:
                st.markdown("##### 💧 Water Tank  *(low-temp, 60–95 °C)*")
                w_cap   = st.number_input("Capacity [kWh]",  min_value=0.0, value=500.0,  step=50.0,  key="w_cap")
                w_eff   = st.slider("Round-trip efficiency [%]", 50, 99, 92, key="w_eff") / 100.0
                w_prio  = st.radio("Discharge priority", ["First (primary)", "Second (backup)"],
                                   index=0, key="w_prio", horizontal=True)
            with col_oil:
                st.markdown("##### 🛢️ Thermal Oil Tank  *(high-temp, 100–300 °C)*")
                o_cap   = st.number_input("Capacity [kWh]",  min_value=0.0, value=300.0,  step=50.0,  key="o_cap")
                o_eff   = st.slider("Round-trip efficiency [%]", 50, 99, 88, key="o_eff") / 100.0
                st.markdown("*(Discharge priority follows water tank setting)*")

            water_first = (w_prio == "First (primary)")

            # ── Heat sources ──────────────────────────────────────
            st.markdown("#### 🔌 Heat Sources & Charging Split")
            st.markdown(
                "For each source, set the installed capacity and how the heat output is "
                "split between the two tanks. Charging priority per day: "
                "**Solar → Heat pump → Electric heater**."
            )

            col_src1, col_src2, col_src3 = st.columns(3)

            with col_src1:
                st.markdown("**☀️ Solar concentrators**")
                st.caption(f"Available: {period_solar_kwh/period_days:,.0f} kWh/day (avg)")
                sol_w_pct = st.slider("→ Water tank [%]", 0, 100, 60, key="sol_w_pct")
                sol_o_pct = 100 - sol_w_pct
                st.caption(f"→ Oil tank: {sol_o_pct} %")

            with col_src2:
                st.markdown("**🔄 Heat pump**")
                use_hp = st.checkbox("Enable", value=True, key="dry_use_hp")
                if use_hp:
                    cop        = st.number_input("COP", 1.0, 8.0, 3.5, 0.1, key="dry_hp_cop")
                    hp_cap_kw  = st.number_input("Thermal capacity [kW]", 10.0, 2000.0, 200.0, 10.0, key="dry_hp_cap")
                    hp_op_h    = st.slider("Operating hours/day", 1, 24, 16, key="dry_hp_h")
                    hp_w_pct   = st.slider("→ Water tank [%]", 0, 100, 80, key="hp_w_pct")
                    hp_o_pct   = 100 - hp_w_pct
                    st.caption(f"→ Oil tank: {hp_o_pct} %")
                    hp_day_kwh = hp_cap_kw * hp_op_h
                else:
                    cop = hp_cap_kw = hp_op_h = hp_day_kwh = 0.0
                    hp_w_pct = hp_o_pct = 0

            with col_src3:
                st.markdown("**⚡ Electric heater**")
                use_el = st.checkbox("Enable", value=True, key="dry_use_el")
                if use_el:
                    el_cap_kw = st.number_input("Thermal capacity [kW]", 10.0, 2000.0, 100.0, 10.0, key="dry_el_cap")
                    el_op_h   = st.slider("Max operating hours/day", 1, 24, 8, key="dry_el_h")

                    # ── Spot price detection: accept any loaded source ──
                    _spot_src = (
                        st.session_state.get("drying_spot_df") or
                        st.session_state.get("sp_loaded_df") or
                        (lambda df: df[["Tid", next(c for c in df.columns if c.endswith("_kr_kwh"))]]
                            .rename(columns={next(c for c in df.columns if c.endswith("_kr_kwh")): "spotpris"})
                            if df is not None and any(c.endswith("_kr_kwh") for c in df.columns) else None
                        )(st.session_state.get("spot_full_extended"))
                    )
                    _spot_loaded = _spot_src is not None and not _spot_src.empty if hasattr(_spot_src, "empty") else False

                    if _spot_loaded:
                        # Store for simulation use
                        st.session_state["drying_spot_df"] = _spot_src
                        _avg_ore = float(_spot_src["spotpris"].mean() * 100)
                        st.caption(f"✅ Spot prices loaded — avg {_avg_ore:.0f} öre/kWh")
                        el_threshold_ore = st.slider(
                            "Run when spot price below [öre/kWh]",
                            min_value=10, max_value=300, value=100, step=5,
                            key="dry_el_threshold",
                            help="Electric heater only runs on days where the average spot price is below this threshold."
                        )
                    else:
                        st.caption("⚠️ No spot prices loaded — load in ⚡ Spot Prices tab")
                        el_threshold_ore = 999  # always run

                    el_energy_tax_ore = st.number_input(
                        "Energy tax [öre/kWh]", 0.0, 100.0, 43.9, 0.1,
                        key="dry_el_tax",
                        help="Energiskatt — 43.9 öre/kWh (2024)"
                    )
                    el_transfer_ore = st.number_input(
                        "Transfer cost [öre/kWh]", 0.0, 100.0, 25.0, 0.5,
                        key="dry_el_transfer",
                        help="Överföringskostnad — typical 20–50 öre/kWh"
                    )
                    el_w_pct = st.slider("→ Water tank [%]", 0, 100, 40, key="el_w_pct")
                    el_o_pct = 100 - el_w_pct
                    st.caption(f"→ Oil tank: {el_o_pct} %")
                    el_day_kwh_max = el_cap_kw * el_op_h
                else:
                    el_cap_kw = el_op_h = el_day_kwh_max = 0.0
                    el_threshold_ore = 0
                    el_energy_tax_ore = el_transfer_ore = 0.0
                    el_w_pct = el_o_pct = 0

            # ── Day-by-day simulation ─────────────────────────────
            daily_solar_list = []
            daily_dates_list = []
            for m in selected_months:
                sol_day = float(daily_system_kwh[m])
                for d in range(DAYS_IN_MONTH[m]):
                    daily_solar_list.append(sol_day)
                    # Build a representative date for spot price lookup
                    mo_idx = MONTHS.index(m) + 1
                    daily_dates_list.append(date(2024, mo_idx, min(d + 1, DAYS_IN_MONTH[m])))

            # Build daily average spot price map (kr/kWh → öre/kWh)
            _spot_df_dry = st.session_state.get("drying_spot_df")
            daily_spot_ore_map = {}
            if _spot_df_dry is not None and not _spot_df_dry.empty:
                _sdf = _spot_df_dry.copy()
                _sdf["_date"] = pd.to_datetime(_sdf["Tid"]).dt.date
                # Use month+day only (year-agnostic match)
                _sdf["_md"] = _sdf["_date"].apply(lambda d: (d.month, d.day))
                _md_avg = _sdf.groupby("_md")["spotpris"].mean() * 100  # → öre/kWh
                daily_spot_ore_map = _md_avg.to_dict()

            soc_w, soc_o = 0.0, 0.0
            sim = []   # one dict per day

            for solar_day, sim_date in zip(daily_solar_list, daily_dates_list):
                # Get spot price for this day (month, day)
                md_key = (sim_date.month, sim_date.day)
                day_spot_ore = daily_spot_ore_map.get(md_key, el_threshold_ore)  # fallback = threshold (always run)

                # Electric heater runs only when spot < threshold
                el_day_kwh = el_day_kwh_max if (use_el and day_spot_ore < el_threshold_ore) else 0.0

                row = dict(
                    solar=0.0, hp=0.0, el=0.0,
                    dis_w=0.0, dis_o=0.0, deficit=0.0,
                    soc_w=0.0, soc_o=0.0,
                    spot_ore=day_spot_ore,
                    el_enabled=(el_day_kwh > 0),
                )
                remaining_demand = daily_demand_kwh

                # ── 1. CHARGING (priority: solar → HP → electric) ──
                for src_kwh, w_frac, o_frac, src_key in [
                    (solar_day,                    sol_w_pct/100, sol_o_pct/100, "solar"),
                    (hp_day_kwh  if use_hp else 0, hp_w_pct/100,  hp_o_pct/100, "hp"),
                    (el_day_kwh,                   el_w_pct/100,  el_o_pct/100, "el"),
                ]:
                    if src_kwh <= 0:
                        continue
                    # Try to push directly to demand first, then overflow to tanks
                    direct = min(src_kwh, remaining_demand)
                    remaining_demand -= direct
                    row[src_key] += direct

                    leftover = src_kwh - direct
                    chg_w = min(leftover * w_frac, w_cap - soc_w)
                    chg_o = min(leftover * o_frac, o_cap - soc_o)
                    # If split leaves unused capacity in one tank, spill to the other
                    spill = leftover - chg_w - chg_o
                    if spill > 0:
                        extra_w = min(spill, w_cap - soc_w - chg_w)
                        extra_o = min(spill - extra_w, o_cap - soc_o - chg_o)
                        chg_w += extra_w
                        chg_o += extra_o
                    soc_w += chg_w
                    soc_o += chg_o
                    row[src_key] += chg_w + chg_o   # track total from this source

                # ── 2. DISCHARGE (priority order per user setting) ──
                tanks = (
                    [("w", soc_w, w_cap, w_eff), ("o", soc_o, o_cap, o_eff)]
                    if water_first
                    else [("o", soc_o, o_cap, o_eff), ("w", soc_w, w_cap, w_eff)]
                )
                for t_key, t_soc, t_cap, t_eff in tanks:
                    if remaining_demand <= 0:
                        break
                    avail = t_soc * t_eff
                    used  = min(avail, remaining_demand)
                    drained = used / t_eff if t_eff > 0 else used
                    if t_key == "w":
                        soc_w = max(soc_w - drained, 0)
                        row["dis_w"] += used
                    else:
                        soc_o = max(soc_o - drained, 0)
                        row["dis_o"] += used
                    remaining_demand -= used

                row["deficit"] = max(remaining_demand, 0)
                row["soc_w"]   = soc_w
                row["soc_o"]   = soc_o
                sim.append(row)

            sim_df = pd.DataFrame(sim)
            sim_df.index = pd.RangeIndex(1, len(sim_df) + 1)
            sim_df.index.name = "Day"

            total_solar_used = sim_df["solar"].sum()
            total_hp_used    = sim_df["hp"].sum()
            total_el_used    = sim_df["el"].sum()
            total_dis_w      = sim_df["dis_w"].sum()
            total_dis_o      = sim_df["dis_o"].sum()
            total_deficit    = sim_df["deficit"].sum()
            total_supplied   = total_drying_kwh - total_deficit
            coverage_pct     = min(total_supplied / total_drying_kwh * 100, 100) \
                if total_drying_kwh > 0 else 0

            # ── KPI row ───────────────────────────────────────────
            st.markdown("#### 📊 Simulation Results")
            kc = st.columns(5)
            kc[0].metric("Overall coverage",       f"{coverage_pct:.1f} %")
            kc[1].metric("Solar used",             f"{total_solar_used/1000:,.1f} MWh")
            kc[2].metric("Heat pump used",         f"{total_hp_used/1000:,.1f} MWh")
            kc[3].metric("Electric heater used",   f"{total_el_used/1000:,.1f} MWh")
            kc[4].metric("Unmet deficit",          f"{total_deficit/1000:,.1f} MWh")

            kc2 = st.columns(4)
            kc2[0].metric("Water tank discharge",  f"{total_dis_w/1000:,.1f} MWh")
            kc2[1].metric("Oil tank discharge",    f"{total_dis_o/1000:,.1f} MWh")
            kc2[2].metric("Days with deficit",     f"{(sim_df['deficit']>5).sum()} days")
            kc2[3].metric("Max water SOC reached", f"{sim_df['soc_w'].max()/w_cap*100:.0f} %" if w_cap>0 else "–")

            # ── SOC chart ─────────────────────────────────────────
            st.markdown("##### Storage State of Charge – daily evolution")
            soc_chart = pd.DataFrame({
                "Water tank [kWh]": sim_df["soc_w"],
                "Oil tank [kWh]":   sim_df["soc_o"],
            })
            st.line_chart(soc_chart, color=["#2196F3", "#F4A300"])

            # ── Daily energy-flow chart ───────────────────────────
            st.markdown("##### Daily energy flows [kWh]")
            flow_chart = pd.DataFrame({
                "Solar direct":        sim_df["solar"].clip(upper=daily_demand_kwh),
                "Water tank out":      sim_df["dis_w"],
                "Oil tank out":        sim_df["dis_o"],
                "Heat pump":           sim_df["hp"].clip(upper=daily_demand_kwh),
                "Electric heater":     sim_df["el"].clip(upper=daily_demand_kwh),
            })
            st.bar_chart(flow_chart, color=["#F4A300","#2196F3","#FF8C00","#4CAF50","#E91E63"])

            # ── Economics ─────────────────────────────────────────
            st.markdown("#### 💰 Economic Comparison")
            pellets_price = st.number_input(
                "Reference price pellets / fuel oil [€/kWh]", min_value=0.01, value=0.08,
                step=0.01, key="dry_pellets"
            )
            ref_cost = total_drying_kwh * pellets_price

            hp_el_kwh = total_hp_used / cop if (use_hp and cop > 0) else 0.0
            # HP electricity price: use spot average if available, else energy tax + transfer only
            _hp_spot_src = st.session_state.get("drying_spot_df")
            hp_spot_eur = float(_hp_spot_src["spotpris"].mean()) if _hp_spot_src is not None else 0.10
            hp_cost = hp_el_kwh * hp_spot_eur

            # Electric heater cost: weighted actual spot + fixed tax + transfer
            if use_el and total_el_used > 0:
                # Weighted average spot price over days heater ran
                _el_rows = sim_df[sim_df["el_enabled"] == True] if "el_enabled" in sim_df.columns else sim_df
                avg_spot_ore = _el_rows["spot_ore"].mean() if len(_el_rows) > 0 else el_threshold_ore
                el_spot_cost  = total_el_used * avg_spot_ore / 100       # spot energy cost
                el_tax_cost   = total_el_used * el_energy_tax_ore / 100  # energiskatt
                el_trans_cost = total_el_used * el_transfer_ore / 100    # överföring
                el_total_cost = el_spot_cost + el_tax_cost + el_trans_cost
                el_avg_total_ore = avg_spot_ore + el_energy_tax_ore + el_transfer_ore
            else:
                el_spot_cost = el_tax_cost = el_trans_cost = el_total_cost = 0.0
                avg_spot_ore = 0.0
                el_avg_total_ore = 0.0

            backup_cost = hp_cost + el_total_cost
            savings     = ref_cost - backup_cost

            # How many days did the heater actually run?
            el_days_active = int(sim_df["el_enabled"].sum()) if "el_enabled" in sim_df.columns else 0
            el_days_total  = len(sim_df)

            col_e1, col_e2, col_e3, col_e4 = st.columns(4)
            col_e1.metric("Cost – all pellets/fuel",   f"{ref_cost:,.0f} €")
            col_e2.metric("Backup operating cost",     f"{backup_cost:,.0f} €",
                          delta=f"-{savings:,.0f} € vs pellets" if savings > 0 else None)
            col_e3.metric("Avoided fuel cost (solar)", f"{total_solar_used * pellets_price:,.0f} €")
            col_e4.metric("HP electricity cost",       f"{hp_cost:,.0f} €")

            # Electric heater cost breakdown
            if use_el and total_el_used > 0:
                st.markdown("##### ⚡ Electric heater cost breakdown")
                eb1, eb2, eb3, eb4, eb5 = st.columns(5)
                eb1.metric("Heater active days",
                           f"{el_days_active} / {el_days_total}",
                           delta=f"spot < {el_threshold_ore} öre/kWh")
                eb2.metric("Total el. consumed",   f"{total_el_used:,.0f} kWh")
                eb3.metric(f"Spot cost (avg {avg_spot_ore:.0f} öre)",
                           f"{el_spot_cost:,.0f} €")
                eb4.metric(f"Tax ({el_energy_tax_ore:.1f}) + Transfer ({el_transfer_ore:.1f} öre)",
                           f"{el_tax_cost + el_trans_cost:,.0f} €")
                eb5.metric(f"Total el. cost  ({el_avg_total_ore:.0f} öre/kWh avg)",
                           f"{el_total_cost:,.0f} €")

            # ── Summary table ─────────────────────────────────────
            st.markdown("#### 📋 Full System Summary")
            summary_rows = {
                "Item": [
                    "Total drying demand",
                    "  ☀️ Solar (direct + stored)",
                    "  🔄 Heat pump contribution",
                    "  ⚡ Electric heater contribution",
                    "  💧 Water tank net discharge",
                    "  🛢️ Oil tank net discharge",
                    "Unmet deficit",
                    "Overall coverage",
                    "Reference cost (all pellets)",
                    "  El. heater – spot cost",
                    "  El. heater – energy tax",
                    "  El. heater – transfer cost",
                    "  Heat pump cost",
                    "Total backup operating cost",
                    "Net savings vs. reference",
                ],
                "Value": [
                    f"{total_drying_kwh/1000:,.1f} MWh",
                    f"{total_solar_used/1000:,.1f} MWh  ({total_solar_used/total_drying_kwh*100:.0f} %)" if total_drying_kwh > 0 else "–",
                    f"{total_hp_used/1000:,.1f} MWh" if use_hp else "–",
                    f"{total_el_used/1000:,.1f} MWh  ({el_days_active} days active)" if use_el else "–",
                    f"{total_dis_w/1000:,.1f} MWh",
                    f"{total_dis_o/1000:,.1f} MWh",
                    f"{total_deficit/1000:,.1f} MWh  ({total_deficit/total_drying_kwh*100:.1f} %)" if total_drying_kwh > 0 else "–",
                    f"{coverage_pct:.1f} %",
                    f"{ref_cost:,.0f} €",
                    f"{el_spot_cost:,.0f} €  (avg {avg_spot_ore:.0f} öre/kWh)" if use_el else "–",
                    f"{el_tax_cost:,.0f} €  ({el_energy_tax_ore:.1f} öre/kWh)" if use_el else "–",
                    f"{el_trans_cost:,.0f} €  ({el_transfer_ore:.1f} öre/kWh)" if use_el else "–",
                    f"{hp_cost:,.0f} €" if use_hp else "–",
                    f"{backup_cost:,.0f} €",
                    f"{savings:,.0f} €",
                ]
            }
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

            # ── Monthly solar vs demand bar chart ─────────────────
            st.markdown("#### 📊 Monthly Solar Heat vs. Drying Demand")
            monthly_demand_kwh_per = total_drying_kwh / len(selected_months) if selected_months else 0
            chart_df = pd.DataFrame({
                "Month":                selected_months,
                "Solar heat [kWh]":    [float(monthly_system_kwh[m]) for m in selected_months],
                "Drying demand [kWh]": [monthly_demand_kwh_per] * len(selected_months),
            })
            st.bar_chart(chart_df.set_index("Month"), color=["#F4A300", "#2196F3"])


    # ========================================
    # TAB 7: SPOT PRICES
    # ========================================

    with tab7:
        st.markdown("### ⚡ Electricity Spot Prices")
        st.markdown(
            "Load Nord Pool spot prices by uploading the CSV from the battery simulation app, "
            "or fetch any period directly from ENTSO-E. The two apps remain fully independent."
        )

        # ── Step 1: Get data into session cache ───────────────────────
        st.markdown("#### 1️⃣ Load spot price data")
        src_col1, src_col2 = st.columns(2)

        with src_col1:
            st.markdown("**📂 Upload CSV file**")
            st.caption("Upload `spotpriser_2023_2026.csv` exported from the battery simulation app.")
            uploaded_spot = st.file_uploader(
                "spotpriser_2023_2026.csv", type=["csv"],
                key="sp_csv_upload", label_visibility="collapsed"
            )
            if uploaded_spot is not None:
                try:
                    raw_df = _ingest_spot_csv(uploaded_spot)
                    st.session_state['spot_full_extended'] = raw_df
                    st.session_state.pop('spot_live_extended_to', None)
                    _add_spot_log(f"Uploaded CSV: {len(raw_df):,} rows, {raw_df['Tid'].min().date()} → {raw_df['Tid'].max().date()}")
                    st.success(
                        f"✅ CSV loaded — **{len(raw_df):,} rows** "
                        f"({raw_df['Tid'].min().date()} → {raw_df['Tid'].max().date()})"
                    )
                except Exception as e:
                    st.error(f"❌ Could not read file: {e}")

        with src_col2:
            st.markdown("**🌐 Fetch directly from ENTSO-E**")
            st.caption("Downloads hourly day-ahead prices for any period. No CSV file needed.")
            me_c1, me_c2 = st.columns(2)
            me_area  = me_c1.selectbox("Area", ["SE1","SE2","SE3","SE4"], index=3, key="me_area",
                                        help="SE4 = Skåne / Southern Sweden")
            me_start = me_c1.date_input("Start", value=date(2024, 1, 1), key="me_start")
            me_end   = me_c2.date_input("End",   value=date.today(),     key="me_end")
            me_key   = me_c2.text_input("API key (optional)", type="password", key="me_key",
                                         help="Leave blank to use the built-in key")
            if st.button("🌐 Fetch from ENTSO-E", key="me_fetch_btn", use_container_width=True):
                with st.spinner(f"Fetching {me_area} {me_start}→{me_end} from ENTSO-E…"):
                    try:
                        me_df = fetch_spotprices_entsoe(
                            me_key or ENTSOE_API_KEY, me_area,
                            str(me_start), str(me_end)
                        )
                        raw_frame = me_df.rename(columns={"spotpris": f"{me_area}_kr_kwh"})
                        raw_frame[f"{me_area}_ore_kwh"] = raw_frame[f"{me_area}_kr_kwh"] * 100
                        st.session_state['spot_full_extended'] = raw_frame
                        st.session_state['spot_entsoe_area']   = me_area
                        st.session_state.pop('spot_live_extended_to', None)
                        _add_spot_log(f"ENTSO-E: fetched {len(me_df):,} hours for {me_area}")
                        st.success(f"✅ Fetched **{len(me_df):,}** hours for **{me_area}**")
                    except Exception as _e:
                        st.error(f"❌ {_e}")

        # Cache status
        _cached = st.session_state.get('spot_full_extended')
        if _cached is not None:
            st.info(
                f"💾 **Data in memory:** {len(_cached):,} rows · "
                f"{_cached['Tid'].min().date()} → {_cached['Tid'].max().date()} · "
                f"{len([c for c in _cached.columns if 'kr_kwh' in c])} area(s)"
            )

        st.markdown("---")

        # ── Step 2: Select area & date range, view data ───────────────
        st.markdown("#### 2️⃣ Select area & period to display")
        sp_c1, sp_c2, sp_c3, sp_c4 = st.columns(4)
        with sp_c1:
            sp_area = st.selectbox(
                "Price area", ["SE1", "SE2", "SE3", "SE4"], index=3, key="sp_area",
                help="SE4 = Malmö/Skåne"
            )
        with sp_c2:
            sp_start = st.date_input("Start date", value=date(2024, 7, 1), key="sp_start")
        with sp_c3:
            sp_end = st.date_input("End date", value=date(2024, 9, 30), key="sp_end")
        with sp_c4:
            st.markdown(" ")
            load_btn   = st.button("📊 Show prices", type="primary", key="sp_load_btn", use_container_width=True)
            reload_btn = st.button("🔄 Re-extend live", key="sp_reload_btn", use_container_width=True)

        if load_btn or reload_btn:
            with st.spinner(f"Preparing {sp_area} data…"):
                sp_df = _load_preinstalled_spotprices(
                    sp_area, sp_start, sp_end, force_reload=bool(reload_btn)
                )
            if sp_df is not None and not sp_df.empty:
                st.session_state["sp_loaded_df"]   = sp_df
                st.session_state["sp_loaded_area"] = sp_area
            else:
                err = st.session_state.get('spot_load_error', 'No data found for selected area/period.')
                st.warning(f"⚠️ {err}")

        # Live-fetch status
        _spot_err  = st.session_state.get('spot_live_fetch_error')
        _spot_last = st.session_state.get('spot_live_extended_to', '—')
        if _spot_err:
            st.warning(f"⚠️ Live-extension error: {_spot_err}  ·  Last successful: **{_spot_last}**")
        elif _spot_last != '—':
            st.caption(f"Live data extended to: **{_spot_last}**")

        # ── Step 3: Display ───────────────────────────────────────────
        sp_df_show  = st.session_state.get("sp_loaded_df")
        loaded_area = st.session_state.get("sp_loaded_area", sp_area)

        if sp_df_show is not None and not sp_df_show.empty:
            st.markdown("---")
            st.markdown("#### 📊 Results")
            eur_sek     = st.session_state.get("spot_eur_sek_rate", 11.20)
            show_eur    = st.toggle("Show in EUR/kWh", value=False, key="sp_eur_toggle")
            prices_disp = sp_df_show["spotpris"] / eur_sek if show_eur else sp_df_show["spotpris"]
            currency    = "EUR/kWh" if show_eur else "kr/kWh"

            kc1, kc2, kc3, kc4 = st.columns(4)
            kc1.metric("Min",     f"{prices_disp.min():.3f} {currency}")
            kc2.metric("Max",     f"{prices_disp.max():.3f} {currency}")
            kc3.metric("Mean",    f"{prices_disp.mean():.3f} {currency}")
            kc4.metric("EUR/SEK", f"{eur_sek:.2f}")

            st.markdown("##### Daily price gap (max − min per day)")
            _pg  = sp_df_show.copy()
            _pg["_dp"] = prices_disp.values
            _pg["Day"] = _pg["Tid"].dt.date
            _ds  = _pg.groupby("Day")["_dp"].agg(["min","max"])
            _ds["gap"] = _ds["max"] - _ds["min"]
            st.line_chart(_ds["gap"].rename(f"Price gap [{currency}]"))
            st.caption(
                f"Average daily price gap: **{_ds['gap'].mean():.3f} {currency}**  ·  "
                f"Max gap: **{_ds['gap'].max():.3f} {currency}** on {_ds['gap'].idxmax()}"
            )

            st.markdown("##### Monthly average spot price")
            _mo           = sp_df_show.copy()
            _mo["_dp"]    = prices_disp.values
            _mo["Period"] = _mo["Tid"].dt.to_period("M").astype(str)
            _ma           = _mo.groupby("Period")["_dp"].agg(["mean","min","max"]).reset_index()
            st.bar_chart(_ma.set_index("Period")["mean"].rename(f"Mean [{currency}]"))

            with st.expander("📋 Monthly data table"):
                _ma.columns = ["Period", f"Mean {currency}", f"Min {currency}", f"Max {currency}"]
                st.dataframe(_ma, use_container_width=True, hide_index=True)

            if st.button("💾 Use these prices in Grain Drying tab", key="sp_use_btn"):
                st.session_state["drying_spot_df"]   = sp_df_show.copy()
                st.session_state["drying_spot_area"] = loaded_area
                st.success(f"✅ Stored for **{loaded_area}** — switch to **🌾 Grain Drying**.")

            st.download_button(
                "📥 Download filtered CSV",
                data=sp_df_show.to_csv(index=False).encode("utf-8"),
                file_name=f"spot_{loaded_area}_{sp_df_show['Tid'].min().date()}_{sp_df_show['Tid'].max().date()}.csv",
                mime="text/csv",
                key="sp_download_btn"
            )

            with st.expander("📋 Load log"):
                for lg in reversed(st.session_state.get("spot_log", [])[-20:]):
                    st.caption(lg)
        else:
            st.info("Upload the CSV file or fetch from ENTSO-E above, then click **Show prices**.")
            st.markdown("""
| Area | Region |
|------|--------|
| SE1 | Luleå / Northern Sweden |
| SE2 | Sundsvall / Mid-North Sweden |
| SE3 | Stockholm / Central Sweden |
| SE4 | Malmö / **Skåne** / Southern Sweden |

> 💡 For the Skåne grain drying use case select **SE4**.
            """)

    # ========================================
    # TAB 8: FIELD LAYOUT & PHYSICAL DIMENSIONING
    # ========================================

    with tab8:
        st.markdown("### 📐 Field Layout & Physical Dimensioning")
        st.markdown(
            "Configure the concentrator array layout and get accurate ground area, "
            "shadow-free spacing and structural requirements."
        )

        # ── LC20 physical dimensions (fixed product specs) ───────────
        # LC20 active mirror area: 20 m²
        # NOTE: physical footprint depth/width below are placeholders carried
        # over from the previous unit — confirm the real LC20 footprint and update.
        UNIT_DEPTH_M  = 5.0   # N-S dimension (determines row pitch) — CONFIRM for LC20
        UNIT_WIDTH_M  = 5.0   # E-W dimension per unit — CONFIRM for LC20

        # Use unit count from sidebar — no duplication
        n_units = int(total_units) if total_units > 0 else 1

        fl_col1, fl_col2 = st.columns([1, 1])

        with fl_col1:
            st.markdown("#### ⚙️ Layout parameters")
            st.caption(
                f"Using **{n_units} units** and optical efficiency **{eta_opt_pct}%** "
                f"from the sidebar. Only physical spacing is configured here."
            )

            n_per_string_max = max(1, n_units)
            n_per_string_default = min(4, n_per_string_max)
            if n_per_string_max > 1:
                n_per_string = st.slider("Units per string (columns)", min_value=1,
                                         max_value=n_per_string_max,
                                         value=n_per_string_default)
            else:
                # A Streamlit slider requires min_value < max_value, so with a
                # single unit we skip the slider and fix it at 1.
                n_per_string = 1
                st.caption("Units per string (columns): **1** (single unit)")

            spacing_factor = st.slider("Row spacing factor", min_value=1.0, max_value=3.0,
                                       value=1.5, step=0.1, key="fl_spacing",
                                       help="Row pitch = aperture depth × factor. "
                                            "1.5× = shadow-free at solar elevation ≥34°. "
                                            "2.0× = shadow-free at ≥27°.")

            col_gap = st.slider("Column gap (m)", min_value=0.5, max_value=5.0,
                                value=2.0, step=0.5, key="fl_col_gap",
                                help="Clear gap between adjacent units in a string.")

            with st.container(border=True):
                st.markdown("**Shadow spacing method**")
                st.markdown(
                    f"Row spacing = aperture depth × spacing factor.  \n"
                    f"At **{spacing_factor:.1f}×** the row behind is fully clear of shadow "
                    f"at solar elevation ≥**{max(5, round(90 - math.degrees(math.atan(spacing_factor)), 0)):.0f}°**. "
                    f"Higher factors give year-round clear sky access at lower sun angles."
                )

        # ── Derived geometry ─────────────────────────────────────────
        n_strings  = math.ceil(n_units / n_per_string)
        last_string_units = n_units - (n_strings - 1) * n_per_string

        row_pitch   = UNIT_DEPTH_M * spacing_factor
        col_pitch   = UNIT_WIDTH_M + col_gap
        shadow_zone = row_pitch - UNIT_DEPTH_M

        field_width  = n_per_string * col_pitch - col_gap
        field_depth  = n_strings * row_pitch - shadow_zone
        field_width_r  = round(field_width / 0.5) * 0.5
        field_depth_r  = round(field_depth / 0.5) * 0.5

        gross_footprint = field_width_r * field_depth_r
        aperture_area   = n_units * APERTURE_20
        gcr_pct         = aperture_area / gross_footprint * 100 if gross_footprint > 0 else 0

        with fl_col2:
            # ── SVG field diagram via components.html ─────────────────
            st.markdown("#### 🗺️ Array footprint diagram")
            import streamlit.components.v1 as _components

            SVG_W, SVG_H = 460, 420
            PAD_L = 44   # left padding for height label
            PAD_T = 16   # top
            PAD_B = 50   # bottom for width label + legend
            PAD_R = 16   # right

            draw_w = SVG_W - PAD_L - PAD_R
            draw_h = SVG_H - PAD_T - PAD_B

            # Scale so the full array fits
            scale = min(draw_w / max(field_width_r, 0.1),
                        draw_h / max(field_depth_r, 0.1))

            unit_w_px = UNIT_WIDTH_M * scale
            unit_d_px = UNIT_DEPTH_M * scale
            col_p_px  = col_pitch    * scale
            row_p_px  = row_pitch    * scale
            shadow_px = shadow_zone  * scale

            shapes = []

            for row in range(n_strings):
                units_this = n_per_string if row < n_strings - 1 else last_string_units
                y0 = PAD_T + row * row_p_px
                # Shadow zone (pink strip between rows)
                if row < n_strings - 1:
                    sw = units_this * col_p_px - (col_pitch - UNIT_WIDTH_M) * scale
                    shapes.append(
                        f'<rect x="{PAD_L:.1f}" y="{y0 + unit_d_px:.1f}" '
                        f'width="{sw:.1f}" height="{shadow_px:.1f}" '
                        f'fill="#FDDDD8" stroke="none"/>'
                    )
                for col in range(units_this):
                    x0 = PAD_L + col * col_p_px
                    # Mirror aperture (blue)
                    shapes.append(
                        f'<rect x="{x0:.1f}" y="{y0:.1f}" '
                        f'width="{unit_w_px:.1f}" height="{unit_d_px:.1f}" '
                        f'fill="#A8C8F0" stroke="#4A7EC0" stroke-width="1.5" rx="3"/>'
                    )
                    # Pillar dot
                    cx = x0 + unit_w_px / 2
                    cy = y0 + unit_d_px / 2
                    shapes.append(
                        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" '
                        f'fill="#1E3A6E" opacity="0.7"/>'
                    )

            total_w_px = n_per_string * col_p_px - (col_pitch - UNIT_WIDTH_M) * scale
            total_h_px = n_strings * row_p_px - shadow_px

            # Dimension arrows
            aw = PAD_L + total_w_px   # right edge
            ah = PAD_T + total_h_px   # bottom edge
            dim_y = ah + 18
            dim_x = PAD_L - 22

            html_content = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:transparent;">
<svg width="{SVG_W}" height="{SVG_H}" xmlns="http://www.w3.org/2000/svg"
     style="background:#F5F7FA;border-radius:10px;border:1px solid #DDE3EC;">
  <defs>
    <marker id="ah" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
      <path d="M1,1 L7,4 L1,7 Z" fill="#555"/>
    </marker>
    <marker id="ah2" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto-start-reverse">
      <path d="M1,1 L7,4 L1,7 Z" fill="#555"/>
    </marker>
  </defs>

  {"".join(shapes)}

  <!-- Width dimension line -->
  <line x1="{PAD_L:.0f}" y1="{dim_y:.0f}" x2="{aw:.0f}" y2="{dim_y:.0f}"
        stroke="#555" stroke-width="1" marker-end="url(#ah)" marker-start="url(#ah2)"/>
  <text x="{(PAD_L + aw)/2:.0f}" y="{dim_y + 13:.0f}"
        text-anchor="middle" font-size="12" font-family="sans-serif" fill="#333">
    {field_width_r:.0f} m
  </text>

  <!-- Height dimension line -->
  <line x1="{dim_x:.0f}" y1="{PAD_T:.0f}" x2="{dim_x:.0f}" y2="{ah:.0f}"
        stroke="#555" stroke-width="1" marker-end="url(#ah)" marker-start="url(#ah2)"/>
  <text x="{dim_x - 8:.0f}" y="{(PAD_T + ah)/2:.0f}"
        text-anchor="middle" font-size="12" font-family="sans-serif" fill="#333"
        transform="rotate(-90,{dim_x - 8:.0f},{(PAD_T + ah)/2:.0f})">
    {field_depth_r:.0f} m
  </text>

  <!-- Legend -->
  <rect x="{PAD_L:.0f}" y="{SVG_H - 24:.0f}" width="13" height="13"
        fill="#A8C8F0" stroke="#4A7EC0" stroke-width="1" rx="2"/>
  <text x="{PAD_L + 17:.0f}" y="{SVG_H - 14:.0f}"
        font-size="11" font-family="sans-serif" fill="#444">Mirror aperture</text>
  <rect x="{PAD_L + 118:.0f}" y="{SVG_H - 24:.0f}" width="13" height="13"
        fill="#FDDDD8" rx="2"/>
  <text x="{PAD_L + 135:.0f}" y="{SVG_H - 14:.0f}"
        font-size="11" font-family="sans-serif" fill="#444">Shadow zone</text>
  <circle cx="{PAD_L + 247:.0f}" cy="{SVG_H - 18:.0f}" r="5"
          fill="#1E3A6E" opacity="0.7"/>
  <text x="{PAD_L + 256:.0f}" y="{SVG_H - 14:.0f}"
        font-size="11" font-family="sans-serif" fill="#444">Pillar (1 m²)</text>
</svg>
</body></html>"""

            _components.html(html_content, height=SVG_H + 10, scrolling=False)

        # ── KPI metrics — physical dimensions only ───────────────────
        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total field area",
                  f"{field_width_r:.0f} × {field_depth_r:.0f} m",
                  delta=f"{gross_footprint:,.0f} m² gross footprint")
        m2.metric("Total aperture area",
                  f"{aperture_area:.1f} m²",
                  delta=f"GCR: {gcr_pct:.0f}% of ground area")
        m3.metric("Pillar foundations",
                  f"{n_units} × 1 m²",
                  delta=f"{n_units} m² total foundation area")
        m4.metric("Array layout",
                  f"{n_strings} strings × {n_per_string}",
                  delta=f"Row pitch {row_pitch:.1f} m · Col pitch {col_pitch:.1f} m")

        # ── Detailed spacing table ────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 📏 Spacing & pitch details")
        detail_data = {
            "Parameter": [
                "Unit aperture (LC20)",
                "Unit depth (N–S)",
                "Unit width (E–W)",
                "Row pitch (N–S, centre–centre)",
                "Shadow zone (inter-row gap)",
                "Column pitch (E–W, centre–centre)",
                "Column gap (clear between units)",
                "Shadow-free solar elevation",
                "Strings (rows)",
                "Units per string",
                "Total units",
            ],
            "Value": [
                f"{APERTURE_20} m²",
                f"{UNIT_DEPTH_M} m",
                f"{UNIT_WIDTH_M} m",
                f"{row_pitch:.2f} m  ({spacing_factor:.1f}× depth)",
                f"{shadow_zone:.2f} m",
                f"{col_pitch:.2f} m",
                f"{col_gap:.1f} m",
                f"≥ {max(5, round(90 - math.degrees(math.atan(spacing_factor)), 0)):.0f}°",
                f"{n_strings}",
                f"{n_per_string} (last string: {last_string_units})" if last_string_units != n_per_string else f"{n_per_string}",
                f"{n_units}",
            ]
        }
        st.dataframe(pd.DataFrame(detail_data), use_container_width=True, hide_index=True)

        # ── Summary bar ───────────────────────────────────────────────
        st.markdown("---")
        st.info(
            f"**{n_units} × LC20** | {n_strings} parallel string{'s' if n_strings > 1 else ''} "
            f"of {n_per_string} units in hydraulic series | "
            f"Row pitch: {row_pitch:.1f} m | Column pitch: {col_pitch:.1f} m | "
            f"Shadow-free above **{max(5, round(90 - math.degrees(math.atan(spacing_factor)), 0)):.0f}° solar elevation** | "
            f"Min. spacing factor {spacing_factor:.1f}× depth ({UNIT_DEPTH_M} m) = {row_pitch:.1f} m row pitch"
        )

    st.markdown("---")
    st.markdown("*Helixis Solar Concentrator Calculator - Results generated: " + 
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M") + "*")

else:
    st.info("Upload a GSA Excel report file to continue.")
