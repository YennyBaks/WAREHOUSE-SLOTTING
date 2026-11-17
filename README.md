# Warehouse Slotting & Inventory Analytics

An interactive Streamlit dashboard that shows how SKU-velocity analysis and ABC classification
re-slot a warehouse to cut picker travel. It's a portfolio version of a warehouse analytics project
I led at a national beverage manufacturer, rebuilt on **fully simulated data** so no proprietary
information is shared.

**Live app:** _add your Streamlit link here_ · **Author:** Omoyeni Bakinde ([LinkedIn](https://www.linkedin.com/in/omoyeni-bakinde-oguntade-64572983))

## What it does
| Tab | What you see |
|---|---|
| Overview | KPIs, problem → approach → output, real-project results, auto-generated insights, Pareto curve, zone health, ABC mix, speed × ABC heatmap |
| Bin map | All 800 bins by zone and lane, colored by ABC class, with misplaced bins outlined; toggle **As-is / After re-slotting** |
| SKU lookup | Pick any SKU: its class, speed, target zone, current bins and the best free bin to move it to |
| Relocation plan | Every misplaced bin with a destination, ranked by picker travel saved; CSV download |
| What-if & sensitivity | Execute the plan move by move and watch picks/labor-hour and labor cost respond; re-run the pipeline at different ABC cutoffs |
| Method & data | The SQL used for classification, the data dictionary and sample records |

## Method
1. **Data:** 400,000 SAP-style inventory movements (goods issues, receipts, transfers), 320 SKUs, 800 bins in 3 zones.
2. **Classification (SQL):** outbound value and pick lines per SKU; ABC by cumulative share of value (window functions), speed by pick-frequency tertile. It runs on an in-memory SQLite database.
3. **Slotting rule:** A-class and fast B-class → Priority (closest to dock); other B and non-slow C → Standard; slow C → Reserve.
4. **Mismatch detection:** any bin stored outside its SKU's target zone.
5. **Relocation plan:** each misplaced bin goes to the nearest free bin in its target zone, ranked by travel saved.
6. **Picker model:** 22 s handling per pick plus a round trip to the dock at 1.2 m/s, which turns distance into picks per labor hour.

On the simulated data, executing the plan (83 moves) lifts modeled picks per labor hour by about 14%. On the
real project, order-picking efficiency rose 15% within 5 months.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy free on Streamlit Community Cloud
1. Create a public GitHub repo (e.g. `warehouse-slotting`) and upload every file in this folder, including `.streamlit/config.toml`.
2. Go to share.streamlit.io, sign in with GitHub, click **Create app**, then choose the repo, branch `main` and main file `app.py`.
3. Optional: set a custom subdomain such as `omoyeni-warehouse-slotting`.
4. Click **Deploy**. The first load takes about a minute while it simulates the data.
5. Paste the live link at the top of this README and in `GITHUB_REPO` / your LinkedIn and resume.

## Personalize
The top of `app.py` holds your name, LinkedIn, repo link, how the employer is described
(`EMPLOYER_LABEL`) and the real-project results shown on the Overview tab.

## Files
- `app.py`: Streamlit UI
- `slotting.py`: data simulation, SQL classification, slotting engine, relocation plan, picker model
- `requirements.txt`, `.streamlit/config.toml`: dependencies and theme

*All data is synthetic, generated from a fixed random seed. Names, values, volumes and locations do not come from any real company.*
