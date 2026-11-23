# Representative distribution feeders per archetype: data, verification, recommendation

Prepared 2026-11-21 for the revision answering the reviewer comment that one IEEE 33-bus feeder is not representative. All paths are relative to this folder. Load-flow numbers come from `radial_pf.py` (balanced backward/forward sweep; scripts in `..\..\scripts\feeders\`); the full output is in `verification_log.txt`.

## 1. Recommended feeder sets and weights

The approach is to keep the hourly feeder simulation, but run 3 feeder types per archetype. Each type's per-unit results are scaled to the national level by a weight:

N_t = w_t x D_archetype / D_t,feeder, and the national result is sum over t of N_t x R_t,feeder.

Use customer weights to place EV charging load (or vehicle-ownership data where available). Use energy weights to scale base load and losses. All values and sources are in `feeder_weights.csv` (rows `recommended_weight_*` plus the underlying data).

### Germany: SimBench MV grids, used as published

| Type | Template | Customer weight | Why |
|---|---|---|---|
| Urban | `simbench_mv_urban` (10 kV, 2 x 63 MVA, 14 feeders, 37.8 km cable, LV grids: 133) | 38.9 % | Eurostat degree of urbanisation (EU-SILC ilc_lvho01, 2024): cities |
| Semi-urban | `simbench_mv_semiurb` (20 kV, 2 x 40 MVA, 9 feeders, 67.3 km, LV grids: 110) | 42.4 % | towns and suburbs |
| Rural | `simbench_mv_rural` (20 kV, 2 x 25 MVA, 8 feeders, 116.0 km, 40 % overhead, LV grids: 90) | 18.6 % | rural areas |

The 2025 shares are 38.6 / 43.2 / 18.2. No source splits load, as opposed to population, by urbanisation, so the same weights serve both purposes.

Reasons for these choices:
- SimBench is German, open (ODbL), built with DSOs and checked against 74 real MV grids (about 11,000 km).
- It carries quarter-hourly 2016 profiles.
- Its types map one-to-one onto Eurostat's three degree-of-urbanisation classes.

National cross-check:
- The population-weighted coincident peak of the three grids is 15.2 MW, so 73.7 GW / 15.2 MW is about 4,800 equivalent MV grids, against roughly 4,500 real MV grids (BMWi 2014).
- That implies about 556,000 LV grids, against roughly 500,000.
- MV line length is understated by about 40%: 0.61 km of MV line per LV grid against 1.06 km nationally. Losses scaled by customers will therefore be low for rural networks. One option is to weight losses by line length as a sensitivity.

The commercial grid (`simbench_mv_comm`) is left out because commercial load is spread across all three classes. It is a sensitivity case.

### Bangladesh (11 kV): utility groups mapped to feeder types

| Type | Utilities | Customer / energy weight | Template | Per-feeder targets |
|---|---|---|---|---|
| Urban | DPDC + DESCO (Dhaka) | 6.7 % / 20.3 % | IEEE 69-bus re-based to 11 kV | 2.34 MW, 4.5 km of 11 kV per feeder, ~2,140 consumers (1,512 feeders) |
| Semi-urban | BPDB zones + WZPDCL + NESCO (district towns) | 17.0 % / 22.1 % | IEEE 33-bus re-based to 11 kV (the current model feeder) | 1.58 MW, ~12 km, ~3,470 consumers (WZPDCL+NESCO) |
| Rural | BREB / 80 PBS | 76.3 % / 57.6 % | Indian 28-bus rural 11 kV (`in_rural28`) | ~1.6 MW, ~52 km incl. single-phase laterals (23 km three-phase), ~5,700 consumers (estimate) |

Sources: FY2024-25 annual reports of DPDC, DESCO, BPDB, WZPDCL, the NESCO web profile and the BREB MIS (June 2025). The weights are shares of 48.5 M consumers and 88.2 TWh sold. The per-feeder figures are averages derived from utility totals; no utility publishes a typical feeder.

Reasons for the templates:
- `in_rural28` is the only openly published, explicitly rural 11 kV feeder with complete data that we could verify. It is South Asian, lightly loaded and has the highest path impedance of the 11 kV benchmarks, which matches BREB's long PBS feeders with single-phase laterals.
- Keeping the IEEE 33-bus as the semi-urban type preserves continuity with the original paper while showing it no longer stands for the whole country.
- The IEEE 69-bus is the stiffer of the two classic 12.66 kV feeders (longest-path impedance 9.5 ohm vs 14.4 ohm) and has a dense lateral structure, so it serves as the urban template.

### Least-developed archetype (Tanzania / Ethiopia)

| Type | Template | Customer / energy weight | Evidence for feeder size |
|---|---|---|---|
| Urban (Dar es Salaam, Addis Ababa) | IEEE 69-bus re-based to 11 kV | 23.5 % / 44.8 % | Dar es Salaam 11 kV feeders: 80, mean 11.1 km, max 37.8 km. 33 kV: mean 19.4 km, ~7 MW each (JICA 2017) |
| Semi-urban (secondary towns, peri-urban) | IEEE 33-bus re-based to 15 kV (Ethiopia) or 11 kV (Tanzania) | 48.8 % / 45.3 % | Adwa town 15 kV feeders 6-48 km, mean 34 km, ~8,900 customers each. Holeta 15 kV feeder peak 6.67 MW. Coast region 33 kV mean 73 km |
| Rural 33 kV | `ieee34_balanced` re-based to 33 kV, calibrated (section 2) | 27.8 % / 9.9 % | Shinyanga-Bariadi 33 kV 180 km, 4.5 MW, end voltage 0.862 pu, no voltage control. Coast feeders up to 170 km. Adwa 33 kV feeders 56 and 62 km with <1 MVA installed |

How the weights were built:
- Customer weights average two splits. Tanzania: Census 2022 grid households, Dar es Salaam 25.0 / other urban 48.5 / rural 26.5. Ethiopia (rough): Addis Ababa ~22 / other towns ~49 / rural ~29 % of connections.
- Energy weights are Tanzania only: Dar es Salaam plus Coast region 41.3 % of energy; Zanzibar bulk sales are excluded and the rest renormalised. The town/rural split assumes a rural customer uses 0.4 times an urban customer. With 0.25 or 0.6 the rural energy share becomes 6 % or 13 %.

The IEEE 34 feeder was chosen because it is the standard long, lightly loaded rural feeder with single-phase laterals, and after calibration it reproduces the one quantified Tanzanian rural feeder.

A two-feeder variant, if three is too many: for Bangladesh merge urban and semi-urban (non-BREB: 23.7 % of customers, 42.4 % of energy); for the LDC archetype merge urban and secondary towns.

## 2. Adapting the templates to an archetype

1. **Change voltage with per-unit impedance kept.** Multiply ohms by (kV_new / kV_old)^2, keeping MW loads unchanged. Factors: 12.66 to 11 kV = 0.755; 12.66 to 15 kV = 1.404; 24.9 to 33 kV = 1.756.
2. **Calibrate electrical length.** The IEEE feeders have no line lengths. Expressed in a reference conductor (ACSR of about 100 mm², 0.45 ohm/km; an assumption), after re-basing:

   | Template | Total line equivalent | Longest path equivalent |
   |---|---|---|
   | IEEE 69 at 11 kV | ≈ 45 km | 16 km |
   | IEEE 33 at 11 kV | ≈ 46 km | 25 km |
   | IEEE 33 at 15 kV | ≈ 86 km | 46 km |
   | in_rural28 | ≈ 88 km | 42 km |

   Scaling impedances to the national km-per-feeder gives these factors: Bangladesh urban 0.10, semi-urban 0.26, rural 0.59; LDC urban 0.25, semi-urban 0.39.

   For the LDC rural type, use the IEEE 34 MV part only, with the 4.16 kV branch folded into bus 832. Multiply its ohms by 0.542 at 33 kV (0.31 in pu). This reproduces the Shinyanga-Bariadi point: 0.862 pu at 4.5 MW with 11.8 % losses. At the native 1.77 MW it gives 0.958 pu and 3.5 % losses.
3. **Calibrate load.** Scale loads to the per-feeder peak (tables above), then set N_t from the national demand.

Checks with both calibrations applied (`work\calibrated_check.txt`):

| Case | Vmin | Losses |
|---|---|---|
| Bangladesh urban | 0.995 | 0.3 % |
| Bangladesh semi-urban | 0.991 | 0.5 % |
| Bangladesh rural | 0.887 | 10.6 % |
| LDC urban | 0.979 | 1.3 % |
| LDC semi-urban | 0.968 | 1.9 % |

These fit the expected pattern: stiff short urban feeders limited by current, and weak long rural feeders limited by voltage and losses.

Without length calibration, the templates overstate voltage drop for the urban types. For example, IEEE 69 at the Bangladesh urban load gives 0.946 pu. That makes the uncalibrated set a conservative sensitivity. The present single IEEE 33 feeder corresponds electrically to a 25 km (longest path) 11 kV feeder, closer to a district-town feeder than to Dhaka.

## 3. Verification of the benchmark data (item 1)

| Feeder | Published | This study |
|---|---|---|
| IEEE 69 (12.66 kV, 3,802.1 kW / 2,694.7 kvar) | losses ≈ 225.0 kW, Vmin 0.9092 at bus 65 | **224.99 kW, 0.9092 at 65: match** |
| IEEE 33, current model | 202.67 kW, 0.9131 | 202.68 kW, 0.9131 at 18: match |
| IEEE 34 balanced equivalent (24.9 kV, 1,769 kW nominal, 93.9 km) | input 2,042.9 kW, 290.3 kvar; losses 273.0 kW; V890 0.9193 (3-phase average; phase A 0.9167); V852 0.9633 | with line charging: 2,039.4 kW (-0.2 %), 287.2 kvar; losses 268.5 kW (-1.7 %, no unbalance losses); V890 0.9195; V852 0.9634 |
| Indian 28-bus rural (11 kV, 761.04 kW) | 68.82 kW, 0.9123 | 68.82 kW, 0.9125 at bus 26: match |
| 85-bus (11 kV, 2,570.28 kW) | 316.12 kW, 0.8713 | 316.14 kW, 0.8713 at 54: match only with the bus-60 load (MATPOWER v2 drops it and gives 299.3 kW) |
| Nigeria GRA 11 kV (4,117 kW) | Vmin 0.8295 at bus 25; loss "7.4188 kW" | Vmin 0.8295 at 25: match; loss 762.6 kW, so the published loss is not reproducible (likely a unit slip) |
| SimBench MV export (4 grids) | SimBench `NodePFResult` | all MV nodes within 0.00001 pu, with line charging |

How the IEEE 34 positive-sequence equivalent was built (details in `ieee34_balanced\ieee34_balanced_meta.txt`):
- **Three-phase lines:** Z1 = Zs - Zm (means of the diagonal and off-diagonal terms) from the published Kron-reduced matrices. Config 300 gives 1.1201 + j0.8333 ohm/mile; config 301 gives 1.6901 + j0.8411 ohm/mile.
- **Single-phase laterals:** 3 x Zaa, which preserves both the voltage drop and the loss of a single-phase lateral. It puts bus 822 at 0.9898 pu against a published 0.9895; using Zaa alone gives 1.0088.
- **Distributed loads:** Kersting's exact lumped model, with 2/3 of the load at a node a quarter of the way along the segment and 1/3 at the far end.
- **Regulators:** fixed average taps (1.0458 and 1.0750).

Without regulators the feeder drops to 0.815 pu at bus 838 (constant power, 1.0 pu source), which matters if the national model has no voltage control.

Substation transformer ratings:
- IEEE 34: 2,500 kVA, 69/24.9 kV.
- SimBench: 2 x 25, 2 x 40, 2 x 63 and 2 x 40 MVA.
- Nigeria GRA: a 15 MVA 33/11 kV substation, shared with other feeders.
- Not stated for IEEE 33, 69, 28-bus or 85-bus. The IEEE 69 base-case input is 4.9 MVA, so 5 MVA is a reasonable assumption.

## 4. SimBench answers (item 2)

- **Data without Python:** each grid has a CSV ZIP linked from https://simbench.de/en/download/datasets/ and hosted on the University of Kassel repository; URLs are in `simbench\simbench_mv_meta.txt`. The four MV base grids are downloaded (`simbench\download_*`) and extracted (`simbench\extracted_*`).
- **Grid parameters:** in `simbench\simbench_mv_summary.csv` and the meta file. The documented "sum of loads" is 17.3 / 31.6 / 49.7 / 34.5 MW, the planning reference used in study case hL. The coincident peak of the 2016 time series is 7.5 / 13.4 / 21.0 / 14.9 MW.
- **Share of German grids per type:** **not documented.** SimBench says the grids are synthetic, represent no real supply area and are not meant for extrapolating to real areas (documentation v1.1.0, sections 2 and 4.1.3). External weights are therefore required; Eurostat degree of urbanisation is used here.

## 5. Gaps and caveats

- **No real feeder data for Bangladesh or Africa.** No openly published Bangladeshi or rural African feeder with complete bus/branch data was found. The shared web-search budget ran out during this work, so that search is not exhaustive. Unchecked leads: Yuvaraj, IJET 2018 (28-bus table); a Nigerian study, doi:10.1080/15567036.2019.1673507; World Bank, ADB and JICA documents on Bangladesh distribution.
- **Bangladesh per-feeder figures are partly assumed.** BREB and BPDB-zone 11 kV feeder counts are not published. The rural per-feeder values assume 5 feeders per 33/11 kV substation (range 4-6). BREB's FY2024-25 peak was not found; the FY2023-24 value is used.
- **Ethiopia evidence is thin.** Rural feeder evidence comes from one MSc thesis (Adwa). There is no national 15/33 kV split and no Addis Ababa energy share. EEU's 2021/22 fact sheet (54,300 km MV) is not re-verified because its URL now returns 404.
- **The Tanzanian energy split depends on an assumption** (the 0.4 consumption ratio). The LDC energy weights use Tanzania only.
- **Some published values come from secondary sources.** The originals of the 28-bus and 85-bus papers are paywalled, so their published results were taken from 2025 papers. The rural label of the 85-bus system is unconfirmed.
- **Length calibration rests on an assumed conductor** (0.45 ohm/km). The IEEE 34 calibration rests on one simulated Tanzanian feeder (Mhagama et al. 2021).
- **The SimBench branch CSVs omit shunt susceptance and generation.** These are in `_branch_details.csv` and the original `RES.csv`.

## 6. File index

- `ieee69\`, `ieee34_balanced\`, `in_rural28\`, `in_85bus\`, `ng_osogbo_gra11kv\`: `<name>_branches.csv`, `<name>_loads.csv` and `<name>_meta.txt` (base voltage, transformer, source, verification). `ieee34_balanced` also has `_branch_notes.csv`, `_load_models.csv` and `_devices.csv`.
- `simbench\simbench_mv_{rural,semiurb,urban,comm}\`: radial exports in the same format, plus `_branch_details.csv`. Also in `simbench\`: `simbench_mv_summary.csv`, `simbench_mv_meta.txt`, the downloaded ZIPs, the extracted CSVs and the documentation PDF.
- `feeder_summary.csv`: one row per feeder (voltage, transformer, size, load, published vs computed results, stress margin, recommended role).
- `feeder_weights.csv`: 278 sourced rows (Germany 46, Bangladesh 130, Tanzania 58, Ethiopia 38, recommended LDC weights 6).
- `verification_log.txt`: all load-flow runs.
- `work\`: converted IEEE 34 files, extracted PDF text and the calibration checks.
- Downloads: `downloads_mine\`, `downloads_de\`, `downloads_bd\`, `downloads_tz_et\`, `downloads_feeder\`, one subfolder per download, untrusted, nothing executed. `downloads_mine\opendss_34bus\` holds five 14-byte "404" responses from a failed OpenDSS fetch; they are unused and can be deleted. `staging\` holds the helper agents' raw outputs.
