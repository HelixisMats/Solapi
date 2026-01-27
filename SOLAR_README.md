# ☀️ Helixis Solar Concentrator Calculator

Advanced thermal production estimation tool for Helixis solar concentrator systems.

## 🚀 Features

- **DNI Analysis**: Upload Global Solar Atlas data
- **Multiple Sizing Options**: 
  - Peak thermal power (kW)
  - Mirror surface area (m²)
  - Number of 12 m² units
  - Number of 24 m² units
  - Mixed configurations
- **Thermal Calculations**:
  - Hourly power profiles
  - Daily/monthly/annual energy
  - System losses modeling
- **Economic Analysis**:
  - System cost estimation
  - Payback period calculation
  - Annual value projection
- **Password Protected**: Secure access for authorized users

## 📊 Data Input

Upload Excel files from:
- **Global Solar Atlas** (globalsolaratlas.info)
- **Energy Data Info** (energydata.info)

Required sheet: `Hourly_profiles` with DNI data

## 🔐 Deployment

### Local
```bash
pip install -r requirements.txt
streamlit run solar_dni_thermal_app_final.py
```

### Streamlit Cloud
1. Push to GitHub
2. Deploy at share.streamlit.io
3. Add secrets:
```toml
[passwords]
admin = "YourPassword123"
client = "ClientPass456"
```

## 📈 System Parameters

- **12 m² unit**: 12.35 m² aperture
- **24 m² unit**: 24.70 m² aperture
- **Design DNI**: 1000 W/m²
- **Optical efficiency**: Configurable (default 75%)
- **Thermal losses**: Configurable (default 0%)

## 💰 Economic Modeling

- Product cost per unit
- Installation cost estimate
- Energy value (€/kWh)
- Automated payback calculation

## 🛠️ Technical Stack

- **Streamlit**: Web interface
- **Pandas**: Data processing
- **NumPy**: Numerical calculations
- **openpyxl**: Excel file parsing

## 📝 License

Proprietary - Helixis Solar Systems

## 👤 Contact

For support or inquiries, contact Helixis Solar
