
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

        # Calculate actual units needed based on mode
        if base_mode == "Number of 12 m² units":
            actual_units = n12
        elif base_mode == "Number of 24 m² units":
            actual_units = n24
        elif base_mode == "Mix of 12 m² + 24 m² units":
            actual_units = n12 + n24
        else:
            # For "Peak thermal power" or "Mirror surface" modes,
            # calculate most efficient unit configuration
            # Option 1: Use only 12 m² units
            cost_12_only = math.ceil(mirror_area / APERTURE_12)
            # Option 2: Use only 24 m² units
            cost_24_only = math.ceil(mirror_area / APERTURE_24)
            # Choose most efficient (fewer units)
            if cost_24_only <= cost_12_only:
                actual_units = cost_24_only
                actual_unit_type = "24 m²"
            else:
                actual_units = cost_12_only
                actual_unit_type = "12 m²"
        
        # Still calculate theoretical needs for reference
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

        # Use actual units for cost calculation
        total_product_cost = actual_units * item_cost_per_unit
        system_cost = total_product_cost + installation_cost

        st.metric("Units used in calculation", f"{actual_units}")
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
    # SUMMARY SECTION (Always visible at top)
    # ========================================
    
    st.markdown("---")
    st.subheader("📊 Summary Results")
    
    # Calculate lifecycle metrics
    total_20yr_production = annual_system_kwh * 20
    cost_per_kwh_20yr = system_cost / total_20yr_production if total_20yr_production > 0 else 0
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Annual Energy", f"{annual_system_kwh:,.0f} kWh")
    with col2:
        annual_value = annual_system_kwh * price_per_kwh
        st.metric("Annual Value", f"{annual_value:,.0f} €")
    with col3:
        payback_years = system_cost / annual_value if annual_value > 0 else float("inf")
        st.metric("Payback Period", f"{payback_years:.1f} years")
    with col4:
        st.metric("Cost per kWh (20yr)", f"{cost_per_kwh_20yr:.3f} €")
    with col5:
        st.metric("Total Units", f"{actual_units}")
    
    # ========================================
    # DETAILED RESULTS IN TABS
    # ========================================
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Summary Report",
        "🔥 Hourly Profiles", 
        "📆 Monthly Data",
        "📊 Input DNI Data",
        "💾 Export"
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
            st.markdown(f"""
            **Mirror Configuration:**
            - Mirror area: {mirror_area:.2f} m²
            - 12 m² units: {needed_12_round} units
            - 24 m² units: {needed_24_round} units
            - Peak thermal power @ 1000 W/m²: {design_peak_kw:.1f} kW
            """)
        
        with col2:
            st.markdown(f"""
            **Performance Parameters:**
            - Optical efficiency: {eta_opt_pct}%
            - Thermal losses: {thermal_loss_pct}%
            - Peak DNI: {hour_matrix_wh.max().max():.0f} W/m²
            - Average thermal power: {target_peak_kw:.1f} kW
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
            # Calculate 20-year totals
            total_20yr_production = annual_system_kwh * 20
            total_20yr_value = annual_value * 20
            
            st.markdown(f"""
            **Revenue:**
            - Energy price: {price_per_kwh:.2f} €/kWh
            - Annual production: {annual_system_kwh:,.0f} kWh
            - **Annual value: {annual_value:,.0f} €**
            - 20-year production: {total_20yr_production:,.0f} kWh
            - **20-year value: {total_20yr_value:,.0f} €**
            """)
        
        with col3:
            # Calculate lifecycle cost per kWh
            total_20yr_production = annual_system_kwh * 20
            cost_per_kwh_20yr = system_cost / total_20yr_production if total_20yr_production > 0 else 0
            
            st.markdown(f"""
            **Return on Investment:**
            - Payback period: **{payback_years:.1f} years**
            - Annual ROI: **{(annual_value/system_cost*100):.1f}%**
            - **Lifecycle cost: {cost_per_kwh_20yr:.3f} €/kWh** (20 years)
            - Net profit (20 yr): **{(total_20yr_value - system_cost):,.0f} €**
            """)
        
        # Add comparison box
        st.markdown("---")
        st.info(f"""
        💡 **Economic Summary:** Over 20 years, this system produces thermal energy at **{cost_per_kwh_20yr:.3f} €/kWh** 
        (system cost divided by total production). Compared to purchasing energy at **{price_per_kwh:.2f} €/kWh**, 
        you save **{(price_per_kwh - cost_per_kwh_20yr):.3f} €/kWh** or **{((price_per_kwh - cost_per_kwh_20yr)/price_per_kwh*100):.1f}%** per kWh produced.
        """)
    
    # ========================================
    # TAB 2: HOURLY PROFILES
    # ========================================
    
    with tab2:
        st.markdown("### 🔥 Hourly Thermal Power Profiles")
        
        # Direct Power Profile
        st.markdown("#### Direct Power into Media [kW_th]")
        st.table(
            hourly_direct_kw.style
            .format("{:.1f}")
            .set_properties(**{"line-height": "0.5rem", "padding": "2px", "font-size": "11px"})
            .background_gradient(cmap="YlOrRd", axis=0)
        )
        
        # System Power Profile (if losses exist)
        if thermal_loss_frac > 0:
            st.markdown("#### System Power after Loop [kW_th]")
            st.table(
                hourly_system_kw.style
                .format("{:.1f}")
                .set_properties(**{"line-height": "0.5rem", "padding": "2px", "font-size": "11px"})
                .background_gradient(cmap="YlOrRd", axis=0)
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
        
        st.table(
            hour_matrix_wh.style
            .format("{:.0f}")
            .set_properties(**{"line-height": "0.5rem", "padding": "2px", "font-size": "11px"})
            .background_gradient(cmap="YlOrBr", axis=0)
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
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Monthly Production")
            st.download_button(
                "📥 Download Monthly Data (CSV)",
                monthly_system_kwh.to_csv().encode("utf-8"),
                "helixis_monthly_production.csv",
                "text/csv",
                use_container_width=True
            )
            
            st.markdown("#### Hourly Profiles")
            st.download_button(
                "📥 Download Hourly Power (CSV)",
                hourly_system_kw.to_csv().encode("utf-8"),
                "helixis_hourly_power.csv",
                "text/csv",
                use_container_width=True
            )
        
        with col2:
            st.markdown("#### Complete Report")
            # Create summary text file
            summary_text = f"""
HELIXIS SOLAR CONCENTRATOR - PRODUCTION ESTIMATE
================================================

SYSTEM CONFIGURATION
--------------------
Mirror area: {mirror_area:.2f} m²
12 m² units: {needed_12_round}
24 m² units: {needed_24_round}
Optical efficiency: {eta_opt_pct}%
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
    
    st.markdown("---")
    st.markdown("*Helixis Solar Concentrator Calculator - Results generated: " + 
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M") + "*")

else:
    st.info("Upload a GSA Excel report file to continue.")
