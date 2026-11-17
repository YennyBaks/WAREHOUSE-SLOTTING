"""Warehouse slotting engine on fully simulated data.

Everything here is synthetic: SKU names, values, bins and movement records are generated
from a fixed random seed. No real company data is used.

Pipeline
  1. generate()      -> SKU master, bin layout, ~400,000 SAP-style movement records
  2. classify()      -> SQL (SQLite window functions): outbound value, ABC class, speed class
  3. place_legacy()  -> the "as-is" slotting (partly right, partly drifted over time)
  4. analyze()       -> target zone per SKU, misplaced bins, picker-travel and efficiency
  5. relocation_plan / recommend_bin / what-if helpers used by the dashboard
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd

SEED = 42
N_SKU = 320
N_RECORDS = 400_000
DAYS = pd.date_range("2026-01-01", "2026-03-31", freq="D")

ZONES = ["Priority", "Standard", "Reserve"]
ZONE_LABEL = {"Priority": "Z1 Priority", "Standard": "Z2 Standard", "Reserve": "Z3 Reserve"}
# lanes per zone, bays per lane, levels per bay
LAYOUT = {
    "Priority": {"lanes": ["PA", "PB", "PC", "PD", "PE", "PF", "PG", "PH"], "bays": 10, "levels": 4, "base_m": 6},
    "Standard": {"lanes": ["SA", "SB", "SC", "SD", "SE", "SF"], "bays": 10, "levels": 4, "base_m": 45},
    "Reserve": {"lanes": ["RA", "RB", "RC", "RD", "RE", "RF"], "bays": 10, "levels": 4, "base_m": 85},
}

CATEGORIES = {
    #  name                    (share, unit value mean $, demand multiplier)
    "Carbonated Soft Drinks": (0.26, 14, 1.6),
    "Bottled Water":          (0.14, 9, 1.4),
    "Coffee Pods":            (0.20, 32, 1.1),
    "Juice & Tea":            (0.14, 18, 0.9),
    "Energy Drinks":          (0.10, 38, 1.0),
    "Mixers":                 (0.10, 16, 0.6),
    "Coffee Brewers":         (0.06, 95, 0.25),
}

# picker model used to turn travel distance into picks per labor hour
WALK_M_PER_S = 1.2       # average walking speed with a cart
HANDLE_S_PER_PICK = 22   # scan, pick, confirm


@dataclass
class Params:
    a_cut: float = 0.80          # cumulative outbound-value share that defines A
    b_cut: float = 0.95          # ... and B (rest is C)
    legacy_accuracy: float = 0.75  # share of SKUs the legacy slotting put in the right zone
    seed: int = SEED


# ---------------------------------------------------------------- 1. generate
def generate(seed: int = SEED):
    rng = np.random.default_rng(seed)
    cats = list(CATEGORIES)
    shares = np.array([CATEGORIES[c][0] for c in cats])
    cat = rng.choice(cats, size=N_SKU, p=shares / shares.sum())
    unit_value = np.array([CATEGORIES[c][1] for c in cat]) * rng.lognormal(0, 0.35, N_SKU)
    # long-tailed demand (a few SKUs drive most picks)
    demand = rng.lognormal(0, 1.45, N_SKU)
    demand *= np.array([CATEGORIES[c][2] for c in cat])
    sku = pd.DataFrame({
        "sku_id": [f"SKU_{i:03d}" for i in range(1, N_SKU + 1)],
        "category": cat,
        "unit_value": unit_value.round(2),
        "demand_weight": demand,
        "case_cube": rng.choice([1, 1, 1, 2, 2, 3], N_SKU),  # bins needed per unit of stock
    })
    sizes = {"Carbonated Soft Drinks": ["12-pack", "24-pack", "2L x 8"], "Bottled Water": ["24-pack", "1L x 12"],
             "Coffee Pods": ["24 ct", "48 ct", "72 ct"], "Juice & Tea": ["6-pack", "12-pack"],
             "Energy Drinks": ["4-pack", "12-pack"], "Mixers": ["6-pack", "1L x 6"], "Coffee Brewers": ["Single unit"]}
    sku["description"] = [f"{c} {rng.choice(sizes[c])}" for c in cat]

    # bins
    rows = []
    for zone, cfg in LAYOUT.items():
        for li, lane in enumerate(cfg["lanes"]):
            for bay in range(1, cfg["bays"] + 1):
                for lvl in range(1, cfg["levels"] + 1):
                    dist = cfg["base_m"] + li * 2.5 + bay * 2.0
                    rows.append({"bin_id": f"{lane}-{bay:02d}-{lvl}", "zone": zone, "lane": lane,
                                 "bay": bay, "level": lvl, "distance_m": round(dist, 1)})
    bins = pd.DataFrame(rows)

    # ~400k SAP-style movement records (goods issue = pick, goods receipt = putaway, transfer)
    p = sku["demand_weight"] / sku["demand_weight"].sum()
    idx = rng.choice(N_SKU, size=N_RECORDS, p=p)
    mv = rng.choice(["Pick", "Putaway", "Transfer"], size=N_RECORDS, p=[0.82, 0.14, 0.04])
    qty = np.where(mv == "Pick", rng.integers(1, 9, N_RECORDS), rng.integers(10, 60, N_RECORDS))
    day = rng.integers(0, len(DAYS), N_RECORDS)
    records = pd.DataFrame({
        "doc_no": np.arange(4_900_000_000, 4_900_000_000 + N_RECORDS),
        "posting_date": DAYS[day].strftime("%Y-%m-%d"),
        "sku_id": sku["sku_id"].to_numpy()[idx],
        "movement_type": mv,
        "qty": qty,
    })
    return sku.drop(columns="demand_weight"), bins, records


# ---------------------------------------------------------------- 2. classify (SQL)
CLASSIFY_SQL = """
WITH picks AS (                         -- velocity and outbound value per SKU
    SELECT r.sku_id,
           COUNT(*)                 AS pick_lines,
           SUM(r.qty)               AS units_out,
           SUM(r.qty * s.unit_value) AS outbound_value
    FROM records r
    JOIN sku s ON s.sku_id = r.sku_id
    WHERE r.movement_type = 'Pick'
    GROUP BY r.sku_id
),
ranked AS (                             -- Pareto: cumulative share of outbound value
    SELECT *,
           SUM(outbound_value) OVER (ORDER BY outbound_value DESC
                                     ROWS UNBOUNDED PRECEDING) * 1.0
             / SUM(outbound_value) OVER () AS cum_value_share,
           NTILE(3) OVER (ORDER BY pick_lines DESC) AS speed_tile
    FROM picks
)
SELECT sku_id, pick_lines, units_out, ROUND(outbound_value, 2) AS outbound_value,
       ROUND(cum_value_share, 4) AS cum_value_share,
       CASE WHEN cum_value_share - outbound_value * 1.0 / (SELECT SUM(outbound_value) FROM picks) < :a_cut THEN 'A'
            WHEN cum_value_share - outbound_value * 1.0 / (SELECT SUM(outbound_value) FROM picks) < :b_cut THEN 'B'
            ELSE 'C' END AS abc_class,
       CASE speed_tile WHEN 1 THEN 'Fast' WHEN 2 THEN 'Medium' ELSE 'Slow' END AS speed_class
FROM ranked
ORDER BY outbound_value DESC;
"""


def load_db(sku: pd.DataFrame, records: pd.DataFrame) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    sku.to_sql("sku", con, index=False)
    records.to_sql("records", con, index=False)
    con.execute("CREATE INDEX ix_rec ON records(sku_id, movement_type)")
    return con


def classify(con: sqlite3.Connection, sku: pd.DataFrame, a_cut=0.80, b_cut=0.95) -> pd.DataFrame:
    cls = pd.read_sql(CLASSIFY_SQL, con, params={"a_cut": a_cut, "b_cut": b_cut})
    out = sku.merge(cls, on="sku_id", how="left")
    out[["pick_lines", "units_out", "outbound_value"]] = out[["pick_lines", "units_out", "outbound_value"]].fillna(0)
    out["abc_class"] = out["abc_class"].fillna("C")
    out["speed_class"] = out["speed_class"].fillna("Slow")
    # bins each SKU occupies: faster movers hold more stock faces
    out["bins_needed"] = (1 + (out["pick_lines"] / out["pick_lines"].max() * 5).round()
                          + (out["case_cube"] - 1)).clip(1, 6).astype(int)
    out["target_zone"] = out.apply(lambda r: target_zone(r.abc_class, r.speed_class), axis=1)
    return out


def target_zone(abc: str, speed: str) -> str:
    """Slotting rule: value (ABC) first, speed breaks ties."""
    if abc == "A" or (abc == "B" and speed == "Fast"):
        return "Priority"
    if abc == "B" or speed != "Slow":
        return "Standard"
    return "Reserve"


# ---------------------------------------------------------------- 3. legacy placement
def place_legacy(skus: pd.DataFrame, bins: pd.DataFrame, accuracy: float, seed: int = SEED) -> pd.DataFrame:
    """As-is slotting: most SKUs were slotted once and never revisited as demand shifted."""
    rng = np.random.default_rng(seed + 1)
    free = {z: list(rng.permutation(bins.index[bins.zone == z])) for z in ZONES}
    assign = {}
    for _, s in skus.sample(frac=1, random_state=seed).iterrows():
        zone = s.target_zone if rng.random() < accuracy else rng.choice(ZONES, p=[0.4, 0.35, 0.25])
        order = [zone] + [z for z in ZONES if z != zone]
        need = int(s.bins_needed)
        for z in order:
            while need and free[z]:
                assign[free[z].pop()] = s.sku_id
                need -= 1
            if not need:
                break
    b = bins.copy()
    b["sku_id"] = b.index.map(assign)
    return b


# ---------------------------------------------------------------- 4. analyze
def picks_per_hour(distance_m):
    return 3600 / (HANDLE_S_PER_PICK + 2 * np.asarray(distance_m) / WALK_M_PER_S)


def analyze(skus: pd.DataFrame, slots: pd.DataFrame):
    """Join bins to SKUs, flag misplaced bins, compute picker travel."""
    b = slots.merge(skus[["sku_id", "description", "category", "abc_class", "speed_class",
                          "target_zone", "pick_lines"]], on="sku_id", how="left")
    b["status"] = np.where(b.sku_id.isna(), "Empty", "Occupied")
    b["misplaced"] = b.sku_id.notna() & (b.zone != b.target_zone)
    b["issue"] = np.select(
        [b.misplaced & (b.abc_class == "A") & (b.zone != "Priority"),
         b.misplaced & (b.abc_class == "C") & (b.zone == "Priority"),
         b.misplaced & (b.zone == "Priority"),
         b.misplaced],
        ["A-class outside Priority", "C-class taking prime space",
         "Low-priority SKU in Priority", "Wrong zone for value/speed"], default="")
    # travel per SKU = picks x round trip to its average bin
    per_sku = b.dropna(subset=["sku_id"]).groupby("sku_id").agg(avg_dist=("distance_m", "mean"),
                                                               zones=("zone", lambda z: ", ".join(sorted(set(z)))))
    s = skus.merge(per_sku, on="sku_id", how="left")
    s["travel_m"] = s.pick_lines * 2 * s.avg_dist
    return b, s


def efficiency(s: pd.DataFrame) -> dict:
    picks = s.pick_lines.sum()
    avg = (s.pick_lines * s.avg_dist).sum() / picks
    return {"avg_dist_m": avg, "picks_per_hour": float(picks_per_hour(avg)),
            "travel_km": s.travel_m.sum() / 1000, "labor_hours": float(picks / picks_per_hour(avg))}


# ---------------------------------------------------------------- 5. plans
def relocation_plan(b: pd.DataFrame) -> pd.DataFrame:
    """Move each misplaced bin to the nearest free bin in its target zone; rank by travel saved."""
    free = {z: list(b[(b.zone == z) & b.sku_id.isna()].sort_values("distance_m").bin_id) for z in ZONES}
    dist = b.set_index("bin_id").distance_m
    nbins = b[b.sku_id.notna()].groupby("sku_id").bin_id.count()
    mis = b[b.misplaced].copy()
    mis["picks_per_bin"] = mis.pick_lines / mis.sku_id.map(nbins)
    mis = mis.sort_values("picks_per_bin", ascending=False)
    rows = []
    for _, r in mis.iterrows():
        tz = r.target_zone
        if free[tz]:
            # moving out of Priority: any bin in the target zone will do; moving in: take the closest
            to = free[tz].pop(0)
        else:
            continue
        saved = r.picks_per_bin * 2 * (r.distance_m - dist[to])
        rows.append({"sku_id": r.sku_id, "description": r.description, "abc_class": r.abc_class,
                     "speed_class": r.speed_class, "from_bin": r.bin_id, "from_zone": r.zone,
                     "to_bin": to, "to_zone": tz, "issue": r.issue,
                     "q1_picks_from_bin": int(round(r.picks_per_bin)), "travel_saved_km": saved / 1000})
    plan = pd.DataFrame(rows)
    if len(plan):
        # moves that free prime space have small or negative direct savings; keep them, rank after
        plan = plan.sort_values("travel_saved_km", ascending=False).reset_index(drop=True)
        plan.index += 1
        plan["cum_saved_km"] = plan.travel_saved_km.cumsum()
    return plan


def apply_plan(slots: pd.DataFrame, plan: pd.DataFrame, n: int | None = None) -> pd.DataFrame:
    """Bin assignments after executing the first n moves of the plan."""
    out = slots[["bin_id", "zone", "lane", "bay", "level", "distance_m", "sku_id"]].copy().set_index("bin_id")
    for _, m in (plan if n is None else plan.head(n)).iterrows():
        out.loc[m.to_bin, "sku_id"] = m.sku_id
        out.loc[m.from_bin, "sku_id"] = np.nan
    return out.reset_index()


def recommend_bin(sku_id: str, skus: pd.DataFrame, b: pd.DataFrame) -> dict | None:
    s = skus[skus.sku_id.str.upper() == sku_id.strip().upper()]
    if s.empty:
        return None
    s = s.iloc[0]
    cur = b[b.sku_id == s.sku_id].sort_values("distance_m")
    free = b[b.sku_id.isna()].sort_values("distance_m")
    best = free[free.zone == s.target_zone].head(1)
    fallback = False
    if best.empty:
        best, fallback = free.head(1), True
    return {"sku": s, "current": cur, "best": best.iloc[0] if len(best) else None, "fallback": fallback,
            "misplaced": bool((cur.zone != s.target_zone).any())}


def insights(skus, b, eff_now, eff_opt, plan) -> list[str]:
    occ = b[b.status == "Occupied"]
    a = skus[skus.abc_class == "A"]
    a_share_picks = a.pick_lines.sum() / skus.pick_lines.sum()
    pri = b[b.zone == "Priority"]
    c_pri = (pri.abc_class == "C").sum()
    top_cat = (skus.groupby("category").outbound_value.sum() / skus.outbound_value.sum()).sort_values(ascending=False)
    gain = eff_opt["picks_per_hour"] / eff_now["picks_per_hour"] - 1
    out = [
        f"**{len(a)} A-class SKUs ({len(a) / len(skus):.0%} of the range) drive {a_share_picks:.0%} of pick lines** "
        f"and {a.outbound_value.sum() / skus.outbound_value.sum():.0%} of outbound value.",
        f"**{b.misplaced.sum()} bins ({b.misplaced.sum() / len(occ):.0%} of occupied) are in the wrong zone**; "
        f"{(b.issue == 'A-class outside Priority').sum()} hold A-class stock outside Priority.",
        f"**{c_pri} Priority bins hold C-class stock**: prime space next to the dock tied up by slow, low-value items.",
        f"**Re-slotting to the rule lifts modeled picks per labor hour by {gain:.0%}** "
        f"({eff_now['picks_per_hour']:.0f} → {eff_opt['picks_per_hour']:.0f}) by cutting average travel "
        f"from {eff_now['avg_dist_m']:.0f} m to {eff_opt['avg_dist_m']:.0f} m per pick.",
        f"**{top_cat.index[0]}** is the largest category by outbound value ({top_cat.iloc[0]:.0%}).",
    ]
    if len(plan):
        top20 = plan.head(20).travel_saved_km.sum() / max(plan.travel_saved_km.clip(lower=0).sum(), 1e-9)
        out.append(f"**The top 20 moves capture {top20:.0%} of the travel savings**: start there.")
    return out


# ---------------------------------------------------------------- one call for the app
def build(params: Params = Params()):
    sku, bins, records = generate(params.seed)
    con = load_db(sku, records)
    # the as-is layout is fixed: it was built from the default policy, then demand drifted
    base = classify(con, sku, Params.a_cut, Params.b_cut)
    slots = place_legacy(base, bins, Params.legacy_accuracy, params.seed)
    skus = classify(con, sku, params.a_cut, params.b_cut)
    b, s = analyze(skus, slots)
    plan = relocation_plan(b)
    # "after": execute every relocation in the plan (what the project did), not a from-scratch rebuild
    b_after, s_after = analyze(skus, apply_plan(b, plan))
    return {"records": records, "con": con, "skus": s, "bins": b, "skus_after": s_after, "bins_after": b_after,
            "eff_now": efficiency(s), "eff_opt": efficiency(s_after), "plan": plan, "params": params}
