
import streamlit as st
import pandas as pd
import numpy as np
import math
from report_generator import generate_report

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
APERTURE_36 = 37.15
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
            "Number of 36 m² units",
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

        n12 = 0
        n24 = 0
        n36 = 0

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

        elif base_mode == "Number of 36 m² units":
            n36 = st.number_input("Number of 36 m² units", min_value=0, value=1)
            mirror_area = n36 * APERTURE_36
            target_peak_kw = mirror_area * peak_kw_per_m2

        elif base_mode == "Mix of units":
            n12 = st.number_input("Number of 12 m² units", min_value=0, value=0)
            n24 = st.number_input("Number of 24 m² units", min_value=0, value=0)
            n36 = st.number_input("Number of 36 m² units", min_value=0, value=1)
            mirror_area = n12 * APERTURE_12 + n24 * APERTURE_24 + n36 * APERTURE_36
            target_peak_kw = mirror_area * peak_kw_per_m2

        needed_12_round = math.ceil(mirror_area / APERTURE_12)
        needed_24_round = math.ceil(mirror_area / APERTURE_24)
        needed_36_round = math.ceil(mirror_area / APERTURE_36)

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
        if base_mode == "Number of 12 m² units":
            actual_n12 = n12
            actual_n24 = 0
            actual_n36 = 0
            total_units = n12
        elif base_mode == "Number of 24 m² units":
            actual_n12 = 0
            actual_n24 = n24
            actual_n36 = 0
            total_units = n24
        elif base_mode == "Number of 36 m² units":
            actual_n12 = 0
            actual_n24 = 0
            actual_n36 = n36
            total_units = n36
        elif base_mode == "Mix of units":
            actual_n12 = n12
            actual_n24 = n24
            actual_n36 = n36
            total_units = n12 + n24 + n36
        else:
            # Peak power or Mirror surface → default to 36 m² units
            actual_n12 = 0
            actual_n24 = 0
            actual_n36 = needed_36_round
            total_units = needed_36_round

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
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📈 Summary Report",
        "🔥 Hourly Profiles", 
        "📆 Monthly Data",
        "📊 Input DNI Data",
        "💾 Export",
        "🌾 Torkning"
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
            if actual_n12 > 0:
                unit_lines += f"            - 12 m² units: {actual_n12} pcs\n"
            if actual_n24 > 0:
                unit_lines += f"            - 24 m² units: {actual_n24} pcs\n"
            if actual_n36 > 0:
                unit_lines += f"            - 36 m² units: {actual_n36} pcs\n"
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
            n12=actual_n12,
            n24=actual_n24,
            n36=actual_n36,
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
            if actual_n12 > 0:
                unit_text += f"12 m² units: {actual_n12}\n"
            if actual_n24 > 0:
                unit_text += f"24 m² units: {actual_n24}\n"
            if actual_n36 > 0:
                unit_text += f"36 m² units: {actual_n36}\n"
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
        st.markdown("### 🌾 Spannmålstorkning – Solvärmeanalys")
        st.markdown(
            "Beräkna hur solvärme, termiskt lager och kompletterande värmekällor "
            "kan möta torkbehovet under skördeperioden."
        )

        # ── Period selection ──────────────────────────────────────
        st.markdown("#### 📅 Torkningsperiod")
        MONTH_ORDER = list(DAYS_IN_MONTH.keys())
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            start_month = st.selectbox(
                "Startmånad", MONTH_ORDER,
                index=MONTH_ORDER.index("Jul"),
                key="dry_start"
            )
        with col_p2:
            end_month = st.selectbox(
                "Slutmånad", MONTH_ORDER,
                index=MONTH_ORDER.index("Aug"),
                key="dry_end"
            )

        start_idx = MONTH_ORDER.index(start_month)
        end_idx   = MONTH_ORDER.index(end_month)
        if end_idx < start_idx:
            st.warning("⚠️ Slutmånad är före startmånad – byt ordning.")
            selected_months = []
        else:
            selected_months = MONTH_ORDER[start_idx : end_idx + 1]
            period_days = sum(DAYS_IN_MONTH[m] for m in selected_months)
            st.info(
                f"**Vald period:** {start_month} – {end_month} "
                f"({len(selected_months)} månader, {period_days} dagar)"
            )

        if selected_months:
            # ── Solar energy in period ───────────────────────────
            period_solar_kwh = float(monthly_system_kwh[selected_months].sum())
            period_daily_kwh = daily_system_kwh[selected_months]

            # ── Drying demand ────────────────────────────────────
            st.markdown("#### ⚡ Torkningsbehov")
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                grain_tonnes = st.number_input(
                    "Säd att torka [ton]", min_value=0.1, value=500.0, step=50.0,
                    key="dry_tonnes"
                )
            with col_d2:
                mc_in = st.number_input(
                    "Inkommande fuktighet [%]", min_value=1.0, max_value=40.0,
                    value=20.0, step=0.5, key="dry_mc_in"
                )
            with col_d3:
                mc_out = st.number_input(
                    "Önskad slutfuktighet [%]", min_value=1.0, max_value=30.0,
                    value=14.0, step=0.5, key="dry_mc_out"
                )

            # Water to remove (wet basis)
            mc_in_f  = mc_in  / 100.0
            mc_out_f = mc_out / 100.0
            water_to_remove_kg = grain_tonnes * 1000.0 * (mc_in_f - mc_out_f) / (1.0 - mc_out_f)
            # Specific energy for hot-air grain drying ≈ 1 000 kWh/ton water (practical value)
            specific_energy_kwh_t = st.slider(
                "Specifik energi för torkning [kWh / ton vatten bortförd]",
                min_value=600, max_value=2000, value=1000, step=50,
                key="dry_specific",
                help="Typiskt 800–1 200 kWh/ton vatten. Lägre värde = effektivare tork."
            )
            total_drying_kwh = (water_to_remove_kg / 1000.0) * specific_energy_kwh_t

            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                st.metric("Vatten att avlägsna", f"{water_to_remove_kg/1000:.1f} ton")
            with col_r2:
                st.metric("Totalt torkbehov", f"{total_drying_kwh:,.0f} kWh")
            with col_r3:
                solar_coverage_pct = min(period_solar_kwh / total_drying_kwh * 100, 100) \
                    if total_drying_kwh > 0 else 0
                st.metric("Solvärme täcker", f"{solar_coverage_pct:.1f} %")

            # ── Thermal storage ──────────────────────────────────
            st.markdown("#### 🔋 Termiskt lager")
            st.markdown(
                "Ett termiskt lager jämnar ut soleffekten över dygnet och minskar "
                "behovet av kompletterande energikällor."
            )
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                storage_kwh = st.number_input(
                    "Lagerkapacitet [kWh]", min_value=0.0, value=200.0, step=10.0,
                    key="dry_storage"
                )
            with col_s2:
                storage_eff = st.slider(
                    "Lagringsverkningsgrad [%]", 50, 99, 90, key="dry_stor_eff"
                ) / 100.0
            with col_s3:
                daily_demand_kwh = total_drying_kwh / period_days if period_days > 0 else 0
                st.metric("Genomsnittligt dagsbehov", f"{daily_demand_kwh:.0f} kWh/dag")

            # Simulate day-by-day storage effect for selected months
            daily_solar_list = []
            for m in selected_months:
                sol_day = float(daily_system_kwh[m])
                for _ in range(DAYS_IN_MONTH[m]):
                    daily_solar_list.append(sol_day)

            soc        = 0.0   # state of charge
            supplied   = []
            charged    = []
            discharged = []
            deficit    = []

            for solar_day in daily_solar_list:
                # 1. Direct solar covers demand
                direct_use = min(solar_day, daily_demand_kwh)
                remaining_solar = solar_day - direct_use
                remaining_demand = daily_demand_kwh - direct_use

                # 2. Charge storage with surplus
                charge = min(remaining_solar, storage_kwh - soc)
                soc += charge
                leftover_solar = remaining_solar - charge

                # 3. Discharge to cover remaining demand
                discharge_need = remaining_demand
                discharge = min(soc * storage_eff, discharge_need)
                soc = max(soc - (discharge / storage_eff if storage_eff > 0 else discharge), 0)
                remaining_demand -= discharge

                total_supplied = direct_use + discharge
                supplied.append(total_supplied)
                charged.append(charge)
                discharged.append(discharge)
                deficit.append(max(remaining_demand, 0))

            total_supplied_kwh  = sum(supplied)
            total_deficit_kwh   = sum(deficit)
            storage_coverage    = min(total_supplied_kwh / total_drying_kwh * 100, 100) \
                if total_drying_kwh > 0 else 0

            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                st.metric(
                    "Sol + lager täcker",
                    f"{storage_coverage:.1f} %",
                    delta=f"+{storage_coverage - solar_coverage_pct:.1f} % vs utan lager"
                )
            with col_t2:
                st.metric("Kvarstående underskott", f"{total_deficit_kwh:,.0f} kWh")
            with col_t3:
                days_deficit = sum(1 for d in deficit if d > 5)
                st.metric("Dagar med underskott (>5 kWh)", f"{days_deficit} dagar")

            # ── Backup heat sources ──────────────────────────────
            st.markdown("#### 🔌 Kompletterande värmekällor")
            col_b1, col_b2 = st.columns(2)

            with col_b1:
                st.markdown("**⚡ Elpatron**")
                use_el = st.checkbox("Inkludera elpatron", value=True, key="dry_use_el")
                el_price = st.number_input(
                    "Elpris [€/kWh]", min_value=0.01, value=0.12, step=0.01,
                    key="dry_el_price"
                ) if use_el else 0.0
                el_capacity_kw = st.number_input(
                    "Elpatroneffekt [kW]", min_value=1.0, value=50.0, step=5.0,
                    key="dry_el_cap"
                ) if use_el else 0.0

            with col_b2:
                st.markdown("**🔄 Värmepump**")
                use_hp = st.checkbox("Inkludera värmepump", value=False, key="dry_use_hp")
                cop = st.number_input(
                    "COP", min_value=1.0, max_value=8.0, value=3.0, step=0.1,
                    key="dry_hp_cop"
                ) if use_hp else 1.0
                hp_price = st.number_input(
                    "Elpris VP [€/kWh]", min_value=0.01, value=0.10, step=0.01,
                    key="dry_hp_price"
                ) if use_hp else 0.0
                hp_capacity_kw = st.number_input(
                    "VP värmeeffekt [kW]", min_value=1.0, value=50.0, step=5.0,
                    key="dry_hp_cap"
                ) if use_hp else 0.0

            # Energy split for deficit
            el_kwh = hp_kwh = 0.0
            if total_deficit_kwh > 0:
                if use_el and use_hp:
                    ratio = el_capacity_kw / (el_capacity_kw + hp_capacity_kw) \
                        if (el_capacity_kw + hp_capacity_kw) > 0 else 0.5
                    el_kwh = total_deficit_kwh * ratio
                    hp_kwh = total_deficit_kwh * (1 - ratio)
                elif use_el:
                    el_kwh = total_deficit_kwh
                elif use_hp:
                    hp_kwh = total_deficit_kwh

            el_cost  = el_kwh * el_price
            hp_el    = hp_kwh / cop if cop > 0 else hp_kwh
            hp_cost  = hp_el * hp_price

            # ── Cost comparison ──────────────────────────────────
            st.markdown("#### 💰 Ekonomisk jämförelse")

            # Reference: all heat from pellets
            pellets_price = st.number_input(
                "Referenspris pellets / olja [€/kWh]", min_value=0.01, value=0.08,
                step=0.01, key="dry_pellets"
            )
            ref_cost_all_pellets = total_drying_kwh * pellets_price

            solar_value       = period_solar_kwh * pellets_price   # avoided cost
            storage_bonus     = (total_supplied_kwh - period_solar_kwh) * pellets_price \
                if total_supplied_kwh > period_solar_kwh else 0
            backup_cost       = el_cost + hp_cost
            total_hybrid_cost = backup_cost   # solar/storage = free after capex

            savings_vs_ref = ref_cost_all_pellets - total_hybrid_cost

            col_e1, col_e2, col_e3 = st.columns(3)
            with col_e1:
                st.metric(
                    "Kostnad – allt med pellets",
                    f"{ref_cost_all_pellets:,.0f} €"
                )
            with col_e2:
                st.metric(
                    "Kostnad – sol + backup",
                    f"{total_hybrid_cost:,.0f} €",
                    delta=f"-{savings_vs_ref:,.0f} € besparing" if savings_vs_ref > 0 else None
                )
            with col_e3:
                st.metric(
                    "Undvikt pelletskostnad (sol)",
                    f"{(period_solar_kwh * pellets_price):,.0f} €"
                )

            # ── Full summary table ────────────────────────────────
            st.markdown("#### 📋 Sammanfattning torkningsanalys")
            summary_data = {
                "Post": [
                    "Totalt torkbehov",
                    "  – Solvärme (direkt)",
                    "  – Termiskt lager (extra)",
                    "  – Elpatron (backup)",
                    "  – Värmepump (backup)",
                    "Täckningsgrad (sol + lager)",
                    "Besparing vs pellets (solenergi)",
                    "Backup-kostnad (el/VP)",
                    "Nettobesparing",
                ],
                "Värde": [
                    f"{total_drying_kwh:,.0f} kWh",
                    f"{period_solar_kwh:,.0f} kWh  ({solar_coverage_pct:.0f} %)",
                    f"{max(total_supplied_kwh - period_solar_kwh, 0):,.0f} kWh",
                    f"{el_kwh:,.0f} kWh" if use_el else "–",
                    f"{hp_kwh:,.0f} kWh  (el: {hp_el:,.0f} kWh)" if use_hp else "–",
                    f"{storage_coverage:.1f} %",
                    f"{period_solar_kwh * pellets_price:,.0f} €",
                    f"{backup_cost:,.0f} €",
                    f"{savings_vs_ref:,.0f} €",
                ]
            }
            st.dataframe(
                pd.DataFrame(summary_data),
                use_container_width=True,
                hide_index=True
            )

            # ── Monthly solar vs demand chart ─────────────────────
            st.markdown("#### 📊 Månatlig solvärme vs torkningsbehov")
            monthly_demand_kwh = total_drying_kwh / len(selected_months) \
                if selected_months else 0

            chart_df = pd.DataFrame({
                "Månad": selected_months,
                "Solvärme [kWh]": [float(monthly_system_kwh[m]) for m in selected_months],
                "Torkningsbehov [kWh]": [monthly_demand_kwh] * len(selected_months),
            })
            st.bar_chart(chart_df.set_index("Månad"), color=["#F4A300", "#2196F3"])

            st.caption(
                "💡 **Tips:** Öka lagerkapaciteten för att utjämna dygnsvariation. "
                "Kombinera med värmepump för lägst driftkostnad under molniga perioder."
            )

    st.markdown("---")
    st.markdown("*Helixis Solar Concentrator Calculator - Results generated: " + 
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M") + "*")

else:
    st.info("Upload a GSA Excel report file to continue.")
