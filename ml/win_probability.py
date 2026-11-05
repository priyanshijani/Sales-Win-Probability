"""Leakage-safe win-probability model for open deals (model wp-v1-2026-09-15).

Reads the dbt marts from the DuckDB warehouse, builds "photos" of closed deals, backtests with a time-based
split, retrains on all history, scores today's open pipeline, and writes results to the `ml` schema
plus ml/outputs/metrics.json. Design and exclusions are documented in docs/model_card.md.

Run after `dbt build`:  python ml/win_probability.py
"""
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse" / "nexora.duckdb"
OUT = ROOT / "ml" / "outputs"
SNAPSHOT = pd.Timestamp("2026-09-15")
BACKTEST = pd.Timestamp("2026-03-01")
CHECKPOINTS = [0, 14, 30, 45, 60, 90, 120]
MODEL_VERSION = "wp-v1-2026-09-15"
SEED = 42

# Allowed = known while the deal is open. Everything else (rep_probability, forecast category, loss reason, close date,
# sales cycle, activity dates / stale flag, max stage reached, lost-at stage, expected close, account_status) leaks the outcome.
CATEGORICAL = ["stage", "service_line", "sales_region", "industry", "company_size_band", "deal_type",
               "lead_source", "sales_manager", "over_stuck_threshold"]
NUMERIC = ["log_amount", "days_in_stage_so_far", "deal_age_days", "regressions_so_far"]
# department is implied by service line + manager; giving a regression the same information twice makes
# coefficients unstable, so only the forest gets it.
FOREST_EXTRA_CATEGORICAL = ["department"]


def load(con):
    deals = con.sql("""
        select opportunity_id, opportunity_name, account_name, service_line, department, sales_region, industry, company_size_band, deal_type,
               lead_source, sales_manager, amount_eur, created_date, actual_close_date, is_won, is_lost, is_open,
               governed_probability as final_governed_probability, days_in_current_stage, is_stuck, regression_count, sales_cycle_days
        from pipeline_deals order by opportunity_id""").df()
    stints = con.sql("""
        select opportunity_id, stint_seq, stage, stage_order, governed_probability, stuck_after_days,
               entered_at, exited_at, days_in_stage, regressions_so_far
        from pipeline_stage_stints order by opportunity_id, stint_seq""").df()
    for c in ["created_date", "actual_close_date"]:
        deals[c] = pd.to_datetime(deals[c])
    for c in ["entered_at", "exited_at"]:
        stints[c] = pd.to_datetime(stints[c])
    return deals, stints


def add_features(df, observation_date, days_in_stage_so_far):
    df = df.copy()
    df["observation_date"] = observation_date
    df["days_in_stage_so_far"] = np.minimum(days_in_stage_so_far, 120)
    df["deal_age_days"] = (df["observation_date"] - df["created_date"]).dt.days
    df["over_stuck_threshold"] = np.where(df["days_in_stage_so_far"] > df["stuck_after_days"], "Yes", "No")
    df["log_amount"] = np.log10(df["amount_eur"])
    return df


def build_photos(deals, stints, closed_before):
    """Photos of closed deals at day 0/14/30/... of each open stage they sat in. Stage fields come from the STINT,
    not from the deal's final stage (that would leak)."""
    closed = deals[(deals.is_won | deals.is_lost) & (deals.actual_close_date < closed_before) & deals.amount_eur.notna()]
    s = stints.merge(closed, on="opportunity_id", how="inner")
    rows = []
    for cp in CHECKPOINTS:
        p = s[s.days_in_stage >= cp].copy()
        p["checkpoint_day"] = cp
        rows.append(add_features(p, p["entered_at"] + pd.to_timedelta(cp, "D"), cp))
    photos = pd.concat(rows, ignore_index=True)
    photos["y"] = photos["is_won"].astype(int)
    return photos


def build_open_on(deals, stints, as_of):
    """The pipeline as it stood on `as_of`: stints that were running that day."""
    s = stints[(stints.entered_at <= as_of) & (stints.exited_at.isna() | (stints.exited_at > as_of))]
    s = s.merge(deals[deals.amount_eur.notna()], on="opportunity_id", how="inner")
    days = (as_of - s["entered_at"]).dt.days
    return add_features(s, as_of, days)


def make_models():
    def prep(extra_cat):
        return ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL + extra_cat),
            ("num", StandardScaler(), NUMERIC)])
    logit = Pipeline([("prep", prep([])), ("clf", LogisticRegression(max_iter=2000, C=0.5))])
    forest = Pipeline([("prep", prep(FOREST_EXTRA_CATEGORICAL)),
                       ("clf", RandomForestClassifier(n_estimators=400, min_samples_leaf=25, n_jobs=-1, random_state=SEED))])
    return {"Logistic Regression": logit, "Forest": forest}


def feature_cols(name):
    return CATEGORICAL + NUMERIC + (FOREST_EXTRA_CATEGORICAL if name == "Forest" else [])


LABELS = {
    "stage": "Current stage", "service_line": "Service line", "sales_manager": "Sales manager",
    "industry": "Client industry", "sales_region": "Sales region", "company_size_band": "Client size",
    "deal_type": "Deal type (new logo / expansion)", "lead_source": "Lead source",
    "over_stuck_threshold": "Beyond stuck threshold", "log_amount": "Deal size",
    "days_in_stage_so_far": "Days in current stage", "deal_age_days": "Deal age",
    "regressions_so_far": "Times moved backwards", "department": "Department",
}


def base_feature(transformed_name):
    """'cat__service_line_Cybersecurity' -> 'service_line' (roll one-hot levels back up to the source column)."""
    f = transformed_name.split("__", 1)[1]
    for c in CATEGORICAL + FOREST_EXTRA_CATEGORICAL + NUMERIC:
        if f == c or f.startswith(c + "_"):
            return c
    return f


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def describe_value(feature, row):
    v = row[feature]
    if feature == "log_amount":
        return f"EUR {10 ** v:,.0f}"
    if feature == "days_in_stage_so_far":
        return f"{int(v)} days (stuck after {int(row['stuck_after_days'])})"
    if feature == "deal_age_days":
        return f"{int(v)} days"
    if feature == "regressions_so_far":
        return str(int(v))
    return str(v)


def insight(feature, row, impact, won_cycle_days):
    """A few plain words per driver. The wording follows the model's own sign, so it can never contradict the impact
    printed next to it. 'Average' means the average open deal."""
    up = impact >= 0
    rel = "above average" if up else "below average"
    v = row[feature]
    if feature == "stage":
        return f"{v}: close to the finish" if up else f"{v}: early, many deals still drop out"
    if feature == "industry":
        return f"{v} clients convert {rel}"
    if feature == "service_line":
        return f"{v} converts {rel}"
    if feature == "sales_manager":
        return f"{v}'s deals convert {rel}"
    if feature == "sales_region":
        return f"{v} converts {rel}"
    if feature == "company_size_band":
        return f"{v}-employee clients convert {rel}"
    if feature == "deal_type":
        return f"{v} deals convert {rel}"
    if feature == "lead_source":
        return f"'{v}' leads convert {rel}"
    if feature == "log_amount":
        return f"Deal size (EUR {10 ** v / 1e6:.1f}M) works {'for' if up else 'against'} it"
    if feature == "deal_age_days":
        return (f"Open {int(v)} days: normal pace" if up else f"Open {int(v)} days; won deals close in ~{int(won_cycle_days)}")
    if feature == "days_in_stage_so_far":
        return f"{int(v)} days here; flagged stuck after {int(row['stuck_after_days'])}"
    if feature == "regressions_so_far":
        return "Never moved backwards" if int(v) == 0 else f"Moved backwards {int(v)}x"
    if feature == "over_stuck_threshold":
        return "Past its stuck threshold" if v == "Yes" else "Within its stuck threshold"
    return f"{LABELS.get(feature, feature)}: {v}"


def explain(fitted, sc, model_name, won_cycle_days):
    """Reason codes for every scored deal, from the logistic regression.

    A deal's log-odds are the intercept plus one contribution per feature (coefficient x value, summed over a
    feature's one-hot columns). A feature's impact is how many probability points that feature adds or removes
    compared with a neutral value, i.e. the average contribution across today's open pipeline. Impacts are
    computed one feature at a time, so they are close to, but not exactly, additive.
    """
    prep, clf = fitted.named_steps["prep"], fitted.named_steps["clf"]
    X = prep.transform(sc[feature_cols(model_name)])
    X = X.toarray() if hasattr(X, "toarray") else np.asarray(X)
    names = prep.get_feature_names_out()
    parts = pd.DataFrame(X * clf.coef_[0], columns=names)
    by_feature = parts.T.groupby([base_feature(n) for n in names]).sum().T
    logit = clf.intercept_[0] + by_feature.sum(axis=1)
    prob = sigmoid(logit)
    neutral = by_feature.mean()
    rows = []
    sc = sc.reset_index(drop=True)
    for f in by_feature.columns:
        impact = (prob - sigmoid(logit - by_feature[f] + neutral[f])) * 100
        for i in range(len(sc)):
            rows.append((sc.at[i, "opportunity_id"], f, LABELS.get(f, f), describe_value(f, sc.loc[i]), float(impact[i]),
                         insight(f, sc.loc[i], float(impact[i]), won_cycle_days)))
    baseline = float(sigmoid(clf.intercept_[0] + neutral.sum()))      # the "typical open deal"
    ex = pd.DataFrame(rows, columns=["opportunity_id", "feature", "feature_label", "feature_value", "impact_pts", "insight"])
    ex["abs_impact_pts"] = ex.impact_pts.abs()
    ex["direction"] = np.where(ex.impact_pts >= 0, "Increases win probability", "Decreases win probability")
    return ex.sort_values(["opportunity_id", "abs_impact_pts"], ascending=[True, False], ignore_index=True), baseline


MATERIAL_PTS = 2        # drivers smaller than this are noise in a one-line explanation


def reasoning_text(model_p, governed_p, baseline_p, drivers):
    def fmt(d):
        return f"{d.insight} ({d.impact_pts:+.0f})"
    pos = [fmt(d) for d in drivers[drivers.impact_pts >= MATERIAL_PTS].head(3).itertuples()]
    neg = [fmt(d) for d in drivers[drivers.impact_pts <= -MATERIAL_PTS].head(3).itertuples()]
    txt = (f"Model {model_p:.0%} vs {baseline_p:.0%} for the average open deal (CRM stage default {governed_p:.0%}). "
           f"Up: {'; '.join(pos) if pos else 'nothing material'}. "
           f"Down: {'; '.join(neg) if neg else 'nothing material'}.")
    return txt, "; ".join(pos), "; ".join(neg)


def calibration(y, p, method, bins=10):
    t = pd.DataFrame({"y": y, "p": p})
    t["prob_bin"] = np.minimum(np.floor(t.p * bins) / bins, 1 - 1 / bins)
    g = t.groupby("prob_bin").agg(deals=("y", "size"), avg_predicted=("p", "mean"), actual_win_rate=("y", "mean")).reset_index()
    g.insert(0, "method", method)
    return g


def importances(name, fitted):
    names = fitted.named_steps["prep"].get_feature_names_out()
    clf = fitted.named_steps["clf"]
    vals = np.abs(clf.coef_[0]) if name == "Logistic Regression" else clf.feature_importances_
    imp = pd.DataFrame({"feature": names, "importance": vals})  # |coefficient| (logit) or Gini importance (forest)
    # roll one-hot levels back up to the original column
    imp["base_feature"] = imp.feature.map(base_feature)
    out = imp.groupby("base_feature", as_index=False).importance.sum()
    out["importance_share"] = out.importance / out.importance.sum()
    out.insert(0, "model", name)
    return out.sort_values("importance_share", ascending=False)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    deals, stints = load(con)

    # ---- Backtest: train on deals closed before 1 Mar 2026, test on the pipeline as it stood that day -------------
    train = build_photos(deals, stints, BACKTEST)
    test = build_open_on(deals, stints, BACKTEST)
    test = test[(test.is_won | test.is_lost)]            # decided by the snapshot date
    test = test.assign(y=test.is_won.astype(int))
    print(f"TRAIN: {len(train):,} photos from {train.opportunity_id.nunique():,} deals "
          f"(win rate {train.y.mean():.1%}) | TEST: {len(test):,} deals open on {BACKTEST.date()}")

    results, calib, fitted = {}, [], {}
    for name, model in make_models().items():
        model.fit(train[feature_cols(name)], train.y)
        p = model.predict_proba(test[feature_cols(name)])[:, 1]
        results[name] = {"brier": brier_score_loss(test.y, p), "auc": roc_auc_score(test.y, p), "pred": p}
        fitted[name] = model
        calib.append(calibration(test.y, p, name))
    gov = test.governed_probability.to_numpy()
    results["Governed stage probability"] = {"brier": brier_score_loss(test.y, gov), "auc": roc_auc_score(test.y, gov), "pred": gov}
    calib.append(calibration(test.y, gov, "Governed stage probability"))

    best = min(("Logistic Regression", "Forest"), key=lambda m: results[m]["brier"])
    actual_won = float((test.amount_eur * test.y).sum())
    backtest_rows = []
    for name, r in results.items():
        forecast = float((test.amount_eur * r["pred"]).sum())
        backtest_rows.append({"method": name, "brier_score": r["brier"], "auc": r["auc"], "forecast_won_eur": forecast,
                              "actual_won_eur": actual_won, "forecast_error_pct": forecast / actual_won - 1,
                              "deals_tested": len(test), "chosen": name == best})
    backtest = pd.DataFrame(backtest_rows)
    print(backtest.drop(columns=["actual_won_eur"]).round(3).to_string(index=False))

    imp = pd.concat([importances(n, fitted[n]) for n in fitted])

    # ---- Final model: retrain on everything closed before the snapshot, score today's open deals ----------------------
    full = build_photos(deals, stints, SNAPSHOT + pd.Timedelta(days=1))
    final = make_models()[best].fit(full[feature_cols(best)], full.y)

    open_deals = deals[deals.is_open].merge(
        stints[stints.entered_at.notna() & stints.exited_at.isna()][["opportunity_id", "stage", "stuck_after_days",
                                                                      "entered_at", "regressions_so_far"]],
        on="opportunity_id")
    open_deals = open_deals.merge(con.sql("select opportunity_id, governed_probability, weighted_amount_eur from pipeline_deals").df(),
                                  on="opportunity_id")
    scorable = open_deals.amount_eur.notna()
    sc = add_features(open_deals[scorable], SNAPSHOT, open_deals[scorable]["days_in_current_stage"])
    sc["model_win_probability"] = final.predict_proba(sc[feature_cols(best)])[:, 1]

    scores = open_deals[["opportunity_id", "opportunity_name", "account_name", "stage", "amount_eur", "governed_probability"]].merge(
        sc[["opportunity_id", "model_win_probability"]], on="opportunity_id", how="left")
    scores["model_weighted_eur"] = scores.amount_eur * scores.model_win_probability
    scores["model_vs_governed_pts"] = (scores.model_win_probability - scores.governed_probability) * 100
    scores["model_review_flag"] = np.where(scores.model_vs_governed_pts.abs() >= 25, "Review", "OK")
    scores.loc[scores.model_win_probability.isna(), "model_review_flag"] = "NOT_SCORED"
    scores["model_status"] = np.where(scores.model_win_probability.isna(), "NOT_SCORED_NO_AMOUNT", "SCORED")
    scores["model_name"] = best
    scores["model_version"] = MODEL_VERSION
    scores["deal_label"] = scores.opportunity_id + " | " + scores.account_name + " | " + scores.stage

    # ---- Why does the model think so? Reason codes per deal (logistic regression only) ----------------------------------
    explanations = pd.DataFrame(columns=["opportunity_id", "feature", "feature_label", "feature_value", "impact_pts",
                                         "insight", "abs_impact_pts", "direction"])
    scores["model_reasoning"] = "Not scored: no usable deal amount."
    scores["top_positive_drivers"] = ""
    scores["top_negative_drivers"] = ""
    if best == "Logistic Regression":
        won_cycle = deals[deals.is_won].sales_cycle_days.median()
        explanations, baseline_p = explain(final, sc, best, won_cycle)
        by_deal = {k: v for k, v in explanations.groupby("opportunity_id")}
        for i, r in scores[scores.model_win_probability.notna()].iterrows():
            txt, pos, neg = reasoning_text(r.model_win_probability, r.governed_probability, baseline_p, by_deal[r.opportunity_id])
            scores.loc[i, ["model_reasoning", "top_positive_drivers", "top_negative_drivers"]] = [txt, pos, neg]
    else:
        print("NOTE: chosen model is not the logistic regression; per-deal explanations were skipped.")

    # guardrails (same spirit as the dbt tests)
    assert len(scores) == len(deals[deals.is_open]) == 724, "scored + not-scored must equal the open pipeline"
    assert scores.model_win_probability.dropna().between(0, 1).all(), "probabilities must lie in [0, 1]"

    # ---- Persist -------------------------------------------------------------------------------------------------------
    con.execute("create schema if not exists ml")
    for table, frame in {"model_scores": scores, "model_calibration": pd.concat(calib, ignore_index=True),
                         "model_backtest": backtest, "model_feature_importance": imp,
                         "model_explanations": explanations}.items():
        con.register("frame", frame)
        con.execute(f"create or replace table ml.{table} as select * from frame")
        con.unregister("frame")
    con.close()

    metrics = {
        "model_version": MODEL_VERSION, "chosen_model": best,
        "train_photos": int(len(train)), "train_deals": int(train.opportunity_id.nunique()),
        "train_win_rate_per_photo": float(train.y.mean()),
        "test_deals": int(len(test)), "test_win_rate": float(test.y.mean()),
        "final_photos": int(len(full)), "final_deals": int(full.opportunity_id.nunique()),
        "open_deals": int(len(scores)), "scored": int(scores.model_win_probability.notna().sum()),
        "backtest": backtest.drop(columns=["chosen"]).to_dict("records"),
        "top_drivers": imp[imp.model == best].head(5)[["base_feature", "importance_share"]].to_dict("records"),
        "model_weighted_pipeline_eur": float(scores.model_weighted_eur.sum()),
        "governed_weighted_pipeline_eur": float((scores.amount_eur * scores.governed_probability).sum()),
        "review_flags": int((scores.model_review_flag == "Review").sum()),
        "baseline_open_deal_probability": float(baseline_p) if best == "Logistic Regression" else None,
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float), encoding="utf-8")
    print(f"\nChosen: {best} | scored {metrics['scored']}/{metrics['open_deals']} open deals | "
          f"review flags: {metrics['review_flags']}")
    print(imp[imp.model == best].head(5).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
