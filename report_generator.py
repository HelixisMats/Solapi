"""
Helixis Solar Concentrator – PDF Report Generator
===================================================
Generates a professional multi-page PDF report from the thermal
production estimate data.  Drop this file next to the Streamlit app
and call  `generate_report(...)` to get the PDF bytes back.
"""

import io
import datetime
import math

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether, Image,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics import renderPDF

# ─── Colour palette ────────────────────────────────────────────────
BRAND_DARK   = colors.HexColor("#1B2A4A")
BRAND_ACCENT = colors.HexColor("#E8740C")
BRAND_LIGHT  = colors.HexColor("#F5F6FA")
BRAND_GREEN  = colors.HexColor("#27AE60")
BRAND_GREY   = colors.HexColor("#7F8C8D")
WHITE        = colors.white
BLACK        = colors.black

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# ─── Custom styles ──────────────────────────────────────────────────
def _build_styles():
    ss = getSampleStyleSheet()

    ss.add(ParagraphStyle(
        "CoverTitle", parent=ss["Title"],
        fontSize=28, leading=34, textColor=WHITE,
        alignment=TA_CENTER, spaceAfter=6 * mm,
    ))
    ss.add(ParagraphStyle(
        "CoverSub", parent=ss["Normal"],
        fontSize=14, leading=18, textColor=colors.HexColor("#CBD5E1"),
        alignment=TA_CENTER, spaceAfter=3 * mm,
    ))
    ss.add(ParagraphStyle(
        "SectionTitle", parent=ss["Heading1"],
        fontSize=16, leading=20, textColor=BRAND_DARK,
        spaceBefore=10 * mm, spaceAfter=4 * mm,
        borderPadding=(0, 0, 2, 0),
    ))
    ss.add(ParagraphStyle(
        "SubSection", parent=ss["Heading2"],
        fontSize=12, leading=15, textColor=BRAND_DARK,
        spaceBefore=6 * mm, spaceAfter=3 * mm,
    ))
    ss.add(ParagraphStyle(
        "BodyText2", parent=ss["Normal"],
        fontSize=9.5, leading=13, textColor=colors.HexColor("#2C3E50"),
    ))
    ss.add(ParagraphStyle(
        "SmallGrey", parent=ss["Normal"],
        fontSize=8, leading=10, textColor=BRAND_GREY,
        alignment=TA_CENTER,
    ))
    ss.add(ParagraphStyle(
        "KPILabel", parent=ss["Normal"],
        fontSize=8, leading=10, textColor=BRAND_GREY,
        alignment=TA_CENTER,
    ))
    ss.add(ParagraphStyle(
        "KPIValue", parent=ss["Normal"],
        fontSize=18, leading=22, textColor=BRAND_DARK,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    ))
    return ss


# ─── Helper: KPI card row ──────────────────────────────────────────
def _kpi_row(items, styles):
    header_cells = [Paragraph(lbl, styles["KPILabel"]) for lbl, _ in items]
    value_cells  = [Paragraph(val, styles["KPIValue"]) for _, val in items]

    n = len(items)
    col_w = CONTENT_W / n

    t = Table([value_cells, header_cells], colWidths=[col_w] * n)
    t.setStyle(TableStyle([
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("BOX",        (0, 0), (-1, -1), 0.5, colors.HexColor("#DEE2E6")),
        ("INNERGRID",  (0, 0), (-1, -1), 0.5, colors.HexColor("#DEE2E6")),
    ]))
    return t


# ─── Helper: styled data table ─────────────────────────────────────
def _data_table(headers, rows, col_widths=None):
    hdr = [Paragraph(f"<b>{h}</b>", ParagraphStyle(
        "TH", fontSize=8, leading=10, textColor=WHITE, alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )) for h in headers]

    body_style = ParagraphStyle("TD", fontSize=8, leading=10, alignment=TA_CENTER)

    body = []
    for row in rows:
        body.append([Paragraph(str(c), body_style) for c in row])

    data = [hdr] + body
    n = len(headers)
    if col_widths is None:
        col_widths = [CONTENT_W / n] * n

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#DEE2E6")),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, BRAND_LIGHT]),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


# ─── Helper: matplotlib heatmap → ReportLab Image ──────────────────
def _heatmap_image(df, title, unit_label, cmap="YlOrRd",
                   fig_width_mm=170, fig_height_mm=90):
    """
    Render a pandas DataFrame as a colour heatmap using matplotlib
    and return a ReportLab Image flowable.
    Rows = hours, Columns = months.
    """
    data = df.values.astype(float)
    row_labels = [str(r) for r in df.index]
    col_labels = [str(c) for c in df.columns]

    # Drop all-zero rows (night hours)
    nonzero_mask = data.max(axis=1) > 0
    data = data[nonzero_mask]
    row_labels = [l for l, m in zip(row_labels, nonzero_mask) if m]

    nrows, ncols = data.shape

    fig_w_in = fig_width_mm / 25.4
    fig_h_in = max(fig_height_mm / 25.4, nrows * 0.22 + 0.8)

    fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in))

    im = ax.imshow(data, aspect="auto", cmap=cmap,
                   interpolation="nearest",
                   vmin=0, vmax=data.max() if data.max() > 0 else 1)

    # Axes labels
    ax.set_xticks(range(ncols))
    ax.set_xticklabels(col_labels, fontsize=7)
    ax.set_yticks(range(nrows))
    ax.set_yticklabels(row_labels, fontsize=6.5)
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")

    # Value annotations (only if cells are big enough)
    if nrows <= 18 and ncols <= 12:
        thresh = data.max() * 0.55
        for r in range(nrows):
            for c in range(ncols):
                v = data[r, c]
                txt_color = "white" if v > thresh else "#333333"
                ax.text(c, r, f"{v:.0f}", ha="center", va="center",
                        fontsize=5.5, color=txt_color)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.03)
    cbar.ax.tick_params(labelsize=6)
    cbar.set_label(unit_label, fontsize=7)

    ax.set_title(title, fontsize=9, fontweight="bold",
                 color="#1B2A4A", pad=8)

    fig.tight_layout(pad=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    img_w = fig_width_mm * mm
    # Maintain aspect ratio
    img_h = fig_h_in / fig_w_in * img_w

    return Image(buf, width=img_w, height=img_h)


# ─── Helper: bar chart ─────────────────────────────────────────────
def _monthly_bar_chart(months, direct_vals, system_vals, title_text=""):
    dw, dh = 480, 220
    d = Drawing(dw, dh)

    chart = VerticalBarChart()
    chart.x = 50
    chart.y = 40
    chart.width = dw - 80
    chart.height = dh - 70
    chart.data = [list(direct_vals), list(system_vals)]
    chart.categoryAxis.categoryNames = list(months)
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = "%0.0f"
    chart.bars[0].fillColor = BRAND_ACCENT
    chart.bars[1].fillColor = BRAND_DARK
    chart.bars.strokeWidth = 0
    chart.barSpacing = 1
    chart.groupSpacing = 6

    legend = Legend()
    legend.x = dw / 2 - 80
    legend.y = dh - 12
    legend.fontSize = 8
    legend.alignment = "right"
    legend.columnMaximum = 1
    legend.colorNamePairs = [
        (BRAND_ACCENT, "Direct Energy"),
        (BRAND_DARK,   "System Energy"),
    ]
    d.add(chart)
    d.add(legend)

    if title_text:
        d.add(String(dw / 2, dh - 2, title_text,
                      fontSize=10, fillColor=BRAND_DARK,
                      textAnchor="middle", fontName="Helvetica-Bold"))
    return d


# ─── Helper: monthly value bar chart ──────────────────────────────
def _monthly_value_chart(months, values, title_text=""):
    """Single-series bar chart for monthly economic value."""
    dw, dh = 480, 200
    d = Drawing(dw, dh)

    chart = VerticalBarChart()
    chart.x = 50
    chart.y = 35
    chart.width = dw - 80
    chart.height = dh - 60
    chart.data = [list(values)]
    chart.categoryAxis.categoryNames = list(months)
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = "%0.0f"
    chart.bars[0].fillColor = BRAND_GREEN
    chart.bars.strokeWidth = 0
    chart.barSpacing = 2
    chart.groupSpacing = 8

    d.add(chart)
    if title_text:
        d.add(String(dw / 2, dh - 2, title_text,
                      fontSize=10, fillColor=BRAND_DARK,
                      textAnchor="middle", fontName="Helvetica-Bold"))
    return d


# ─── Helper: cumulative cash-flow line chart ───────────────────────
def _cashflow_chart(annual_value, system_cost, lifetime_years):
    """Line chart showing cumulative revenue vs system cost break-even."""
    years = list(range(0, lifetime_years + 1))
    cum_revenue = [annual_value * y for y in years]
    cost_line   = [system_cost] * len(years)

    dw, dh = 480, 200
    d = Drawing(dw, dh)

    chart = LinePlot()
    chart.x = 50
    chart.y = 35
    chart.width = dw - 80
    chart.height = dh - 60
    chart.data = [
        list(zip(years, cum_revenue)),
        list(zip(years, cost_line)),
    ]
    chart.lines[0].strokeColor = BRAND_GREEN
    chart.lines[0].strokeWidth = 2
    chart.lines[1].strokeColor = BRAND_ACCENT
    chart.lines[1].strokeWidth = 1.5
    chart.lines[1].strokeDashArray = [4, 3]

    chart.xValueAxis.valueMin = 0
    chart.xValueAxis.valueMax = lifetime_years
    chart.xValueAxis.labels.fontSize = 7
    chart.yValueAxis.valueMin = 0
    chart.yValueAxis.labels.fontSize = 7
    chart.yValueAxis.labelTextFormat = "%0.0f"

    legend = Legend()
    legend.x = dw / 2 - 90
    legend.y = dh - 12
    legend.fontSize = 8
    legend.alignment = "right"
    legend.colorNamePairs = [
        (BRAND_GREEN,  "Cumulative Revenue"),
        (BRAND_ACCENT, "System Cost"),
    ]
    d.add(chart)
    d.add(legend)
    d.add(String(dw / 2, dh - 2,
                  "Cumulative Cash Flow [EUR]",
                  fontSize=10, fillColor=BRAND_DARK,
                  textAnchor="middle", fontName="Helvetica-Bold"))
    return d


# ─── Page templates (header / footer) ──────────────────────────────
def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(BRAND_ACCENT)
    canvas.setLineWidth(1.5)
    canvas.line(MARGIN, PAGE_H - 14 * mm, PAGE_W - MARGIN, PAGE_H - 14 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(BRAND_DARK)
    canvas.drawString(MARGIN, PAGE_H - 12 * mm, "HELIXIS SOLAR CONCENTRATOR")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(BRAND_GREY)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 12 * mm,
                           "Thermal Production Estimate")

    canvas.setStrokeColor(colors.HexColor("#DEE2E6"))
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 12 * mm, PAGE_W - MARGIN, 12 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(BRAND_GREY)
    canvas.drawString(MARGIN, 8 * mm,
                      f"Generated {datetime.datetime.now():%Y-%m-%d %H:%M}")
    canvas.drawRightString(PAGE_W - MARGIN, 8 * mm,
                           f"Page {doc.page}")
    canvas.restoreState()


def _cover_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BRAND_DARK)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(BRAND_ACCENT)
    canvas.rect(0, PAGE_H * 0.42, PAGE_W, 4 * mm, fill=1, stroke=0)
    canvas.restoreState()


# ─── Main entry point ──────────────────────────────────────────────
def generate_report(
    # System sizing
    mirror_area: float,
    n12: int,
    n24: int,
    n36: int,
    eta_opt_pct: float,
    thermal_loss_pct: float,
    design_peak_kw: float,
    target_peak_kw: float,
    # Energy data
    annual_direct_kwh: float,
    annual_system_kwh: float,
    monthly_direct_kwh: pd.Series,
    monthly_system_kwh: pd.Series,
    daily_direct_kwh: pd.Series,
    daily_system_kwh: pd.Series,
    hourly_direct_kw: pd.DataFrame,
    hourly_system_kw: pd.DataFrame,
    hour_matrix_wh: pd.DataFrame,
    monthly_kwh_m2: pd.Series,
    annual_kwh_m2: float,
    # Economics
    price_per_kwh: float,
    system_cost: float,
    total_product_cost: float,
    installation_cost: float,
    annual_value: float,
    payback_years: float,
    lcoe: float = 0.0,
    system_lifetime_years: int = 25,
    # Optional metadata
    project_name: str = "",
    location: str = "",
    notes: str = "",
) -> bytes:
    """Build the full PDF report and return it as bytes."""

    buf = io.BytesIO()
    styles = _build_styles()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=20 * mm, bottomMargin=18 * mm,
        title="Helixis Solar Report",
        author="Helixis Solar Calculator",
    )

    story: list = []

    # ================================================================
    # COVER PAGE
    # ================================================================
    story.append(Spacer(1, 60 * mm))
    story.append(Paragraph("HELIXIS", styles["CoverTitle"]))
    story.append(Paragraph("Solar Concentrator", styles["CoverSub"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Thermal Production Estimate", styles["CoverSub"]))
    story.append(Spacer(1, 20 * mm))

    if project_name:
        story.append(Paragraph(project_name, styles["CoverSub"]))
    if location:
        story.append(Paragraph(location, styles["CoverSub"]))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        f"Report generated {datetime.datetime.now():%Y-%m-%d}",
        styles["CoverSub"],
    ))
    story.append(PageBreak())

    # ================================================================
    # 1. EXECUTIVE SUMMARY
    # ================================================================
    story.append(Paragraph("1 &nbsp; Executive Summary", styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_ACCENT,
                             spaceAfter=4 * mm))

    roi_pct = (annual_value / system_cost * 100) if system_cost > 0 else 0
    lifetime_value = annual_value * system_lifetime_years

    story.append(_kpi_row([
        ("Annual System Energy", f"{annual_system_kwh:,.0f} kWh"),
        ("Annual Value",         f"{annual_value:,.0f} \u20ac"),
        ("Payback Period",       f"{payback_years:.1f} yr"),
        ("LCOE ({0} yr)".format(system_lifetime_years), f"{lcoe:.4f} \u20ac/kWh"),
        ("{0}-Year Value".format(system_lifetime_years), f"{lifetime_value:,.0f} \u20ac"),
    ], styles))
    story.append(Spacer(1, 6 * mm))

    unit_parts = []
    if n12 > 0:
        unit_parts.append(f"{n12} x 12 m<super>2</super>")
    if n24 > 0:
        unit_parts.append(f"{n24} x 24 m<super>2</super>")
    if n36 > 0:
        unit_parts.append(f"{n36} x 36 m<super>2</super>")
    unit_desc = " + ".join(unit_parts) + " units" if unit_parts else "custom area"

    summary_text = (
        f"The proposed Helixis solar concentrator system comprises "
        f"<b>{mirror_area:,.1f} m<super>2</super></b> of mirror aperture area "
        f"({unit_desc}) "
        f"with an optical efficiency of <b>{eta_opt_pct:.0f}%</b> and "
        f"thermal loop losses of <b>{thermal_loss_pct:.0f}%</b>. "
        f"At design-point DNI (1 000 W/m<super>2</super>) the system delivers "
        f"a peak thermal power of <b>{design_peak_kw:,.1f} kW</b>. "
        f"Based on site-specific hourly DNI profiles the estimated annual "
        f"useful thermal energy is <b>{annual_system_kwh:,.0f} kWh</b>, "
        f"resulting in an annual economic value of <b>{annual_value:,.0f} \u20ac</b> "
        f"and a simple payback period of <b>{payback_years:.1f} years</b>. "
        f"The levelized cost of energy (LCOE) over {system_lifetime_years} years is "
        f"<b>{lcoe:.4f} \u20ac/kWh</b>."
    )
    story.append(Paragraph(summary_text, styles["BodyText2"]))
    story.append(Spacer(1, 4 * mm))

    if notes:
        story.append(Paragraph(f"<i>Notes: {notes}</i>", styles["BodyText2"]))
        story.append(Spacer(1, 4 * mm))

    # ================================================================
    # 2. SYSTEM CONFIGURATION
    # ================================================================
    story.append(Paragraph("2 &nbsp; System Configuration", styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_ACCENT,
                             spaceAfter=4 * mm))

    config_headers = ["Parameter", "Value"]
    config_rows = [
        ["Total mirror aperture area",    f"{mirror_area:,.2f} m\u00b2"],
    ]
    if n12 > 0:
        config_rows.append(["12 m\u00b2 units", f"{n12} pcs"])
    if n24 > 0:
        config_rows.append(["24 m\u00b2 units", f"{n24} pcs"])
    if n36 > 0:
        config_rows.append(["36 m\u00b2 units", f"{n36} pcs"])
    config_rows += [
        ["Optical efficiency",            f"{eta_opt_pct:.0f} %"],
        ["Thermal loop losses",           f"{thermal_loss_pct:.0f} %"],
        ["Peak thermal power (design @ 1000 W/m\u00b2)", f"{design_peak_kw:,.1f} kW"],
        ["Peak thermal power (from site DNI)",            f"{target_peak_kw:,.1f} kW"],
        ["Annual DNI",                    f"{annual_kwh_m2:.0f} kWh/m\u00b2"],
        ["Peak DNI",                      f"{hour_matrix_wh.max().max():.0f} W/m\u00b2"],
        ["Best solar month",              str(monthly_kwh_m2.idxmax())],
    ]
    cw = [CONTENT_W * 0.60, CONTENT_W * 0.40]
    story.append(_data_table(config_headers, config_rows, col_widths=cw))
    story.append(Spacer(1, 6 * mm))

    # ================================================================
    # 3. MONTHLY ENERGY PRODUCTION
    # ================================================================
    story.append(Paragraph("3 &nbsp; Monthly Energy Production", styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_ACCENT,
                             spaceAfter=4 * mm))

    months = list(monthly_direct_kwh.index)
    econ_monthly = monthly_system_kwh.values * price_per_kwh
    dni_monthly  = monthly_kwh_m2.values

    energy_headers = ["Month", "DNI [kWh/m\u00b2]", "Direct [kWh]",
                       "System [kWh]", "Value [\u20ac]"]
    energy_rows = []
    for i, m in enumerate(months):
        energy_rows.append([
            m,
            f"{dni_monthly[i]:,.1f}",
            f"{monthly_direct_kwh.values[i]:,.0f}",
            f"{monthly_system_kwh.values[i]:,.0f}",
            f"{econ_monthly[i]:,.0f}",
        ])
    energy_rows.append([
        "TOTAL",
        f"{annual_kwh_m2:,.1f}",
        f"{annual_direct_kwh:,.0f}",
        f"{annual_system_kwh:,.0f}",
        f"{annual_value:,.0f}",
    ])

    ew = CONTENT_W / 5
    story.append(_data_table(energy_headers, energy_rows, col_widths=[ew] * 5))
    story.append(Spacer(1, 6 * mm))

    # Bar chart – monthly energy
    story.append(_monthly_bar_chart(
        months,
        monthly_direct_kwh.values,
        monthly_system_kwh.values,
        title_text="Monthly Energy Production [kWh]",
    ))
    story.append(Spacer(1, 4 * mm))

    # Bar chart – monthly value
    story.append(_monthly_value_chart(
        months,
        econ_monthly,
        title_text="Monthly Economic Value [\u20ac]",
    ))

    # ================================================================
    # 4. ECONOMIC ANALYSIS
    # ================================================================
    story.append(PageBreak())
    story.append(Paragraph("4 &nbsp; Economic Analysis", styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_ACCENT,
                             spaceAfter=4 * mm))

    story.append(_kpi_row([
        ("System Cost",    f"{system_cost:,.0f} \u20ac"),
        ("Annual Revenue", f"{annual_value:,.0f} \u20ac"),
        ("Payback",        f"{payback_years:.1f} yr"),
        ("LCOE ({0} yr)".format(system_lifetime_years), f"{lcoe:.4f} \u20ac/kWh"),
        ("Annual ROI",     f"{roi_pct:.1f} %"),
    ], styles))
    story.append(Spacer(1, 6 * mm))

    econ_headers = ["Item", "Value"]
    econ_rows = [
        ["Product cost",              f"{total_product_cost:,.0f} \u20ac"],
        ["Installation cost",         f"{installation_cost:,.0f} \u20ac"],
        ["Total system cost",         f"{system_cost:,.0f} \u20ac"],
        ["Energy price",              f"{price_per_kwh:.2f} \u20ac/kWh"],
        ["Annual system production",  f"{annual_system_kwh:,.0f} kWh"],
        ["Annual economic value",     f"{annual_value:,.0f} \u20ac"],
        ["Simple payback period",     f"{payback_years:.1f} years"],
        ["LCOE ({0} yr lifetime)".format(system_lifetime_years), f"{lcoe:.4f} \u20ac/kWh"],
        ["Annual ROI",                f"{roi_pct:.1f} %"],
        ["{0}-year cumulative value".format(system_lifetime_years),
         f"{lifetime_value:,.0f} \u20ac"],
    ]
    story.append(_data_table(econ_headers, econ_rows, col_widths=cw))
    story.append(Spacer(1, 6 * mm))

    # Cumulative cash-flow chart
    story.append(_cashflow_chart(annual_value, system_cost, system_lifetime_years))
    story.append(Spacer(1, 6 * mm))

    # Cumulative cash-flow table
    story.append(Paragraph("Cumulative Cash Flow", styles["SubSection"]))
    cf_headers = ["Year", "Cumulative Revenue [\u20ac]", "Net Position [\u20ac]"]
    cf_rows = []
    cf_years = sorted(set([1, 2, 3, 5, 10, 15, 20, system_lifetime_years]))
    for yr in cf_years:
        cum_rev = annual_value * yr
        net = cum_rev - system_cost
        cf_rows.append([str(yr), f"{cum_rev:,.0f}",
                         f"{net:+,.0f}"])
    cf_w = CONTENT_W / 3
    story.append(_data_table(cf_headers, cf_rows, col_widths=[cf_w] * 3))

    # ================================================================
    # 5. DAILY ENERGY TOTALS
    # ================================================================
    story.append(PageBreak())
    story.append(Paragraph("5 &nbsp; Daily Energy Totals", styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_ACCENT,
                             spaceAfter=4 * mm))

    daily_headers = ["Month", "Direct [kWh/day]", "System [kWh/day]",
                      "Value [\u20ac/day]"]
    daily_rows = []
    for i, m in enumerate(months):
        daily_val = daily_system_kwh.values[i] * price_per_kwh
        daily_rows.append([
            m,
            f"{daily_direct_kwh.values[i]:,.1f}",
            f"{daily_system_kwh.values[i]:,.1f}",
            f"{daily_val:,.2f}",
        ])
    dw_col = CONTENT_W / 4
    story.append(_data_table(daily_headers, daily_rows, col_widths=[dw_col] * 4))
    story.append(Spacer(1, 6 * mm))

    # ================================================================
    # 6. DNI INPUT DATA + HEATMAP
    # ================================================================
    story.append(Paragraph("6 &nbsp; Solar DNI Input Data", styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_ACCENT,
                             spaceAfter=4 * mm))

    story.append(Paragraph(
        f"Peak DNI: <b>{hour_matrix_wh.max().max():.0f} W/m<super>2</super></b>"
        f" &nbsp;|&nbsp; "
        f"Annual DNI: <b>{annual_kwh_m2:.0f} kWh/m<super>2</super></b>"
        f" &nbsp;|&nbsp; "
        f"Best month: <b>{monthly_kwh_m2.idxmax()}</b>",
        styles["BodyText2"],
    ))
    story.append(Spacer(1, 4 * mm))

    # DNI heatmap
    story.append(Paragraph(
        "Hourly DNI Heatmap [W/m<super>2</super>]  "
        "<i>(rows = hours, columns = months)</i>",
        styles["SubSection"],
    ))
    story.append(_heatmap_image(
        hour_matrix_wh,
        title="DNI – Hourly Profile [W/m²]",
        unit_label="W/m²",
        cmap="YlOrBr",
        fig_width_mm=170,
        fig_height_mm=110,
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "The table below lists the raw hourly DNI values [W/m\u00b2].",
        styles["BodyText2"],
    ))
    story.append(Spacer(1, 3 * mm))

    # DNI numeric table
    dni_month_headers = ["Hour"] + list(hour_matrix_wh.columns)
    dni_rows = []
    for h in hour_matrix_wh.index:
        row_vals = hour_matrix_wh.loc[h]
        if row_vals.max() == 0:
            continue
        dni_rows.append([str(h)] + [f"{v:.0f}" for v in row_vals])
    n_cols = len(dni_month_headers)
    first_w = 22 * mm
    rest_w  = (CONTENT_W - first_w) / (n_cols - 1)
    story.append(_data_table(
        dni_month_headers, dni_rows,
        col_widths=[first_w] + [rest_w] * (n_cols - 1),
    ))

    # ================================================================
    # 7. HOURLY THERMAL PROFILES + HEATMAPS
    # ================================================================
    story.append(PageBreak())
    story.append(Paragraph("7 &nbsp; Hourly Thermal Power Profiles",
                             styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_ACCENT,
                             spaceAfter=4 * mm))

    # 7a – Direct power heatmap
    story.append(Paragraph("Direct Thermal Power Heatmap [kW<sub>th</sub>]",
                             styles["SubSection"]))
    story.append(_heatmap_image(
        hourly_direct_kw.round(1),
        title="Direct Thermal Power [kW]",
        unit_label="kW",
        cmap="YlOrRd",
        fig_width_mm=170,
        fig_height_mm=110,
    ))
    story.append(Spacer(1, 4 * mm))

    # 7b – Direct power table
    story.append(Paragraph(
        "Direct Thermal Power – numeric table [kW]", styles["BodyText2"]
    ))
    story.append(Spacer(1, 3 * mm))
    tbl_headers = ["Hour"] + list(hourly_direct_kw.columns)
    tbl_rows = []
    for h in hourly_direct_kw.index:
        row_vals = hourly_direct_kw.loc[h]
        if row_vals.max() == 0:
            continue
        tbl_rows.append([str(h)] + [f"{v:.1f}" for v in row_vals])
    n_c = len(tbl_headers)
    f_w = 22 * mm
    r_w = (CONTENT_W - f_w) / (n_c - 1)
    story.append(_data_table(
        tbl_headers, tbl_rows,
        col_widths=[f_w] + [r_w] * (n_c - 1),
    ))

    # 7c – System power (if losses > 0)
    if thermal_loss_pct > 0:
        story.append(PageBreak())
        story.append(Paragraph(
            "System Thermal Power after Loop Losses [kW<sub>th</sub>]",
            styles["SubSection"],
        ))
        story.append(_heatmap_image(
            hourly_system_kw.round(1),
            title=f"System Thermal Power [kW]  (after {thermal_loss_pct:.0f}% loop losses)",
            unit_label="kW",
            cmap="YlOrRd",
            fig_width_mm=170,
            fig_height_mm=110,
        ))
        story.append(Spacer(1, 4 * mm))

        sys_tbl_rows = []
        for h in hourly_system_kw.index:
            row_vals = hourly_system_kw.loc[h]
            if row_vals.max() == 0:
                continue
            sys_tbl_rows.append([str(h)] + [f"{v:.1f}" for v in row_vals])
        story.append(_data_table(
            tbl_headers, sys_tbl_rows,
            col_widths=[f_w] + [r_w] * (n_c - 1),
        ))

    # ================================================================
    # DISCLAIMER
    # ================================================================
    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_GREY))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "<i>Disclaimer — This report is an estimate based on typical meteorological "
        "year data and simplified thermal models. Actual performance may vary due to "
        "local weather conditions, shading, soiling, and installation-specific factors. "
        "This document does not constitute a guarantee of performance.</i>",
        styles["SmallGrey"],
    ))

    # ── Build ───────────────────────────────────────────────────────
    doc.build(
        story,
        onFirstPage=_cover_background,
        onLaterPages=_header_footer,
    )
    return buf.getvalue()
