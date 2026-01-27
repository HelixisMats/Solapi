# 🚀 Deployment Guide - Helixis Solar Calculator

## Quick Start

### Option 1: New Repository (Recommended)

**1. Create new GitHub repository:**
```
Name: helixis-solar-calculator
Visibility: Public (or Private with Streamlit Teams)
```

**2. Upload files:**
- `solar_dni_thermal_app_final.py`
- `requirements.txt` (rename from solar_requirements.txt)
- `.gitignore` (rename from solar_gitignore.txt)
- `README.md` (rename from SOLAR_README.md)

**3. Deploy on Streamlit Cloud:**
- Go to https://share.streamlit.io/deploy
- Repository: `YourUsername/helixis-solar-calculator`
- Branch: `main`
- Main file: `solar_dni_thermal_app_final.py`

**4. Add passwords in Streamlit Secrets:**
```toml
[passwords]
admin = "YourSecurePassword123"
client1 = "ClientPass456"
demo = "DemoUser789"
```

---

### Option 2: Add to Existing Batterysimulation Repo

**If you want both apps in one repository:**

**1. Add files to repository:**
```bash
cd Batterysimulation
# Copy solar app file
# Update requirements.txt to include openpyxl
```

**2. Update requirements.txt:**
```txt
streamlit>=1.28.0
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
scipy>=1.11.0
requests>=2.31.0
openpyxl>=3.1.0
```

**3. Deploy second app:**
- Go to https://share.streamlit.io/deploy
- Repository: `Eaasymats/Batterysimulation`
- Branch: `main`
- Main file: `solar_dni_thermal_app_final.py`
- App URL: `helixis-solar` (different from battery app)

**Note:** With Streamlit Community Cloud, you can have:
- 1 private app
- Unlimited public apps

So if Batterysimulation is public, you can have both apps!

---

## 🔐 Password Configuration

### Production Passwords

Use strong passwords:
```toml
[passwords]
# Admin access
admin = "Helix!s2024Solar@Secure"

# Client access
client_spain = "Cliente2024!ES"
client_sweden = "Klient2024!SE"

# Demo/trial access
demo = "HelixDemo2024"
```

### Password Best Practices

- Minimum 12 characters
- Mix uppercase, lowercase, numbers, symbols
- Unique per user
- Change regularly
- Document who has which username

---

## 📊 Test Data

To test the app, users need Excel files from:

**Global Solar Atlas:**
1. Go to globalsolaratlas.info
2. Select location
3. Download → PVOUT (Excel format)
4. Upload to app

**Or:**
1. Go to energydata.info
2. Search for solar radiation data
3. Download hourly DNI data
4. Format must have "Hourly_profiles" sheet

---

## 🎯 App URL Examples

After deployment, your app will be at:

**Option 1 (New repo):**
```
https://helixis-solar-calculator.streamlit.app
```

**Option 2 (Same repo, different app):**
```
https://helixis-solar-batterysimulation.streamlit.app
```

---

## 🛠️ Customization

### Change Company Branding

In `solar_dni_thermal_app_final.py`:
```python
st.title("Helixis Solar Concentrator Thermal Production Estimate")
# Change to:
st.title("Your Company Name - Solar Calculator")
```

### Change Unit Sizes

```python
APERTURE_12 = 12.35  # Your 12m² unit size
APERTURE_24 = 24.7   # Your 24m² unit size
```

### Change Currency

Search for `€` and replace with your currency symbol.

---

## 📱 Share with Users

**Email template:**
```
Subject: Access to Helixis Solar Calculator

Hello,

You now have access to our solar thermal production calculator.

App URL: https://your-app-url.streamlit.app
Username: [username]
Password: [password]

The calculator allows you to:
- Upload Global Solar Atlas data
- Configure your system size
- See hourly/daily/monthly production
- Calculate economics and payback

Please keep your credentials secure.

Best regards,
Helixis Team
```

---

## 🔄 Updates

To update the app after changes:

```bash
git add solar_dni_thermal_app_final.py
git commit -m "Update calculation logic"
git push origin main
```

Streamlit Cloud auto-deploys within 1-2 minutes.

---

## ✅ Deployment Checklist

- [ ] Files uploaded to GitHub
- [ ] requirements.txt includes openpyxl
- [ ] .gitignore protects secrets
- [ ] App deployed on Streamlit Cloud
- [ ] Passwords configured in Secrets
- [ ] Login tested
- [ ] Test Excel file uploaded successfully
- [ ] Calculations verified
- [ ] URL shared with users
- [ ] User credentials documented

---

## 🆘 Troubleshooting

**"Module 'openpyxl' not found"**
- Add `openpyxl>=3.1.0` to requirements.txt

**"Cannot read Excel file"**
- Ensure file has "Hourly_profiles" sheet
- Check file format is .xlsx (not .xls)

**"Password not working"**
- Check Secrets are saved correctly
- Ensure no extra spaces in TOML
- Try redeploying app

**"App not loading"**
- Check logs in Streamlit dashboard
- Verify all imports in requirements.txt

---

## 💰 Costs

**Streamlit Community Cloud:**
- Public repos: FREE, unlimited apps
- Private repos: 1 app free, $250/month for more

**If you need multiple private apps:**
- Use Azure App Service (~$13/month, unlimited apps)
- Or make repos public (app still password-protected)

---

**Ready to deploy! 🎉**
