"""Generate the Power BI project (PBIP: TMDL semantic model + PBIR report) from the pipeline outputs.

Reads  data/output/powerbi/*.csv  and  powerbi/measures.dax
Writes powerbi/PowerBI_Workbook.SemanticModel/definition/**  and  powerbi/PowerBI_Workbook.Report/definition/**

Close the project in Power BI Desktop before running (otherwise Desktop may overwrite the files), then re-open the .pbip.
Run:  python scripts/build_pbip.py
Anything built by hand in Desktop is overwritten by this script; change the script (or measures.dax) instead.
"""
import csv
import json
import re
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / "powerbi"
DATA = ROOT / "data" / "output" / "powerbi"
MODEL = PBI / "PowerBI_Workbook.SemanticModel" / "definition"
REPORT = PBI / "PowerBI_Workbook.Report" / "definition"
NS = uuid.UUID("6f1c2f2e-0d2a-4b0e-9a57-0a5f0f9c7c11")
T = "\t"


def guid(*parts):
    """Deterministic ids so regenerating produces no diff noise."""
    return str(uuid.uuid5(NS, "/".join(parts)))


def q(name):
    """TMDL needs single quotes around any name that is not a plain identifier (e.g. 'Month Start')."""
    return f"'{name}'" if re.search(r"[^A-Za-z0-9_]", name) else name


def hid(*parts):
    return uuid.uuid5(NS, "/".join(parts)).hex[:20]


# ======================================================================================================================
# 1. Semantic model: tables from the CSV exports
# ======================================================================================================================
TABLES = ["pipeline_deals", "pipeline_stage_stints", "sales_team", "dim_accounts", "dept_quarter_summary",
          "model_scores", "model_calibration", "model_backtest", "model_feature_importance",
          "model_explanations", "dq_reconciliation", "rejected_records"]
SORT_BY = {("pipeline_deals", "stage"): "stage_order", ("pipeline_stage_stints", "stage"): "stage_order",
           ("model_scores", "stage"): None}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")
INT_RE = re.compile(r"^-?\d+$")
FLOAT_RE = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")


def infer(values):
    vals = [v for v in values if v not in ("", None)]
    if not vals:
        return "string"
    low = {v.lower() for v in vals}
    if low <= {"true", "false"}:
        return "boolean"
    if all(INT_RE.match(v) for v in vals):
        return "int64"
    if all(FLOAT_RE.match(v) for v in vals):
        return "double"
    if all(DATE_RE.match(v) for v in vals):
        return "date"
    if all(DT_RE.match(v) for v in vals):
        return "datetime"
    return "string"


M_TYPE = {"string": "type text", "boolean": "type logical", "int64": "Int64.Type", "double": "type number",
          "date": "type date", "datetime": "type datetime"}
FORMAT = {"int64": "0", "date": "dd mmm yyyy", "datetime": "dd mmm yyyy hh:mm"}
NO_SUM = {"id", "seq", "order", "quarter", "year", "lat", "lon", "day", "bin", "rank", "version"}


def read_table(name):
    with open(DATA / f"{name}.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    cols = []
    for i, c in enumerate(header):
        cols.append((c, infer([r[i] for r in body])))
    return cols


def summarize(col, typ):
    """Visuals use explicit DAX measures, so only EUR amounts get a default sum."""
    return "sum" if typ in ("int64", "double") and col.endswith("_eur") else "none"


def table_tmdl(name, cols):
    out = [f"table {name}", f"{T}lineageTag: {guid(name)}", ""]
    for c, typ in cols:
        dt = {"string": "string", "boolean": "boolean", "int64": "int64", "double": "double",
              "date": "dateTime", "datetime": "dateTime"}[typ]
        out.append(f"{T}column {q(c)}")
        out.append(f"{T*2}dataType: {dt}")
        if typ in FORMAT:
            out.append(f"{T*2}formatString: {FORMAT[typ]}")
        out.append(f"{T*2}lineageTag: {guid(name, c)}")
        out.append(f"{T*2}summarizeBy: {summarize(c, typ)}")
        sb = SORT_BY.get((name, c))
        if sb:
            out.append(f"{T*2}sortByColumn: {sb}")
        out.append(f"{T*2}sourceColumn: {c}")
        out.append("")
        out.append(f"{T*2}annotation SummarizationSetBy = Automatic")
        out.append("")
    types = ", ".join('{"%s", %s}' % (c, M_TYPE[t]) for c, t in cols)
    out += [
        f"{T}partition {name} = m",
        f"{T*2}mode: import",
        f"{T*2}source =",
        f"{T*4}let",
        f'{T*4}  Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), [Delimiter = ",", Columns = {len(cols)}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        f'{T*4}  #"Promoted headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),',
        f'{T*4}  #"Changed column type" = Table.TransformColumnTypes(#"Promoted headers", {{{types}}}, "en-US")',
        f"{T*4}in",
        f'{T*4}  #"Changed column type"',
        "",
        f"{T}annotation PBI_ResultType = Table",
        "",
    ]
    return "\n".join(out)


# ======================================================================================================================
# 2. Calculated tables and measures (single source of truth: powerbi/measures.dax)
# ======================================================================================================================
def calc_table(name, dax, columns, category=None, key=None):
    out = [f"table {name}"]
    if category:
        out.append(f"{T}dataCategory: {category}")
    out += [f"{T}lineageTag: {guid(name)}", ""]
    for c, dt, fmt in columns:
        out.append(f"{T}column {q(c)}")
        out.append(f"{T*2}dataType: {dt}")
        if fmt:
            out.append(f"{T*2}formatString: {fmt}")
        if c == key:
            out.append(f"{T*2}isKey")
        out.append(f"{T*2}isDataTypeInferred")
        out.append(f"{T*2}lineageTag: {guid(name, c)}")
        out.append(f"{T*2}summarizeBy: none")
        out.append(f"{T*2}sourceColumn: [{c}]")
        out.append("")
        out.append(f"{T*2}annotation SummarizationSetBy = Automatic")
        out.append("")
    out.append(f"{T}partition {name} = calculated")
    out.append(f"{T*2}mode: import")
    out.append(f"{T*2}source =")
    for line in dax.strip("\n").split("\n"):
        out.append(f"{T*4}{line}")
    out.append("")
    return "\n".join(out)


DIM_DATE = """ADDCOLUMNS (
    CALENDAR ( DATE ( 2024, 4, 1 ), DATE ( 2027, 12, 31 ) ),
    "Year", YEAR ( [Date] ),
    "Quarter", YEAR ( [Date] ) & "-Q" & QUARTER ( [Date] ),
    "Month", FORMAT ( [Date], "yyyy-MM" ),
    "Month Start", DATE ( YEAR ( [Date] ), MONTH ( [Date] ), 1 )
)"""
# A fixed list, NOT DISTINCT(pipeline_deals[department]): a calculated table that depends on a column which a
# relationship then points back to is a circular dependency ("invalid column ID").
DIM_DEPT = """DATATABLE (
    "department", STRING,
    { { "Cloud & Infrastructure" }, { "Data & AI" }, { "Cybersecurity" }, { "ERP & Business Apps" } }
)"""
DIM_STAGE = """DATATABLE (
    "stage_order", INTEGER, "stage", STRING,
    { { 1, "Discovery" }, { 2, "Solution Design" }, { 3, "Proposal" }, { 4, "Negotiation" }, { 5, "Closed Won" } }
)"""

CALC_TABLE_NAMES = {"DimDate", "DimDepartment", "DimStage"}


def parse_measures():
    """Parse measures.dax: a measure starts at column 0 as `Name = ...`; VAR / RETURN lines and // comments don't."""
    lines = (PBI / "measures.dax").read_text(encoding="utf-8").split("\n")
    measures, cur, folder = [], None, ""
    start = re.compile(r"^(?!VAR |RETURN|//|\)|\s)([^=]+?) =\s*(.*)$")
    for ln in lines:
        h = re.match(r"^// -{2,} (.+?) -{2,}", ln)
        if h:
            folder = re.sub(r"\s*\(.*?\)", "", h.group(1)).strip()
            cur = None
            continue
        if ln.startswith("//") and cur is None:
            continue
        m = start.match(ln)
        if m and m.group(1).strip() not in CALC_TABLE_NAMES and not ln.startswith("DimStage"):
            name = m.group(1).strip()
            if name in CALC_TABLE_NAMES:
                cur = None
                continue
            cur = {"name": name, "lines": [m.group(2)] if m.group(2) else [], "folder": folder}
            measures.append(cur)
        elif m and m.group(1).strip() in CALC_TABLE_NAMES:
            cur = None
        elif cur is not None:
            if ln.strip() == "":
                cur = None
            else:
                cur["lines"].append(ln)
    # drop pure comment fragments
    for m in measures:
        m["lines"] = [l for l in m["lines"] if l.strip()]
    return [m for m in measures if m["lines"]]


# Backslash-escaped literals: TMDL rejects format strings that contain bare double quotes.
EUR_M = r"\€#,0.0,,\M"
FORMATS = {
    "EUR_M": EUR_M,
    "EUR_K": r"\€#,0,\K",
    "PCT": "0.0%",
    "X": r"0.0\x",
    "INT": "#,0",
    "DAYS": "0.0",
    "DATE": "dd mmm yyyy",
}


def fmt_for(name):
    n = name.lower()
    if name == "Snapshot Date":
        return FORMATS["DATE"]
    if name in ("Current Quarter", "Next Quarter"):
        return None
    if n.endswith("%") or "win rate" in n or n.endswith("share") or n.endswith("probability"):
        return FORMATS["PCT"]
    if name == "Reasoning Text":
        return None
    if name == "Impact (pts)":
        return "+0.0;-0.0;0.0"
    if n.endswith(" x"):
        return FORMATS["X"]
    if name in ("Avg Won Deal EUR", "Open Pipeline per Account EUR"):
        return FORMATS["EUR_K"]
    if n.endswith("eur"):
        return FORMATS["EUR_M"]
    if "days" in n and ("avg" in n or "median" in n):
        return FORMATS["DAYS"]
    if "honesty" in n:
        return "0.0"
    if n.startswith("account l"):
        return "0.0000"
    return FORMATS["INT"]


def measures_tmdl(measures):
    out = ["table _Measures", f"{T}lineageTag: {guid('_Measures')}", ""]
    for m in measures:
        nm = m["name"]
        q = f"'{nm}'" if re.search(r"[^A-Za-z0-9_]", nm) else nm
        expr = [l.rstrip() for l in m["lines"]]
        # normalise indentation: strip the common leading whitespace, re-indent by tabs
        if len(expr) == 1:
            out.append(f"{T}measure {q} = {expr[0].strip()}")
        else:
            out.append(f"{T}measure {q} =")
            for l in expr:
                out.append(f"{T*3}{l.strip()}" if not l.startswith(" ") else f"{T*3}{l.strip()}")
        f = fmt_for(nm)
        if f:
            out.append(f"{T*2}formatString: {f}")
        if m["folder"]:
            out.append(f"{T*2}displayFolder: {m['folder']}")
        out.append(f"{T*2}lineageTag: {guid('_Measures', nm)}")
        out.append("")
    out += [f"{T}column Dummy", f"{T*2}isHidden", f"{T*2}dataType: int64", f"{T*2}formatString: 0",
            f"{T*2}lineageTag: {guid('_Measures', 'Dummy')}", f"{T*2}summarizeBy: none", f"{T*2}sourceColumn: Dummy", "",
            f"{T*2}annotation SummarizationSetBy = Automatic", "",
            f"{T}partition _Measures = m", f"{T*2}mode: import", f"{T*2}source = #table(type table [Dummy = Int64.Type], {{{{1}}}})", ""]
    return "\n".join(out)


RELATIONSHIPS = [
    # (from many side, to one side, extra properties)
    ("pipeline_deals.actual_close_date", "DimDate.Date", []),
    ("pipeline_deals.created_date", "DimDate.Date", ["isActive: false"]),
    ("pipeline_deals.expected_close_date", "DimDate.Date", ["isActive: false"]),
    ("pipeline_deals.department", "DimDepartment.department", []),
    ("dept_quarter_summary.department", "DimDepartment.department", []),
    ("pipeline_stage_stints.opportunity_id", "pipeline_deals.opportunity_id", []),
    ("pipeline_deals.owner_email", "sales_team.owner_email", []),
    ("pipeline_deals.master_account_id", "dim_accounts.master_account_id", []),
    ("model_scores.opportunity_id", "pipeline_deals.opportunity_id", ["fromCardinality: one", "crossFilteringBehavior: bothDirections"]),
    ("model_explanations.opportunity_id", "model_scores.opportunity_id", []),
]


def relationships_tmdl():
    out = []
    for frm, to, extra in RELATIONSHIPS:
        out.append(f"relationship {guid('rel', frm, to)}")
        for e in extra:
            out.append(f"{T}{e}")
        out.append(f"{T}fromColumn: {frm}")
        out.append(f"{T}toColumn: {to}")
        out.append("")
    return "\n".join(out)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_model():
    shutil.rmtree(MODEL / "tables", ignore_errors=True)
    write(MODEL / "expressions.tmdl",
          f'expression DataFolder = "{DATA}\\" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
          f"{T}lineageTag: {guid('DataFolder')}\n\n{T}annotation PBI_ResultType = Text\n")
    all_cols = {}
    for t in TABLES:
        cols = read_table(t)
        all_cols[t] = cols
        write(MODEL / "tables" / f"{t}.tmdl", table_tmdl(t, cols))
    write(MODEL / "tables" / "DimDate.tmdl", calc_table(
        "DimDate", DIM_DATE,
        [("Date", "dateTime", "dd mmm yyyy"), ("Year", "int64", "0"), ("Quarter", "string", None),
         ("Month", "string", None), ("Month Start", "dateTime", "dd mmm yyyy")], category="Time", key="Date"))
    write(MODEL / "tables" / "DimDepartment.tmdl", calc_table("DimDepartment", DIM_DEPT, [("department", "string", None)]))
    write(MODEL / "tables" / "DimStage.tmdl", calc_table(
        "DimStage", DIM_STAGE, [("stage_order", "int64", "0"), ("stage", "string", None)]))
    measures = parse_measures()
    write(MODEL / "tables" / "_Measures.tmdl", measures_tmdl(measures))
    write(MODEL / "relationships.tmdl", relationships_tmdl())

    names = TABLES + ["DimDate", "DimDepartment", "DimStage", "_Measures"]
    m_tables = TABLES + ["_Measures"]
    write(MODEL / "model.tmdl", "\n".join([
        "model Model", f"{T}culture: en-US", f"{T}defaultPowerBIDataSourceVersion: powerBI_V3",
        f"{T}sourceQueryCulture: en-IN", f"{T}valueFilterBehavior: independent", f"{T}dataAccessOptions",
        f"{T*2}legacyRedirects", f"{T*2}returnErrorValuesAsNull", "",
        "annotation __PBI_TimeIntelligenceEnabled = 1", "",
        "annotation PBI_QueryOrder = " + json.dumps(["DataFolder"] + m_tables), "",
        'annotation PBI_ProTooling = ["DevMode"]', "",
        "ref expression DataFolder", "",
        *[f"ref table {n}" for n in names], "",
        "ref cultureInfo en-US", ""]))
    cache = PBI / "PowerBI_Workbook.SemanticModel" / ".pbi" / "cache.abf"
    if cache.exists():
        cache.unlink()
    return all_cols, measures


# ======================================================================================================================
# 3. Report pages (PBIR)
# ======================================================================================================================
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.3.0/schema.json"
PAGE_W, PAGE_H = 1920, 1080


def col(table, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}


def msr(prop, table="_Measures"):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}


def proj(field):
    kind = "Measure" if "Measure" in field else "Column"
    ent = field[kind]["Expression"]["SourceRef"]["Entity"]
    prop = field[kind]["Property"]
    return {"field": field, "queryRef": f"{ent}.{prop}", "nativeQueryRef": prop}


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


class Page:
    def __init__(self, key, name, title, subtitle):
        self.id = hid("page", key)
        self.name = name
        self.visuals = []
        self.z = 0
        self.title = title
        self.subtitle = subtitle

    def add(self, vtype, x, y, w, h, roles=None, title=None, sort=None, objects=None, extra=None):
        v = {"visualType": vtype}
        if roles:
            v["query"] = {"queryState": {r: {"projections": [proj(f) for f in fs]} for r, fs in roles.items()}}
            if sort:
                v["query"]["sortDefinition"] = {"sort": [{"field": f, "direction": d} for f, d in sort], "isDefaultSort": True}
        if objects:
            v["objects"] = objects
        if title:
            v["visualContainerObjects"] = {"title": [{"properties": {"show": lit("true"), "text": lit("'" + title.replace("'", "''") + "'")}}]}
        v = {k: val for k, val in v.items() if val is not None}
        vis = {"$schema": SCHEMA, "name": hid("vis", self.id, str(len(self.visuals))),
               "position": {"x": x, "y": y, "z": self.z, "height": h, "width": w, "tabOrder": self.z}, "visual": v}
        self.z += 1000
        self.visuals.append(vis)

    # --- convenience builders -------------------------------------------------------------------------------------
    def text(self, x, y, w, h, value, size="12pt", bold=False, color="#1B2A41"):
        run = {"value": value, "textStyle": {"fontSize": size, "color": color, **({"fontWeight": "bold"} if bold else {})}}
        self.add("textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": [{"textRuns": [run]}]}}]})

    def card(self, x, y, w, h, measure, title):
        self.add("card", x, y, w, h, {"Values": [msr(measure)]}, title=title)

    def slicer(self, x, y, w, h, field, title):
        self.add("slicer", x, y, w, h, {"Values": [field]}, title=title,
                 objects={"data": [{"properties": {"mode": lit("'Dropdown'")}}]})

    def header(self, slicers=True):
        self.text(30, 14, 1500, 56, self.title, "26pt", True)
        self.text(30, 66, 1500, 30, self.subtitle, "12pt", False, "#4A5568")
        self.add("pageNavigator", 1300, 14, 590, 56)
        if slicers:
            self.slicer(30, 104, 300, 66, col("DimDepartment", "department"), "Department")
            self.slicer(350, 104, 300, 66, col("pipeline_deals", "sales_region"), "Sales region")
            self.slicer(670, 104, 300, 66, col("pipeline_deals", "service_line"), "Service line")

    def so_what(self):
        self.text(30, 1010, 1860, 50, "So what: (write your one-line takeaway for the CRO here)", "13pt", True, "#1F4E79")

    def cards(self, items, y=184, h=110):
        n = len(items)
        gap = 16
        w = (PAGE_W - 60 - gap * (n - 1)) // n
        for i, (m, t) in enumerate(items):
            self.card(30 + i * (w + gap), y, w, h, m, t)


def asc(f):
    return (f, "Ascending")


def desc(f):
    return (f, "Descending")


def build_pages():
    pages = []

    # ---- Page 1: Pipeline Health & Forecast ------------------------------------------------------------------------
    p = Page("p1", "Pipeline Health & Forecast", "Will we hit the number, and how healthy is the pipeline?",
             "Open pipeline, governed weighted forecast and bookings vs target · snapshot 15 Sep 2026")
    p.header()
    p.cards([("Open Pipeline EUR", "Open pipeline"), ("Weighted Pipeline EUR", "Weighted pipeline (governed)"),
             ("Current Quarter Attainment %", "Bookings vs target, this quarter"), ("Next Quarter Coverage x", "Pipeline coverage, next quarter"),
             ("Win Rate Last 12M", "Win rate, last 12 months"), ("Avg Won Deal EUR", "Average won deal")])
    p.add("clusteredBarChart", 30, 310, 620, 330, {"Category": [col("pipeline_deals", "stage")], "Y": [msr("Open Pipeline EUR")]},
          "Open pipeline by stage", sort=[asc(col("pipeline_deals", "stage"))])
    p.add("lineStackedColumnComboChart", 670, 310, 1220, 330,
          {"Category": [col("dept_quarter_summary", "quarter")],
           "Y": [msr("Commit EUR"), msr("Best Case EUR"), msr("Pipeline Category EUR")], "Y2": [msr("Target EUR")]},
          "Forecast by expected close quarter vs target", sort=[asc(col("dept_quarter_summary", "quarter"))])
    p.add("lineChart", 30, 660, 940, 330, {"Category": [col("DimDate", "Month")], "Y": [msr("Bookings EUR")]},
          "Monthly bookings", sort=[asc(col("DimDate", "Month"))])
    p.add("clusteredColumnChart", 990, 660, 900, 330, {"Category": [col("pipeline_deals", "forecast_category")],
                                                      "Y": [msr("Open Pipeline EUR"), msr("Weighted Pipeline EUR")]},
          "Open vs weighted pipeline by forecast category")
    p.so_what()
    pages.append(p)

    # ---- Page 2: Deal Velocity & Stuck Deals -----------------------------------------------------------------------
    p = Page("p2", "Deal Velocity & Stuck Deals", "Where are deals getting stuck, and how much money is at risk?",
             "Stuck = open longer in a stage than its governed threshold · at risk = stuck, stale, past due or orphaned")
    p.header()
    p.cards([("EUR At Risk", "Pipeline at risk"), ("At Risk % of Pipeline", "Share of open pipeline at risk"),
             ("Stuck Deals", "Stuck deals"), ("Avg Sales Cycle Days", "Avg sales cycle, won (days)"),
             ("At Risk Deals", "At-risk deals")])
    p.add("lineClusteredColumnComboChart", 30, 310, 620, 330,
          {"Category": [col("pipeline_stage_stints", "stage")], "Y": [msr("Median Days in Stage")], "Y2": [msr("Avg Stuck Threshold Days")]},
          "Median days in stage vs stuck threshold", sort=[asc(col("pipeline_stage_stints", "stage"))])
    p.add("pivotTable", 670, 310, 620, 330,
          {"Rows": [col("pipeline_stage_stints", "department")], "Columns": [col("pipeline_stage_stints", "stage")],
           "Values": [msr("Median Days in Stage")]}, "Median days in stage: department x stage")
    p.add("clusteredBarChart", 1310, 310, 580, 330, {"Category": [col("pipeline_deals", "department")], "Y": [msr("Stuck EUR"), msr("EUR At Risk")]},
          "Stuck and at-risk pipeline by department")
    p.add("scatterChart", 30, 660, 760, 330,
          {"Category": [col("pipeline_deals", "opportunity_id")], "X": [msr("Days In Current Stage")], "Y": [msr("Deal Amount EUR")],
           "Series": [col("pipeline_deals", "stage")]},
          "Open deals: days in stage vs deal value")
    p.add("tableEx", 810, 660, 1080, 330,
          {"Values": [col("pipeline_deals", "opportunity_name"), col("pipeline_deals", "owner_name"), col("pipeline_deals", "stage"),
                      msr("Days In Current Stage"), msr("EUR At Risk"), col("pipeline_deals", "risk_reasons")]},
          "Fix this week: at-risk deals", sort=[desc(msr("EUR At Risk"))])
    p.so_what()
    pages.append(p)

    # ---- Page 3: Manager & Department Performance ------------------------------------------------------------------
    p = Page("p3", "Manager & Department Performance", "Which managers and departments convert pipeline into revenue?",
             "FY2026 year to date · quota prorated to days active")
    p.header()
    p.cards([("Bookings YTD EUR", "Bookings YTD"), ("Quota Attainment YTD %", "Quota attainment YTD"),
             ("Win Rate (count)", "Win rate"), ("Open Pipeline EUR", "Open pipeline"), ("Forecast Honesty Gap (pts)", "Rep optimism vs governed (pts)")])
    p.add("pivotTable", 30, 310, 760, 330,
          {"Rows": [col("sales_team", "department"), col("sales_team", "sales_manager"), col("sales_team", "full_name")],
           "Values": [msr("Bookings YTD EUR"), msr("Quota Attainment YTD %"), msr("Win Rate (count)"), msr("Open Pipeline EUR")]},
          "Department > manager > account executive")
    p.add("clusteredBarChart", 810, 310, 520, 330, {"Category": [col("sales_team", "full_name")], "Y": [msr("Quota Attainment YTD %")]},
          "Quota attainment YTD by account executive", sort=[desc(msr("Quota Attainment YTD %"))])
    p.add("scatterChart", 1350, 310, 540, 330,
          {"Category": [col("sales_team", "sales_manager")], "X": [msr("Open Pipeline EUR")], "Y": [msr("Win Rate (count)")],
           "Size": [msr("Bookings YTD EUR")]}, "Open pipeline vs win rate by manager")
    p.add("clusteredBarChart", 30, 660, 760, 330, {"Category": [col("sales_team", "sales_manager")], "Y": [msr("Forecast Honesty Gap (pts)")]},
          "Forecast honesty gap by manager (positive = optimistic)", sort=[desc(msr("Forecast Honesty Gap (pts)"))])
    p.add("hundredPercentStackedBarChart", 810, 660, 1080, 330,
          {"Category": [col("pipeline_deals", "department")], "Series": [col("pipeline_deals", "loss_reason")], "Y": [msr("Lost Deals")]},
          "Loss reasons by department")
    p.so_what()
    pages.append(p)

    # ---- Page 4: Europe Market Opportunity -------------------------------------------------------------------------
    p = Page("p4", "Europe Market Opportunity", "Where in Europe, and in which industries and services, should we invest next?",
             "Open pipeline and win rate by country, region, industry and service line")
    p.header()
    p.cards([("Open Pipeline EUR", "Open pipeline"), ("Win Rate (count)", "Win rate"), ("Accounts", "Accounts"),
             ("Open Pipeline per Account EUR", "Open pipeline per account")])
    p.add("map", 30, 310, 760, 330,
          {"Category": [col("dim_accounts", "city")], "X": [msr("Account Longitude")], "Y": [msr("Account Latitude")],
           "Size": [msr("Open Pipeline EUR")]}, "Open pipeline by city")
    p.add("clusteredBarChart", 810, 310, 520, 330, {"Category": [col("pipeline_deals", "country_name")], "Y": [msr("Open Pipeline EUR")]},
          "Open pipeline by country", sort=[desc(msr("Open Pipeline EUR"))])
    p.add("clusteredBarChart", 1350, 310, 540, 330, {"Category": [col("pipeline_deals", "service_line")], "Y": [msr("Open Pipeline EUR")]},
          "Open pipeline by service line", sort=[desc(msr("Open Pipeline EUR"))])
    p.add("pivotTable", 30, 660, 940, 330,
          {"Rows": [col("pipeline_deals", "industry")], "Columns": [col("pipeline_deals", "sales_region")], "Values": [msr("Win Rate (count)")]},
          "Win rate: industry x sales region")
    p.add("tableEx", 990, 660, 900, 330,
          {"Values": [col("dim_accounts", "account_name"), col("dim_accounts", "country_name"), col("dim_accounts", "industry"),
                      col("dim_accounts", "account_status"), msr("Open Pipeline EUR"), msr("Bookings EUR")]},
          "Top accounts by open pipeline", sort=[desc(msr("Open Pipeline EUR"))])
    p.so_what()
    pages.append(p)

    # ---- Page 5: Win Probability (ML) ------------------------------------------------------------------------------
    p = Page("p5", "Win Probability (ML)", "Does a data-driven win probability beat the CRM's stage probabilities?",
             "ADVISORY - never replaces the governed forecast · backtest: trained before 1 Mar 2026, tested on 550 deals · see docs/model_card.md")
    p.header(slicers=False)
    p.cards([("Weighted Pipeline EUR", "Governed weighted pipeline"), ("Model Weighted Pipeline EUR", "Model-weighted pipeline"),
             ("Governed Weighted (scored deals) EUR", "Governed, scored deals only"), ("Deals To Review", "Deals to review (>= 25 pts apart)"),
             ("Deals Not Scored", "Deals not scored (no amount)")], y=110)
    p.add("scatterChart", 30, 240, 620, 400,
          {"Category": [col("model_calibration", "prob_bin")], "Series": [col("model_calibration", "method")],
           "X": [msr("Predicted Win Rate")], "Y": [msr("Actual Win Rate")], "Size": [msr("Calibration Deals")]},
          "Calibration: predicted vs actual win rate (closer to the diagonal is better)")
    p.add("clusteredColumnChart", 670, 240, 620, 400,
          {"Category": [col("model_backtest", "method")], "Y": [msr("Backtest Forecast EUR"), msr("Backtest Actual EUR")]},
          "Backtest: forecast won EUR vs actual")
    p.add("clusteredBarChart", 1310, 240, 580, 400,
          {"Category": [col("model_feature_importance", "base_feature")], "Series": [col("model_feature_importance", "model")],
           "Y": [msr("Feature Importance Share")]},
          "What drives the model", sort=[desc(msr("Feature Importance Share"))])
    p.add("tableEx", 30, 660, 1860, 330,
          {"Values": [col("model_scores", "opportunity_id"), col("model_scores", "stage"), col("model_scores", "amount_eur"),
                      col("model_scores", "governed_probability"), col("model_scores", "model_win_probability"),
                      col("model_scores", "model_vs_governed_pts"), msr("Deals To Review")]},
          "Open deals where the model and the governed probability disagree by 25 points or more",
          sort=[desc(col("model_scores", "amount_eur"))])
    p.so_what()
    pages.append(p)

    # ---- Page 6: Deal explainer (why does the model think so?) -----------------------------------------------------
    p = Page("p5b", "Why this deal?", "Why does the model think this deal will (or won't) convert?",
             "ADVISORY - click a deal in the list · bars show how many probability points each fact about the deal adds or removes "
             "compared with the average open deal")
    p.header(slicers=False)
    p.cards([("Selected Model Win Probability", "Model win probability"), ("Selected Governed Probability", "CRM stage default"),
             ("Average Open Deal Probability", "Average open deal (model)"), ("Selected Deal Amount EUR", "Deal value")], y=110)
    p.add("tableEx", 30, 240, 820, 750,
          {"Values": [col("model_scores", "deal_label"), col("model_scores", "amount_eur"), col("model_scores", "governed_probability"),
                      col("model_scores", "model_win_probability"), col("model_scores", "model_vs_governed_pts")]},
          "Open deals (click one)", sort=[desc(col("model_scores", "amount_eur"))])
    p.add("card", 870, 240, 1020, 170, {"Values": [msr("Reasoning Text")]}, "In plain words")
    p.add("clusteredBarChart", 870, 430, 1020, 330,
          {"Category": [col("model_explanations", "feature_label")], "Y": [msr("Impact (pts)")]},
          "What pushes the win probability up (+) or down (-), in points", sort=[desc(msr("Impact (pts)"))])
    p.add("tableEx", 870, 780, 1020, 210,
          {"Values": [col("model_explanations", "feature_label"), col("model_explanations", "insight"), msr("Impact (pts)")]},
          "The reasons, in a few words", sort=[desc(msr("Impact (pts)"))])
    pages.append(p)

    # ---- Page 6: Data Trust ----------------------------------------------------------------------------------------
    p = Page("p6", "Data Trust", "Can I trust these numbers?",
             "Every number reconciles to the CRM's own control totals; a failed check stops the dbt build")
    p.header(slicers=False)
    p.cards([("Checks Passed", "Checks passed"), ("Checks Total", "Checks total"), ("Trust Score %", "Trust score"),
             ("Rejected Records", "Raw rows not turned into deals")], y=110)
    p.add("tableEx", 30, 240, 1240, 750,
          {"Values": [col("dq_reconciliation", "check_group"), col("dq_reconciliation", "check_name"), col("dq_reconciliation", "dimension"),
                      col("dq_reconciliation", "expected"), col("dq_reconciliation", "actual"), col("dq_reconciliation", "difference"),
                      col("dq_reconciliation", "status")]}, "Reconciliation checks")
    p.add("clusteredBarChart", 1290, 240, 600, 360, {"Category": [col("rejected_records", "reject_reason")], "Y": [msr("Rejected Records")]},
          "Why raw rows were rejected")
    p.add("textbox", 1290, 620, 600, 370, objects={"general": [{"properties": {"paragraphs": [
        {"textRuns": [{"value": "Row bridge", "textStyle": {"fontWeight": "bold", "fontSize": "16pt", "color": "#1B2A41"}}]},
        {"textRuns": [{"value": "5,012 raw CRM rows = 4,800 opportunities + 206 older versions + 6 test records.", "textStyle": {"fontSize": "13pt"}}]},
        {"textRuns": [{"value": "765 account records = 720 master accounts + 45 merged duplicates.", "textStyle": {"fontSize": "13pt"}}]},
        {"textRuns": [{"value": "Nothing is silently deleted: every rejected row is in rejected_records with a reason.", "textStyle": {"fontSize": "13pt"}}]}]}}]})
    pages.append(p)
    return pages


THEME = {
    "name": "Nexora Executive",
    "dataColors": ["#1F4E79", "#2E75B6", "#7FB2E5", "#BDD7EE", "#2E9E5B", "#E0A526", "#C0392B", "#8C8C8C"],
    "background": "#FFFFFF", "foreground": "#1B2A41", "tableAccent": "#1F4E79",
    "good": "#2E9E5B", "neutral": "#E0A526", "bad": "#C0392B",
}


def build_report(pages):
    pdir = REPORT / "pages"
    shutil.rmtree(pdir, ignore_errors=True)
    old_first = "a3c8dc5d73d92273fc0b"          # the blank page created in Desktop becomes page 1
    for i, pg in enumerate(pages):
        if i == 0:
            pg.id = old_first
        write(pdir / pg.id / "page.json", json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": pg.id, "displayName": pg.name, "displayOption": "FitToPage", "height": PAGE_H, "width": PAGE_W}, indent=2))
        for k, v in enumerate(pg.visuals):
            v["name"] = hid("vis", pg.id, str(k))
            write(pdir / pg.id / "visuals" / v["name"] / "visual.json", json.dumps(v, indent=2, ensure_ascii=False))
    write(pdir / "pages.json", json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
        "pageOrder": [p.id for p in pages], "activePageName": pages[0].id}, indent=2))

    # custom theme
    res = PBI / "PowerBI_Workbook.Report" / "StaticResources" / "RegisteredResources"
    write(res / "NexoraExecutive.json", json.dumps(THEME, indent=2))
    write(PBI / "theme.json", json.dumps(THEME, indent=2))
    rpt = json.loads((REPORT / "report.json").read_text(encoding="utf-8"))
    rpt["themeCollection"]["customTheme"] = {
        "name": "NexoraExecutive.json",
        "reportVersionAtImport": rpt["themeCollection"]["baseTheme"]["reportVersionAtImport"], "type": "RegisteredResources"}
    pk = [r for r in rpt["resourcePackages"] if r["name"] != "RegisteredResources"]
    pk.append({"name": "RegisteredResources", "type": "RegisteredResources",
               "items": [{"name": "NexoraExecutive.json", "path": "NexoraExecutive.json", "type": "CustomTheme"}]})
    rpt["resourcePackages"] = pk
    write(REPORT / "report.json", json.dumps(rpt, indent=2))


if __name__ == "__main__":
    cols, measures = build_model()
    pages = build_pages()
    build_report(pages)
    print(f"model: {len(TABLES)} imported tables + 3 calculated + _Measures ({len(measures)} measures), "
          f"{len(RELATIONSHIPS)} relationships")
    print(f"report: {len(pages)} pages, {sum(len(p.visuals) for p in pages)} visuals")
    for m in measures:
        print("  -", m["name"])
