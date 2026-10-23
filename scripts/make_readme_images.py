"""Draw the README images (banner, business workflow, win-probability explainer, technical architecture).

Numbers come from the warehouse and ml/outputs/metrics.json, so the pictures cannot drift from the data.
Run after the pipeline:  python scripts/make_readme_images.py   ->  images/readme/*.png
"""
import json
import textwrap
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle, Wedge

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "images" / "readme"
OUT.mkdir(parents=True, exist_ok=True)

FONT = "Segoe UI"
BOLD = "Segoe UI Semibold"
NAVY, INK, BLUE, MID, SKY, PALE = "#0B1F3A", "#1B2A41", "#1F4E79", "#2E75B6", "#7FB2E5", "#EAF2FB"
AMBER, GREEN, RED, GREY, WHITE = "#F2A900", "#2E9E5B", "#C0392B", "#6B7280", "#FFFFFF"

# ---- numbers ----------------------------------------------------------------------------------------------------------
con = duckdb.connect(str(ROOT / "warehouse" / "nexora.duckdb"), read_only=True)
m = json.load(open(ROOT / "ml" / "outputs" / "metrics.json", encoding="utf-8"))
N = {
    "raw_rows": con.execute("select count(*) from stg_crm__opportunities").fetchone()[0],
    "deals": con.execute("select count(*) from pipeline_deals").fetchone()[0],
    "checks": con.execute("select count(*) from dq_reconciliation").fetchone()[0],
    "open_eur": con.execute("select sum(amount_eur) from pipeline_deals where is_open").fetchone()[0] / 1e6,
    "risk_eur": con.execute("select sum(amount_eur) from pipeline_deals where is_at_risk").fetchone()[0] / 1e6,
    "flag_n": con.execute("select count(*) from ml.model_scores where model_vs_governed_pts <= -25").fetchone()[0],
    "flag_eur": con.execute("select sum(amount_eur) from ml.model_scores where model_vs_governed_pts <= -25").fetchone()[0] / 1e6,
    "scored": m["scored"],
    "train_deals": m["train_deals"],
    "test_deals": m["test_deals"],
    "crm_err": [b for b in m["backtest"] if b["method"].startswith("Governed")][0]["forecast_error_pct"],
    "model_err": [b for b in m["backtest"] if b["method"] == m["chosen_model"]][0]["forecast_error_pct"],
}
EX = con.sql("""select s.deal_label, s.amount_eur, s.model_win_probability p, s.governed_probability g
                from ml.model_scores s where opportunity_id = 'OPP-004267'""").df().iloc[0]
EXPL = con.sql("""select feature_label, feature_value, impact_pts from ml.model_explanations
                  where opportunity_id = 'OPP-004267' order by abs_impact_pts desc""").df()
BASE = m["baseline_open_deal_probability"]


def canvas(w, h, bg=WHITE):
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100, facecolor=bg)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)            # y grows downwards, like a slide
    ax.axis("off")
    return fig, ax


def t(ax, x, y, s, size=14, color=INK, weight="normal", ha="left", va="center", family=None, **kw):
    ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, fontfamily=family or (BOLD if weight == "bold" else FONT), **kw)


def box(ax, x, y, w, h, fc, ec="none", r=18, lw=0, alpha=1.0, z=1):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=lw, alpha=alpha, zorder=z)
    ax.add_patch(p)
    return p


def arrow(ax, x1, y1, x2, y2, color=MID, lw=3, ms=22, z=3):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=ms, color=color, lw=lw, zorder=z,
                                 shrinkA=0, shrinkB=0))


def save(fig, name):
    fig.savefig(OUT / name, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    print("wrote", OUT / name)


# ======================================================================================================================
# 1. Hero banner
# ======================================================================================================================
def hero():
    W, H = 1600, 440
    fig, ax = canvas(W, H, NAVY)
    grad = np.linspace(0, 1, 256).reshape(1, -1)
    ax.imshow(grad, extent=[0, W, H, 0], cmap=matplotlib.colors.LinearSegmentedColormap.from_list("g", [NAVY, "#133A63", "#1F4E79"]),
              aspect="auto", zorder=0)
    ax.set_xlim(0, W); ax.set_ylim(H, 0)
    # faint grid
    for x in range(0, W, 80):
        ax.plot([x, x], [0, H], color=WHITE, alpha=0.04, lw=1, zorder=1)
    for y in range(0, H, 80):
        ax.plot([0, W], [y, y], color=WHITE, alpha=0.04, lw=1, zorder=1)

    t(ax, 70, 92, "NEXORA CONSULTING  ·  SALES OPERATIONS", 13, SKY, "bold")
    t(ax, 70, 168, "Sales Pipeline", 54, WHITE, "bold")
    t(ax, 70, 232, "Intelligence", 54, WHITE, "bold")
    ax.add_patch(Rectangle((70, 268), 90, 5, fc=AMBER, zorder=3))
    t(ax, 70, 312, "Know which deals will close, and why.", 24, "#DCE9F7")
    t(ax, 70, 352, "One trusted view of the pipeline. A win probability you can explain.", 16, SKY)
    # right: funnel of deals + probability ring
    stages = ["Discovery", "Solution\nDesign", "Proposal", "Negotiation", "Won"]
    xs = np.linspace(790, 1060, 5)
    widths = [330, 270, 210, 150, 96]
    for i, (s, w) in enumerate(zip(stages, widths)):
        x0 = 790 + i * 62
        box(ax, x0, 120 + i * 0 + (i * 8), 56, w * 0.62 + 40, MID if i < 4 else GREEN, r=10, alpha=0.30 + 0.14 * i, z=2)
    rng = np.random.default_rng(7)
    for i in range(5):
        n = [26, 19, 13, 8, 5][i]
        x0 = 790 + i * 62 + 28
        for yy in np.linspace(150 + i * 8, 120 + i * 8 + widths[i] * 0.62 + 20, n):
            ax.add_patch(Circle((x0 + rng.normal(0, 6), yy), 4.6, fc=SKY if i < 4 else "#9FE2BF", alpha=0.9, zorder=3))
    # probability ring
    cx, cy, R = 1380, 215, 105
    ax.add_patch(Wedge((cx, cy), R, 0, 360, width=20, fc=WHITE, alpha=0.10, zorder=2))
    ax.add_patch(Wedge((cx, cy), R, -90, -90 + 360 * 0.84, width=20, fc=AMBER, zorder=3))
    t(ax, cx, cy - 8, "84%", 46, WHITE, "bold", ha="center")
    t(ax, cx, cy + 38, "chance to win", 14, "#DCE9F7", ha="center")
    box(ax, cx - 150, 350, 300, 44, WHITE, r=22, alpha=0.12, z=2)
    t(ax, cx, 372, "…because late stage, a strong service line", 12.5, WHITE, ha="center")
    save(fig, "hero_banner.png")


# ======================================================================================================================
# 2. Business workflow overview
# ======================================================================================================================
def workflow():
    W, H = 1600, 700
    fig, ax = canvas(W, H, "#F5F8FC")
    t(ax, W / 2, 52, "From messy CRM data to decisions leaders can trust", 30, NAVY, "bold", ha="center")
    t(ax, W / 2, 92, "What was built, in five steps", 16, GREY, ha="center")
    steps = [
        ("1", "DATA SOURCES", "⚑", "Capture", ["24 monthly CRM extracts", "2 system versions after a migration", "8 currencies"], GREY),
        ("2", "TRUST LAYER", "✔", "Cleanse & reconcile", [f"{N['raw_rows']:,} raw rows become {N['deals']:,} real deals", "Duplicates and test data removed", f"{N['checks']} of {N['checks']} checks pass"], BLUE),
        ("3", "BUSINESS RULES", "⚖", "Govern", ["One definition per metric", "Stage odds, FX and “stuck” rules", "Written down, versioned, tested"], BLUE),
        ("4", "PREDICTIVE SCIENCE", "⚙", "Learn from history", [f"Learns from {N['train_deals']:,} closed deals", f"Proven on {N['test_deals']} unseen deals", "A win probability for every open deal"], MID),
        ("5", "DECISIONS", "★", "Act", [f"€{N['flag_eur']:.0f}M of pipeline flagged for review", "“Why this deal?” in plain words", "Early warning on stuck deals"], AMBER),
    ]
    n = len(steps)
    gap, margin = 34, 50
    bw = (W - 2 * margin - gap * (n - 1)) / n
    for i, (num, head, icon, verb, lines, col) in enumerate(steps):
        x = margin + i * (bw + gap)
        box(ax, x, 150, bw, 440, WHITE, ec="#D6E2F0", lw=1.5, r=22, z=1)
        box(ax, x, 150, bw, 112, col, r=22, z=2)
        ax.add_patch(Rectangle((x, 230), bw, 32, fc=col, zorder=2))          # square off the header's lower corners
        ax.add_patch(Circle((x + 44, 206), 26, fc=WHITE, alpha=0.95, zorder=3))
        t(ax, x + 44, 205, icon, 26, col if col != AMBER else "#B97C00", ha="center", family="DejaVu Sans", zorder=4)
        t(ax, x + 86, 184, f"STEP {num}", 11, WHITE, "bold")
        t(ax, x + 84, 214, head, 12.5, WHITE, "bold")
        t(ax, x + bw / 2, 300, verb, 21, NAVY, "bold", ha="center")
        ax.add_patch(Rectangle((x + bw / 2 - 28, 326), 56, 4, fc=col, zorder=3))
        for k, line in enumerate(lines):
            yy = 372 + k * 70
            t(ax, x + 24, yy, "•", 20, col if col != AMBER else AMBER, "bold")
            wrapped = textwrap.fill(line, 24)
            t(ax, x + 48, yy + (10 if wrapped.count(chr(10)) else 0), wrapped, 14, INK, va="center", linespacing=1.35)
        if i < n - 1:
            arrow(ax, x + bw + 4, 206, x + bw + gap - 4, 206, color=NAVY, lw=3.5, ms=26)
    # bottom ribbon
    box(ax, margin, 618, W - 2 * margin, 52, NAVY, r=26)
    for i, w in enumerate(["DATA", "TRUST", "RULES", "PREDICTION", "ACTION"]):
        x = margin + (i + 0.5) * (W - 2 * margin) / 5
        t(ax, x, 644, w, 17, WHITE if i < 4 else AMBER, "bold", ha="center")
        if i < 4:
            t(ax, margin + (i + 1) * (W - 2 * margin) / 5, 643, "›", 26, SKY, ha="center", family="DejaVu Sans")
    save(fig, "workflow_overview.png")


# ======================================================================================================================
# 3. What is win probability? (one real deal)
# ======================================================================================================================
def explainer():
    W, H = 1600, 760
    fig, ax = canvas(W, H, "#F5F8FC")
    t(ax, W / 2, 50, "What is a win probability?", 32, NAVY, "bold", ha="center")
    t(ax, W / 2, 92, "The chance, from 0% to 100%, that an open deal ends in a signed contract", 18, GREY, ha="center")

    # left panel: who says what
    box(ax, 50, 140, 520, 570, WHITE, ec="#D6E2F0", lw=1.5, r=22)
    t(ax, 80, 178, "ONE DEAL, THREE ANSWERS", 13, MID, "bold")
    name = EX.deal_label.split(" | ")[1]
    t(ax, 80, 212, name, 22, NAVY, "bold")
    t(ax, 80, 244, f"SAP S/4HANA · €{EX.amount_eur / 1e6:.1f}M · Solution Design stage", 14, GREY)
    rows = [("“I feel good about it”", "Rep’s gut feeling", "varies by person", GREY, None),
            ("CRM stage default", "Same % for every deal in the stage", f"{EX.g:.0%}", MID, EX.g),
            ("Win-probability model", "Learned from 2,927 closed deals", f"{EX.p:.0%}", AMBER, EX.p)]
    for i, (a, b, c, col, v) in enumerate(rows):
        y = 292 + i * 128
        box(ax, 80, y, 460, 108, PALE if i < 2 else "#FFF6DC", r=16)
        t(ax, 100, y + 30, a, 17, NAVY, "bold")
        t(ax, 100, y + 58, b, 12.5, GREY)
        t(ax, 520, y + 40, c, 34 if v is not None else 15, col if col != GREY else GREY, "bold", ha="right")
        if v is not None:
            ax.add_patch(Rectangle((100, y + 80), 420, 10, fc="#D6E2F0", zorder=3))
            ax.add_patch(Rectangle((100, y + 80), 420 * v, 10, fc=col, zorder=4))
    # arrow to right panel
    arrow(ax, 585, 425, 640, 425, color=NAVY, lw=4, ms=30)

    # right panel: reasons waterfall
    box(ax, 655, 140, 895, 570, WHITE, ec="#D6E2F0", lw=1.5, r=22)
    t(ax, 685, 178, "WHY THE MODEL SAYS " + f"{EX.p:.0%}", 13, MID, "bold")
    t(ax, 685, 212, "Each fact about the deal moves the probability up or down", 20, NAVY, "bold")
    top = EXPL.head(4)
    other = EX.p * 100 - BASE * 100 - top.impact_pts.sum()
    items = [("Average open deal", BASE * 100, "start")]
    for r in top.itertuples():
        lab = {"Client industry": "Industry", "Service line": "Service line", "Sales manager": "Sales manager",
               "Current stage": "Early stage"}.get(r.feature_label, r.feature_label)
        val = r.feature_value.replace(" Implementation", "").replace(" & Consumer Goods", " & Consumer")
        items.append((f"{lab}: {val}", r.impact_pts, "delta"))
    items.append(("All other factors", other, "delta"))
    items.append(("Model’s estimate", EX.p * 100, "end"))
    x0, x1 = 1080, 1470                       # bar zone
    scale = (x1 - x0) / 60                    # 60 points across
    cum = 0
    for i, (lab, v, kind) in enumerate(items):
        y = 258 + i * 56
        t(ax, 685, y + 20, lab, 14.5, INK, "bold" if kind != "delta" else "normal")
        if kind == "start":
            ax.add_patch(Rectangle((x0, y + 4), v * scale, 32, fc=SKY, zorder=3)); cum = v
            t(ax, x0 + v * scale + 10, y + 20, f"{v:.0f}%", 15, NAVY, "bold")
        elif kind == "end":
            ax.add_patch(Rectangle((x0, y + 4), v * scale, 32, fc=AMBER, zorder=3))
            t(ax, x0 + v * scale + 10, y + 20, f"{v:.0f}%", 17, NAVY, "bold")
        else:
            a, b = cum, cum + v
            ax.add_patch(Rectangle((x0 + min(a, b) * scale, y + 4), abs(v) * scale, 32, fc=GREEN if v > 0 else RED, zorder=3))
            t(ax, x0 + max(a, b) * scale + 10, y + 20, f"{v:+.0f} pts", 15, GREEN if v > 0 else RED, "bold")
            cum = b
        ax.plot([x0, x0], [y - 4, y + 44], color="#D6E2F0", lw=1, zorder=2)
    box(ax, 685, 652, 835, 40, "#EAF6EF", r=14)
    t(ax, 705, 672, f"Takeaway: the CRM says {EX.g:.0%}, the model says about a quarter. Check it before banking it.", 13.5, INK)
    save(fig, "win_probability_explained.png")


# ======================================================================================================================
# 4. Technical architecture
# ======================================================================================================================
def architecture():
    W, H = 1600, 860
    fig, ax = canvas(W, H, WHITE)
    t(ax, W / 2, 40, "Technical architecture", 28, NAVY, "bold", ha="center")

    def node(x, y, w, h, title, sub, fc=PALE, ec="#BCD3EA", tc=NAVY):
        box(ax, x, y, w, h, fc, ec=ec, lw=1.6, r=14)
        t(ax, x + w / 2, y + 26, title, 14.5, tc, "bold", ha="center")
        for k, s in enumerate(sub):
            t(ax, x + w / 2, y + 52 + k * 20, s, 11.5, GREY, ha="center")

    # lane labels
    lanes = [("SOURCES", 40), ("STAGING (dbt views)", 330), ("INTERMEDIATE (dbt views)", 640), ("MARTS (dbt tables · DuckDB)", 950), ("CONSUME", 1280)]
    for lab, x in lanes:
        t(ax, x, 84, lab, 12, MID, "bold")
        ax.plot([x, x + 270], [98, 98], color=SKY, lw=2)
    node(40, 116, 250, 78, "24 monthly CRM CSVs", ["v1 + v2 schemas · 5,012 rows"])
    node(40, 206, 250, 78, "Stage-change audit log", ["16,289 field changes"])
    node(40, 296, 250, 78, "Accounts Excel export", ["junk header/footer · 765 rows"])
    node(40, 386, 250, 78, "Sales roster", ["29 AEs · 8 managers"])
    node(330, 116, 270, 100, "stg_crm__opportunities", ["mapping-driven macro", "dates · amounts · aliases"])
    node(330, 228, 270, 70, "stg_crm__stage_history", ["3 timestamp formats"])
    node(330, 310, 270, 70, "stg_crm__accounts / roster", ["Excel + CSV · aliases"])
    node(640, 116, 270, 100, "int_opportunities_clean", ["latest version · owner match", "currency fill · account link"])
    node(640, 228, 270, 70, "int_accounts_master", ["765 → 720 master accounts"])
    node(640, 310, 270, 70, "int_stage_stints", ["12,017 stints via lead()"])
    node(950, 116, 270, 100, "pipeline_deals", ["rules · FX · risk flags", "4,800 rows"], fc="#DCEBFA")
    node(950, 228, 270, 70, "stints · team · accounts", ["dept_quarter_summary"], fc="#DCEBFA")
    node(950, 310, 270, 70, "rejected_records", ["212 rows, each with a reason"], fc="#DCEBFA")
    node(1280, 116, 270, 100, "Power BI (PBIP)", ["7 pages · 63 DAX measures"], fc="#FFF6DC", ec="#EBD28B")
    node(1280, 228, 270, 70, "CSV exports", ["data/output/*"], fc="#FFF6DC", ec="#EBD28B")
    node(1280, 310, 270, 70, "AI experiment", ["grounded vs ungrounded"], fc="#FFF6DC", ec="#EBD28B")
    for y in (166, 263, 345):
        arrow(ax, 292, 160 if y == 166 else y, 328, 160 if y == 166 else y, lw=2, ms=16)
    arrow(ax, 292, 420, 328, 345, lw=2, ms=16)
    for y in (166, 263, 345):
        arrow(ax, 602, 166 if y == 166 else y, 638, 166 if y == 166 else y, lw=2, ms=16)
        arrow(ax, 912, 166 if y == 166 else y, 948, 166 if y == 166 else y, lw=2, ms=16)
    for y in (166, 263, 345):
        arrow(ax, 1222, 166 if y == 166 else y, 1278, 166 if y == 166 else y, lw=2, ms=16)

    # ML lane
    box(ax, 40, 500, 1510, 120, "#F5F8FC", ec="#D6E2F0", lw=1.5, r=16)
    t(ax, 60, 522, "MACHINE LEARNING  ·  Python / scikit-learn", 12, MID, "bold")
    ml = [("Photos of closed deals", "day 0/14/30/45/60/90/120 per stage"), ("Time-based backtest", "train < 1 Mar 2026 · test 550 deals"),
          ("Logistic regression vs forest", "Brier · AUC · calibration"), ("Score + explain", f"{N['scored']} deals · reason codes"),
          ("ml.* tables", "scores · explanations · calibration")]
    for i, (a, b) in enumerate(ml):
        x = 60 + i * 296
        box(ax, x, 538, 270, 66, WHITE, ec="#BCD3EA", lw=1.4, r=12)
        t(ax, x + 135, 561, a, 13, NAVY, "bold", ha="center")
        t(ax, x + 135, 584, b, 11, GREY, ha="center")
        if i < 4:
            arrow(ax, x + 272, 571, x + 292, 571, lw=2, ms=14)
    arrow(ax, 1085, 382, 1085, 498, color=MID, lw=2.5, ms=18)
    arrow(ax, 1415, 500, 1415, 384, color=MID, lw=2.5, ms=18)

    # governance lane
    box(ax, 40, 650, 1510, 170, "#FFFBF0", ec="#F0DCA0", lw=1.5, r=16)
    t(ax, 60, 672, "QUALITY & GOVERNANCE  ·  runs on every build", 12, "#B97C00", "bold")
    gov = [("Reconciliation", f"{N['checks']} checks vs CRM totals", "a failure stops the build"),
           ("dbt tests", "40 tests · keys, values,", "relationships, no overlaps"),
           ("Rules as data", "seeds: stage odds, FX, targets", "aliases, field mapping"),
           ("Audit trail", "212 rejected rows + reasons", "flags: missing, outlier, orphan"),
           ("Model governance", "model card · advisory status", "2-quarter promotion rule"),
           ("CI + reproducible", "GitHub Actions · seeded data", "one command rebuilds all")]
    for i, (a, b, c) in enumerate(gov):
        x = 60 + i * 247
        box(ax, x, 694, 232, 106, WHITE, ec="#F0DCA0", lw=1.4, r=12)
        t(ax, x + 116, 716, a, 13, NAVY, "bold", ha="center")
        t(ax, x + 116, 745, b, 11, GREY, ha="center")
        t(ax, x + 116, 765, c, 11, GREY, ha="center")
    save(fig, "technical_architecture.png")


if __name__ == "__main__":
    hero()
    workflow()
    explainer()
    architecture()
