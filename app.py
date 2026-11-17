"""Warehouse Slotting & Inventory Analytics: portfolio dashboard on simulated data.

Run locally:  pip install -r requirements.txt  &&  streamlit run app.py
"""
import html

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import slotting as S

# ------------------------------------------------------------------ personalise here
AUTHOR = "Omoyeni Bakinde"
LINKEDIN = "https://www.linkedin.com/in/omoyeni-bakinde-oguntade-64572983"
GITHUB_REPO = ""  # e.g. "https://github.com/YennyBaks/warehouse-slotting"
EMPLOYER_LABEL = "Sumner Distribution Center"  # or your employer's name, if you choose to show it
REAL_RESULTS = [  # results from the real project (your resume); shown as context, not computed here
    ("+15%", "order-picking efficiency within 5 months"),
    ("2 days", "faster warehouse data processing"),
    ("~90 min/day", "of manual reporting eliminated"),
    ("~10%", "lower inventory movement costs"),
]

COLORS = {"A": "#16a34a", "B": "#f59e0b", "C": "#dc2626", "Empty": "#e5e7eb"}
ZONE_COLORS = {"Priority": "#4f46e5", "Standard": "#0891b2", "Reserve": "#64748b"}
INK, MUTED, ACCENT = "#0f172a", "#64748b", "#4f46e5"

st.set_page_config(page_title="Warehouse Slotting Analytics | " + AUTHOR, page_icon="📦", layout="wide")

st.markdown(f"""
<style>
.block-container {{padding-top: 1.4rem; max-width: 1400px;}}
.hero {{background: linear-gradient(120deg,#0f172a 0%,#1e1b4b 100%); color:#fff; border-radius:16px;
        padding:22px 28px; margin-bottom:14px;}}
.hero h1 {{font-size:1.65rem; margin:0 0 4px 0; color:#fff; font-weight:700;}}
.hero p {{margin:0; color:#c7d2fe; font-size:.95rem;}}
.pill {{display:inline-block; background:#fef3c7; color:#92400e; border-radius:999px; padding:2px 10px;
        font-size:.75rem; font-weight:600; margin-left:8px; vertical-align:middle;}}
.kpi {{background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:12px 14px; height:100%;}}
.kpi .l {{font-size:.72rem; letter-spacing:.06em; text-transform:uppercase; color:{MUTED};}}
.kpi .v {{font-size:1.65rem; font-weight:700; color:{INK}; line-height:1.25;}}
.kpi .s {{font-size:.78rem; color:{MUTED};}}
.story {{background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px; height:100%;}}
.story h4 {{margin:0 0 6px 0; font-size:.95rem; color:{ACCENT};}}
.story p {{margin:0; font-size:.9rem; color:#334155;}}
.real {{background:#eef2ff; border-radius:12px; padding:12px 16px; text-align:center; height:100%;}}
.real .v {{font-size:1.5rem; font-weight:700; color:{ACCENT};}}
.real .s {{font-size:.8rem; color:#334155;}}
.zone-h {{font-weight:700; margin:14px 0 6px 0; font-size:.95rem;}}
.zone-h span {{font-weight:400; color:{MUTED}; font-size:.82rem;}}
.lanes {{display:flex; flex-wrap:wrap; gap:10px;}}
.lane {{border:1px solid #e2e8f0; border-radius:10px; padding:8px 10px 10px; background:#fff;}}
.lane .t {{font-size:.72rem; color:{MUTED}; text-align:center; margin-bottom:4px; font-weight:600;}}
.grid {{display:grid; grid-template-columns:repeat(10,14px); gap:3px;}}
.b {{width:14px; height:14px; border-radius:3px;}}
.b.mis {{outline:2px solid {INK}; outline-offset:-1px;}}
.b.dim {{opacity:.15;}}
.legend span {{display:inline-flex; align-items:center; margin-right:16px; font-size:.85rem; color:#334155;}}
.legend i {{width:12px; height:12px; border-radius:3px; display:inline-block; margin-right:6px;}}
.foot {{color:{MUTED}; font-size:.8rem; text-align:center; margin-top:28px; border-top:1px solid #e2e8f0; padding-top:12px;}}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ data
@st.cache_resource(show_spinner="Simulating 400,000 warehouse movement records…")
def load(a_cut: float, b_cut: float):
    return S.build(S.Params(a_cut=a_cut, b_cut=b_cut))


@st.cache_data(show_spinner="Running policy sensitivity…")
def sensitivity():
    rows = []
    for a in (0.70, 0.75, 0.80, 0.85, 0.90):
        d = S.build(S.Params(a_cut=a, b_cut=min(0.97, a + 0.15)))
        rows.append({"A cutoff (cum. value)": f"{a:.0%}", "A SKUs": int((d["skus"].abc_class == "A").sum()),
                     "Misplaced bins": int(d["bins"].misplaced.sum()),
                     "Picks / hr after": round(d["eff_opt"]["picks_per_hour"], 1),
                     "Efficiency gain (%)": round(100 * (d["eff_opt"]["picks_per_hour"] / d["eff_now"]["picks_per_hour"] - 1), 1)})
    return pd.DataFrame(rows)


def kpi(col, label, value, sub=""):
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div>'
                 f'<div class="s">{sub}</div></div>', unsafe_allow_html=True)


def style(fig, h=330):
    fig.update_layout(template="plotly_white", height=h, margin=dict(l=10, r=10, t=40, b=10),
                      font=dict(color=INK, size=12), legend=dict(orientation="h", y=-0.2, title=None),
                      title_font=dict(size=14))
    return fig


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### Filters")
    f_abc = st.multiselect("ABC class", ["A", "B", "C"], default=["A", "B", "C"])
    f_speed = st.multiselect("Speed class", ["Fast", "Medium", "Slow"], default=["Fast", "Medium", "Slow"])
    f_zone = st.multiselect("Zone", S.ZONES, default=S.ZONES, format_func=lambda z: S.ZONE_LABEL[z])
    f_cat = st.multiselect("Category", list(S.CATEGORIES), default=list(S.CATEGORIES))
    st.divider()
    st.markdown("### Slotting policy")
    a_cut = st.slider("A class = top % of outbound value", 0.60, 0.90, 0.80, 0.05, format="%.2f",
                      help="SKUs that together make up this share of outbound value are A-class.")
    b_cut = st.slider("A + B = top % of outbound value", max(0.85, a_cut + 0.05), 0.99, max(0.95, a_cut + 0.05), 0.01,
                      format="%.2f")
    st.caption("Change the cutoffs to see how the classification, misplaced bins and gains respond.")

D = load(round(a_cut, 2), round(b_cut, 2))
skus, bins, plan = D["skus"], D["bins"], D["plan"]
eff_now, eff_opt = D["eff_now"], D["eff_opt"]

with st.sidebar:
    st.divider()
    st.markdown("### Zone breakdown")
    zb = bins.groupby("zone").agg(Total=("bin_id", "count"), Occupied=("sku_id", "count"),
                                  Misplaced=("misplaced", "sum")).reindex(S.ZONES)
    zb["Free"] = zb.Total - zb.Occupied
    zb.index = [S.ZONE_LABEL[z] for z in zb.index]
    st.dataframe(zb[["Free", "Occupied", "Total", "Misplaced"]], use_container_width=True)


def keep(df):
    m = df.abc_class.isin(f_abc) & df.speed_class.isin(f_speed) & df.category.isin(f_cat)
    if "zone" in df:
        m &= df.zone.isin(f_zone)
    return df[m]


# ------------------------------------------------------------------ header + KPIs
st.markdown(f"""<div class="hero"><h1>Warehouse Slotting &amp; Inventory Analytics<span class="pill">Simulated data</span></h1>
<p>Beverage distribution center · Q1 2026 · {len(D['records']):,} SAP-style movement records · {len(skus)} SKUs ·
{len(bins)} bins &nbsp;|&nbsp; Portfolio project by {AUTHOR}</p></div>""", unsafe_allow_html=True)

occ = int((bins.status == "Occupied").sum())
gain = eff_opt["picks_per_hour"] / eff_now["picks_per_hour"] - 1
c = st.columns(7)
kpi(c[0], "SKUs tracked", f"{len(skus)}", f"{(skus.abc_class == 'A').sum()} A · {(skus.abc_class == 'B').sum()} B · {(skus.abc_class == 'C').sum()} C")
kpi(c[1], "Storage bins", f"{len(bins):,}", "3 zones by distance to dock")
kpi(c[2], "Occupied", f"{occ / len(bins):.0%}", f"{occ} bins · {len(bins) - occ} free")
kpi(c[3], "Misplaced bins", f"{int(bins.misplaced.sum())}", f"{bins.misplaced.sum() / occ:.0%} of occupied")
kpi(c[4], "A outside Priority", f"{(bins.issue == 'A-class outside Priority').sum()}", "high-value, far from dock")
kpi(c[5], "C in Priority", f"{(bins.issue == 'C-class taking prime space').sum()}", "slow stock in prime space")
kpi(c[6], "Modeled efficiency gain", f"+{gain:.0%}", f"{eff_now['picks_per_hour']:.0f} → {eff_opt['picks_per_hour']:.0f} picks / labor hr")
st.write("")

t_over, t_map, t_sku, t_plan, t_what, t_method = st.tabs(
    ["Overview", "Bin map", "SKU lookup", "Relocation plan", "What-if & sensitivity", "Method & data"])

# ------------------------------------------------------------------ overview
with t_over:
    c = st.columns(3)
    for col, (h, p) in zip(c, [
        ("The problem", "Products were slotted once and never revisited. As demand shifted, fast, high-value SKUs "
                        "ended up far from the dock while slow items sat in prime space, adding picker travel on every order."),
        ("The approach", f"Pulled {len(D['records']):,} SAP inventory movements into SQL and Python, ranked every SKU by "
                         "outbound value (ABC) and pick frequency (speed), mapped bins by distance to the dock, and "
                         "flagged every bin stored in the wrong zone."),
        ("The output", "A ranked relocation plan, a best-bin recommender for putaway, and dashboards that let "
                       "operations track utilization and slotting health instead of rebuilding reports by hand."),
    ]):
        col.markdown(f'<div class="story"><h4>{h}</h4><p>{p}</p></div>', unsafe_allow_html=True)

    st.markdown(f"##### Results on the real project at {EMPLOYER_LABEL}")
    c = st.columns(len(REAL_RESULTS))
    for col, (v, s) in zip(c, REAL_RESULTS):
        col.markdown(f'<div class="real"><div class="v">{v}</div><div class="s">{s}</div></div>', unsafe_allow_html=True)
    st.caption("These outcomes come from the original engagement. Everything else on this page is computed live from simulated data.")

    st.markdown("##### Key insights from the simulation")
    for i in S.insights(skus, bins, eff_now, eff_opt, plan):
        st.markdown(f"- {i}")

    fs = keep(skus)
    fb = keep(bins[bins.status == "Occupied"])
    c1, c2 = st.columns(2)
    with c1:
        p = skus.sort_values("outbound_value", ascending=False).reset_index(drop=True)
        p["rank_pct"] = (p.index + 1) / len(p)
        fig = px.scatter(p, x="rank_pct", y="cum_value_share", color="abc_class", color_discrete_map=COLORS,
                         hover_data={"sku_id": True, "description": True, "rank_pct": ":.0%", "cum_value_share": ":.0%"},
                         title="Pareto: cumulative outbound value by SKU rank")
        fig.update_traces(marker_size=5)
        fig.update_xaxes(tickformat=".0%", title="Share of SKUs (ranked by outbound value)")
        fig.update_yaxes(tickformat=".0%", title="Cumulative outbound value")
        st.plotly_chart(style(fig), use_container_width=True)
    with c2:
        u = bins[bins.zone.isin(f_zone)].assign(state=lambda d: np.where(d.status == "Empty", "Free",
                                                np.where(d.misplaced, "Misplaced", "Correctly slotted")))
        u = u.groupby(["zone", "state"]).size().reset_index(name="bins")
        u["zone"] = u.zone.map(S.ZONE_LABEL)
        fig = px.bar(u, x="zone", y="bins", color="state", title="Zone utilization and slotting health",
                     color_discrete_map={"Correctly slotted": "#4f46e5", "Misplaced": "#dc2626", "Free": "#cbd5e1"},
                     category_orders={"zone": list(S.ZONE_LABEL.values()), "state": ["Correctly slotted", "Misplaced", "Free"]})
        fig.update_layout(xaxis_title=None, yaxis_title="Bins")
        st.plotly_chart(style(fig), use_container_width=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        m = fb.groupby(["zone", "abc_class"]).size().reset_index(name="bins")
        m["zone"] = m.zone.map(S.ZONE_LABEL)
        fig = px.bar(m, x="zone", y="bins", color="abc_class", color_discrete_map=COLORS,
                     title="ABC mix by zone (ideal: Z1 green, Z3 red)",
                     category_orders={"zone": list(S.ZONE_LABEL.values()), "abc_class": ["A", "B", "C"]})
        fig.update_layout(xaxis_title=None, yaxis_title="Bins")
        st.plotly_chart(style(fig), use_container_width=True)
    with c2:
        h = fs.pivot_table(index="speed_class", columns="abc_class", values="pick_lines", aggfunc="sum", fill_value=0)
        h = h.reindex(index=["Fast", "Medium", "Slow"], columns=["A", "B", "C"], fill_value=0)
        fig = px.imshow(h / max(h.values.sum(), 1), text_auto=".0%", color_continuous_scale="Purples", aspect="auto",
                        title="Share of pick lines: speed × ABC")
        fig.update_layout(coloraxis_showscale=False, xaxis_title="ABC class", yaxis_title="Speed class")
        st.plotly_chart(style(fig), use_container_width=True)
    with c3:
        cat = fs.groupby("category").agg(value=("outbound_value", "sum")).sort_values("value").reset_index()
        fig = px.bar(cat, x="value", y="category", orientation="h", title="Outbound value by category (Q1)",
                     color_discrete_sequence=[ACCENT])
        fig.update_layout(xaxis_title="Outbound value ($)", yaxis_title=None)
        fig.update_xaxes(tickprefix="$", tickformat="~s")
        st.plotly_chart(style(fig), use_container_width=True)

# ------------------------------------------------------------------ bin map
with t_map:
    c1, c2 = st.columns([3, 2])
    view = c1.radio("Layout", ["As-is", "After re-slotting"], horizontal=True,
                    help="'After re-slotting' applies every move in the relocation plan.")
    ring = c2.toggle("Outline misplaced bins", value=True)
    mb = bins if view == "As-is" else D["bins_after"]
    st.markdown('<div class="legend">' + "".join(
        f'<span><i style="background:{COLORS[k]}"></i>{t}</span>' for k, t in
        [("A", "A-class: highest value"), ("B", "B-class: medium"), ("C", "C-class: low value"), ("Empty", "Empty bin")])
        + f'<span><i style="background:#fff;outline:2px solid {INK}"></i>Wrong zone</span></div>', unsafe_allow_html=True)
    st.caption("Each square is one bin (10 bays × 4 levels per lane). Hover a bin for SKU details. "
               "Sidebar filters fade bins that don't match.")

    def bin_html(r):
        cls = r.abc_class if r.status == "Occupied" else "Empty"
        match = r.status == "Empty" or (r.abc_class in f_abc and r.speed_class in f_speed and r.category in f_cat)
        css = "b" + (" mis" if (ring and r.misplaced) else "") + ("" if match else " dim")
        if r.status == "Occupied":
            tip = (f"{r.bin_id} · {r.sku_id} · {r.description}\nClass {r.abc_class} · {r.speed_class} mover\n"
                   f"{r.distance_m:.0f} m to dock · belongs in {r.target_zone}" + (f"\n⚠ {r.issue}" if r.misplaced else ""))
        else:
            tip = f"{r.bin_id} · empty · {r.distance_m:.0f} m to dock"
        return f'<div class="{css}" style="background:{COLORS[cls]}" title="{html.escape(tip).replace(chr(10), "&#10;")}"></div>'

    desc = {"Priority": "closest to the dock · reserved for A-class and fast B-class SKUs",
            "Standard": "mid-distance · B-class and faster C-class SKUs",
            "Reserve": "furthest from the dock · slow, low-value stock"}
    for zone in [z for z in S.ZONES if z in f_zone]:
        zb_ = mb[mb.zone == zone]
        mis = int(zb_.misplaced.sum())
        out = [f'<div class="zone-h" style="color:{ZONE_COLORS[zone]}">{S.ZONE_LABEL[zone]} '
               f'<span>— {desc[zone]} · {int((zb_.status == "Occupied").sum())}/{len(zb_)} occupied · {mis} misplaced</span></div>'
               '<div class="lanes">']
        for lane, lb in zb_.groupby("lane", sort=True):
            lb = lb.sort_values(["level", "bay"], ascending=[False, True])
            out.append(f'<div class="lane"><div class="t">{lane}</div><div class="grid">'
                       + "".join(bin_html(r) for r in lb.itertuples()) + "</div></div>")
        out.append("</div>")
        st.markdown("".join(out), unsafe_allow_html=True)

# ------------------------------------------------------------------ SKU lookup
with t_sku:
    st.markdown("##### Best-bin recommendation")
    st.caption("Pick a SKU (type to search). The engine checks its ABC and speed class, decides the zone it belongs in, "
               "and returns the closest free bin there.")
    opts = skus.sort_values("pick_lines", ascending=False)
    names = dict(zip(opts.sku_id, opts.description))
    choice = st.selectbox("SKU", opts.sku_id, format_func=lambda s: f"{s} · {names[s]}")
    rec = S.recommend_bin(choice, skus, bins)
    s = rec["sku"]
    c = st.columns(5)
    kpi(c[0], "ABC class", s.abc_class, f"{s.cum_value_share:.0%} cumulative value")
    kpi(c[1], "Speed", s.speed_class, f"{int(s.pick_lines):,} pick lines in Q1")
    kpi(c[2], "Outbound value", f"${s.outbound_value:,.0f}", f"{int(s.units_out):,} units shipped")
    kpi(c[3], "Belongs in", S.ZONE_LABEL[s.target_zone], "rule: value first, speed breaks ties")
    kpi(c[4], "Currently in", s.zones if isinstance(s.zones, str) else "No bin yet", "⚠ wrong zone" if rec["misplaced"] else "✓ correctly slotted")
    st.write("")
    best = rec["best"]
    if best is not None:
        msg = (f"**Recommended bin: {best.bin_id}** ({S.ZONE_LABEL[best.zone]}, {best.distance_m:.0f} m from the dock)")
        if rec["fallback"]:
            msg += f". {S.ZONE_LABEL[s.target_zone]} is full, so this is the closest free bin overall."
        (st.warning if rec["misplaced"] else st.success)(msg)
        if rec["misplaced"]:
            far = rec["current"][rec["current"].zone != s.target_zone]
            per_bin = s.pick_lines / max(len(rec["current"]), 1)
            saved = (per_bin * 2 * (far.distance_m - best.distance_m)).clip(lower=0).sum() / 1000
            if saved > 0:
                st.caption(f"Moving its wrong-zone stock here would save about {saved:,.0f} km of picker travel per quarter.")
    st.markdown("**Bins holding this SKU now**")
    st.dataframe(rec["current"][["bin_id", "zone", "lane", "bay", "level", "distance_m", "misplaced", "issue"]],
                 hide_index=True, use_container_width=True,
                 column_config={"distance_m": st.column_config.NumberColumn("Distance to dock (m)", format="%.0f")})

# ------------------------------------------------------------------ relocation plan
with t_plan:
    fp = plan.merge(skus[["sku_id", "category"]], on="sku_id", how="left")
    fp = fp[fp.abc_class.isin(f_abc) & fp.speed_class.isin(f_speed) & fp.category.isin(f_cat) & fp.from_zone.isin(f_zone)]
    c = st.columns(4)
    kpi(c[0], "Moves in plan", f"{len(fp)}", f"of {int(bins.misplaced.sum())} misplaced bins")
    kpi(c[1], "Travel saved / quarter", f"{fp.travel_saved_km.sum():,.0f} km", "net, all moves in view")
    hrs = (eff_now["labor_hours"] - eff_opt["labor_hours"])
    kpi(c[2], "Labor hours saved / quarter", f"{hrs:,.0f}", "full plan, modeled")
    kpi(c[3], "Top-20 share of savings",
        f"{plan.head(20).travel_saved_km.sum() / max(plan.travel_saved_km.clip(lower=0).sum(), 1e-9):.0%}", "do these first")
    st.write("")
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("##### Relocation candidates, ranked by travel saved")
        st.dataframe(
            fp[["sku_id", "description", "abc_class", "speed_class", "from_bin", "from_zone", "to_bin", "to_zone",
                "issue", "q1_picks_from_bin", "travel_saved_km"]],
            use_container_width=True, height=420,
            column_config={"sku_id": "SKU", "description": "Product", "abc_class": "ABC", "speed_class": "Speed",
                           "from_bin": "From bin", "from_zone": "From zone", "to_bin": "To bin", "to_zone": "To zone",
                           "issue": "Why", "q1_picks_from_bin": st.column_config.NumberColumn("Q1 picks", format="%d"),
                           "travel_saved_km": st.column_config.NumberColumn("Travel saved (km/qtr)", format="%.1f")})
        st.download_button("Download plan (CSV)", fp.to_csv(index_label="priority").encode(), "relocation_plan.csv", "text/csv")
    with c2:
        fig = px.line(plan.reset_index(names="move"), x="move", y="cum_saved_km",
                      title="Cumulative travel saved as moves are executed")
        fig.update_traces(line_color=ACCENT, line_width=3)
        fig.update_layout(xaxis_title="Moves executed (ranked)", yaxis_title="km saved per quarter")
        st.plotly_chart(style(fig, 300), use_container_width=True)
        st.caption("Moves that clear C-class stock out of Priority save little travel themselves, "
                   "but they free the prime bins that A-class moves need.")

# ------------------------------------------------------------------ what-if
with t_what:
    st.markdown("##### How far do you need to go? Execute the plan step by step")
    c1, c2 = st.columns([1, 2])
    with c1:
        n = st.slider("Moves executed", 0, len(plan), min(20, len(plan)))
        rate = st.number_input("Loaded labor rate ($/hr)", 15.0, 60.0, 24.0, 1.0)
        picks = skus.pick_lines.sum()
        travel0 = eff_now["travel_km"] * 1000
        cum = np.r_[0, plan.cum_saved_km.to_numpy() * 1000] if len(plan) else np.array([0.0])
        avg = (travel0 - cum) / (2 * picks)
        pph = S.picks_per_hour(avg)
        hrs_saved = picks / pph[0] - picks / pph[n]
        kpi(st, "Picks per labor hour", f"{pph[n]:.1f}", f"+{pph[n] / pph[0] - 1:.1%} vs as-is ({pph[0]:.1f})")
        st.write("")
        kpi(st, "Labor saved", f"{hrs_saved:,.0f} hrs / qtr", f"≈ ${hrs_saved * rate * 4:,.0f} per year at ${rate:.0f}/hr")
    with c2:
        curve = pd.DataFrame({"moves": np.arange(len(pph)), "pph": pph})
        fig = px.area(curve, x="moves", y="pph", title="Modeled picks per labor hour vs. moves executed")
        fig.update_traces(line_color=ACCENT, fillcolor="rgba(79,70,229,.12)")
        fig.add_vline(x=n, line_dash="dash", line_color=INK)
        fig.update_layout(xaxis_title="Moves executed", yaxis_title="Picks per labor hour")
        fig.update_yaxes(range=[pph.min() * 0.97, pph.max() * 1.02])
        st.plotly_chart(style(fig, 340), use_container_width=True)
    st.caption(f"Picker model: {S.HANDLE_S_PER_PICK}s handling per pick plus a round trip from the dock at "
               f"{S.WALK_M_PER_S} m/s. Distance falls as busy SKUs move closer to the dock.")

    st.divider()
    st.markdown("##### Policy sensitivity: how much does the A-class cutoff matter?")
    st.caption("Re-runs the whole pipeline at five cutoffs (B cutoff = A + 15 points). A looser A class sends more SKUs "
               "to Priority: more moves, bigger gain, until Priority runs out of space.")
    if st.button("Run sensitivity analysis"):
        st.dataframe(sensitivity(), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ method
with t_method:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("""
##### How it works
1. **Extract.** 400,000 SAP-style inventory movements (goods issues, receipts, transfers) for Q1 2026.
2. **Classify in SQL.** Outbound value and pick frequency per SKU; ABC by cumulative share of value
   (Pareto), speed by pick-frequency tertile. The query below runs live on an in-memory SQLite database.
3. **Map the warehouse.** 800 bins in 3 zones, each with its walking distance to the shipping dock.
4. **Find mismatches.** Rule: A-class (and fast B-class) → Priority; other B and non-slow C → Standard;
   slow C → Reserve. Any bin outside its SKU's zone is misplaced.
5. **Plan and model.** Each misplaced bin goes to the nearest free bin in its target zone, ranked by travel
   saved; a simple picker model turns distance into picks per labor hour.
""")
        st.code(S.CLASSIFY_SQL.strip(), language="sql")
    with c2:
        st.markdown("##### Data dictionary")
        st.dataframe(pd.DataFrame([
            ("records", "doc_no, posting_date, sku_id, movement_type, qty", f"{len(D['records']):,}"),
            ("sku", "sku_id, category, description, unit_value, case_cube", f"{len(skus)}"),
            ("bins", "bin_id, zone, lane, bay, level, distance_m, sku_id", f"{len(bins)}"),
        ], columns=["Table", "Columns", "Rows"]), hide_index=True, use_container_width=True)
        st.markdown("##### Sample movement records")
        st.dataframe(D["records"].head(200), hide_index=True, use_container_width=True, height=260)
        st.info("**All data is simulated** from a fixed random seed. No SKU, value, location or volume comes from a "
                "real company. The structure mirrors the real project so the method can be shown without sharing "
                "proprietary information.")

links = f'<a href="{LINKEDIN}" target="_blank">LinkedIn</a>' + (f' · <a href="{GITHUB_REPO}" target="_blank">Code</a>' if GITHUB_REPO else "")
st.markdown(f'<div class="foot">Portfolio project by {AUTHOR} · {links} · Python · SQL · pandas · Plotly · Streamlit · '
            '⚠ Simulated data: no proprietary information shared</div>', unsafe_allow_html=True)
