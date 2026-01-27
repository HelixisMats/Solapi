
import streamlit as st
import pandas as pd
import numpy as np
import math

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

APERTURE_12 = 12.35
APERTURE_24 = 24.7
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
            "Number of 12 m² units",
            "Number of 24 m² units",
            "Mix of 12 m² + 24 m² units",
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

        n12 = 0
        n24 = 0

        if base_mode == "Peak thermal power (kW)":
            target_peak_kw = st.number_input("Target peak power [kW]", min_value=0.1, value=100.0)
            mirror_area = target_peak_kw / peak_kw_per_m2

        elif base_mode == "Mirror surface (m²)":
            mirror_area = st.number_input("Mirror area [m²]", min_value=1.0, value=APERTURE_24)
            target_peak_kw = mirror_area * peak_kw_per_m2

        elif base_mode == "Number of 12 m² units":
            n12 = st.number_input("Number of 12 m² units", min_value=0, value=1)
            mirror_area = n12 * APERTURE_12
            target_peak_kw = mirror_area * peak_kw_per_m2

        elif base_mode == "Number of 24 m² units":
            n24 = st.number_input("Number of 24 m² units", min_value=0, value=1)
            mirror_area = n24 * APERTURE_24
            target_peak_kw = mirror_area * peak_kw_per_m2

        elif base_mode == "Mix of 12 m² + 24 m² units":
            n12 = st.number_input("Number of 12 m² units", min_value=0, value=1)
            n24 = st.number_input("Number of 24 m² units", min_value=0, value=1)
            mirror_area = n12 * APERTURE_12 + n24 * APERTURE_24
            target_peak_kw = mirror_area * peak_kw_per_m2

        needed_12_exact = mirror_area / APERTURE_12
        needed_24_exact = mirror_area / APERTURE_24
        needed_12_round = math.ceil(needed_12_exact)
        needed_24_round = math.ceil(needed_24_exact)

        design_peak_kw = mirror_area * (DESIGN_DNI_W_M2 / 1000.0) * eta_opt

        st.subheader("Calculated values")
        st.metric("Mirror area [m²]", f"{mirror_area:,.2f}")
        st.metric("Peak average thermal power [kW]", f"{target_peak_kw:,.2f}")
        st.metric("Peak thermal power @ 1000 W/m² [kW]", f"{design_peak_kw:,.2f}")

        st.header("💰 Economic Parameters")

        price_per_kwh = st.number_input("Value of thermal energy [€/kWh]", min_value=0.0, value=0.10)

        item_cost_per_unit = st.number_input("Product cost [€ / unit]", min_value=0.0, value=15000.0)
        installation_cost = st.number_input("Estimated installation cost [€]", min_value=0.0, value=20000.0)

        total_units = needed_12_round + needed_24_round
        total_product_cost = total_units * item_cost_per_unit
        system_cost = total_product_cost + installation_cost

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

    st.subheader(" DNI Hourly Profile (Input Data)")
    st.table(hour_matrix_wh.style.format("{:.0f}"))

    st.subheader(" Thermal Power Profile – Direct into Media [kW_th] (Heatmap)")
    st.table(
        hourly_direct_kw.style
        .format("{:.1f}")
        .set_properties(**{"line-height": "0.5rem", "padding": "1px"})
        .background_gradient(cmap="YlOrRd", axis=0)
    )

    if thermal_loss_frac > 0:
        st.subheader(" Thermal Power Profile – System after Loop [kW_th] (Heatmap)")
        st.table(
            hourly_system_kw.style
            .format("{:.1f}")
            .set_properties(**{"line-height": "0.5rem", "padding": "1px"})
            .background_gradient(cmap="YlOrRd", axis=0)
        )

    st.subheader("🔥 Estimated Daily Thermal Energy [kWh/day]")
    st.table(
        pd.DataFrame({
            "Direct": daily_direct_kwh,
            "System": daily_system_kwh
        }).round(1)
    )

    st.subheader("📆 Monthly and Annual Thermal Energy [kWh]")
    st.table(
        pd.DataFrame({
            "Direct": monthly_direct_kwh,
            "System": monthly_system_kwh
        }).round(0)
    )

    st.metric("Annual direct thermal energy [kWh/year]", f"{annual_direct_kwh:,.0f}")
    st.metric("Annual system thermal energy [kWh/year]", f"{annual_system_kwh:,.0f}")

    annual_value = annual_system_kwh * price_per_kwh
    payback_years = system_cost / annual_value if annual_value > 0 else float("inf")

    st.subheader("💰 Economic Evaluation")
    st.metric("Annual economic value [€]", f"{annual_value:,.0f}")
    st.metric("Estimated payback period [years]", f"{payback_years:,.1f}")

    st.subheader("🛰️ Required Number of Concentrators")
    st.write(f"**12 m² units needed:** {needed_12_round} _(exact: {needed_12_exact:.2f})_")
    st.write(f"**24 m² units needed:** {needed_24_round} _(exact: {needed_24_exact:.2f})_")

    st.download_button(
        "📥 Download monthly thermal production (CSV)",
        monthly_system_kwh.to_csv().encode("utf-8"),
        "thermal_monthly_production.csv",
        "text/csv",
    )

else:
    st.info("Upload a GSA Excel report file to continue.")
