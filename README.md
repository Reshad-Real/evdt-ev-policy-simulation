# evdt: electric-vehicle policy simulation with device-level power electronics

Reproduction package (release v2.0) for the manuscript

> **Device-Level Power-Electronics Modeling in Electric-Vehicle Policy
> Assessment: A Calibrated Simulation Across Development Contexts**
>
> Md. Reshad Al Muttaki, Alvi Ibn Amzad Anil, Sadia Afrin and Shameem Hasan
> Department of Electrical and Electronic Engineering, BSRM School of Engineering,
> BRAC University, Dhaka, Bangladesh

Every number, figure and table in the revised paper is produced by the code in
this package; the in-text numbers are written to `results/numbers.json`. The
first version of the manuscript is reproduced by release v1.0 of
https://github.com/Reshad-Real/evdt-reproduction-package.

## What changed from v1.0

- The model is no longer called a digital twin: it has no automated data link to
  a physical system.
- **Adoption** is modelled as the electric share of new registrations, stepped
  one year at a time, with the stock following through fleet turnover; price
  and charging provision act on the sales ceiling relative to the reference
  package (`evdt/mobility.py`, `evdt/engine.py: adoption_step`).
- **Calibration.** `digital_twin/calibrate.py` fits the diffusion to the
  battery-electric share of German new cars (KBA, fit 2014-2022, hold-out
  2023-2025, with the federal purchase premium as paid; price elasticity from
  the European panel estimate of Muenzel et al., 2019) and, jointly, to the
  electric share of two-wheeler sales in India (fit 2018-2022, hold-out
  2023-2025), Indonesia and Kenya with the incentives paid. It also reconciles
  base-year emissions with the German CRF inventory and national transport
  totals.
- **Power electronics** resolved by vehicle segment: 60 V two- and three-wheeler
  drives with 100 V devices, a 1200 V IGBT and three-level legs at 800 V, and
  efficiency on 0.1 s drive cycles with the operating point set by torque and
  speed. Thermal swings are reported; lifetimes are withdrawn.
- **Accounting.** Abatement is reported relative to the reference package S0,
  the social cost-benefit account excludes transfers and counts fuel savings
  once, and the bus lever no longer re-weights the electric fleet.
- **New analyses** (`digital_twin/run_revision_analyses.py`): device-level,
  technology-lookup and constant-efficiency representations under identical
  levers; network ablation; concentrated charging; site-level versus pooled
  queues; adoption structure; sequencing; emission-intensity decomposition.
- **Robustness.** TOPSIS weight sensitivity, a 19-parameter Monte Carlo
  including device and model uncertainty, and surrogate accuracy on independent
  test simulations with per-objective Pareto verification.

### Further changes in this release (after internal review)

- **Devices fitted to datasheets.** `fit_devices.py` fits the traction-inverter
  slots to Infineon FS820R08A6P2B, FS380R12A6T4B, FS01MR08A8MA2C and
  FS03MR12A6MA1B and Transphorm TP65H035G4WS (`data/devices/`), and fits an
  effective PWM ripple to the ORNL light-load efficiency maps of the 2010 Prius
  inverter (650/500 V fitted, 225 V held out). Conduction in the freewheeling
  interval of a bridge leg (diode or reverse channel), missing before, is
  included. The silicon super-junction, 100 V and charger devices are fitted to
  discrete parts (Infineon IPDQ65R017CFD7A, IAUT300N10S5N015, IMZA65R027M1H and
  IMZA120R022M2H; EPC2302) from their datasheet tables
  (`data/devices/datasheet_tables.csv`, every value with conditions and page);
  switching energies a datasheet does not tabulate are estimated from switching
  times and charges, calibrated on IMZA120R022M2H. Only the on-board charger's
  silicon IGBT keeps a representative class.
- **Vehicle energy use** is computed on the same drive cycles as the converter
  efficiency (`powerelectronics.cycle_wheel_energy`), replacing a mean-speed
  estimate that understated urban consumption.
- **Silicon-loss brackets** from both sides: silicon losses scaled up until the
  published drive-cycle gain of SiC is reproduced, and down until the measured
  99 % peak efficiency of production IGBT inverters is reproduced
  (`silicon_sensitivity.csv`, `silicon_sensitivity_low.csv`).
- **Standard drive cycles** (`data/cycles/`): WLTC class 3b, its low and
  medium phases, the Indian Driving Cycle, WMTC; EPA UDDS/HWFET for the
  comparison with Allca-Pekarovic et al.
- **Adoption transfer.** Bangladesh and the least-developed archetype take the
  price elasticity and mean Bass coefficients of a two-wheeler panel (India,
  Indonesia, Kenya; `data/adoption_panel.csv`); leaving each country out
  measures the transfer error, and the assessment is repeated with each
  country's coefficients.
- **Economics re-sourced** per archetype (`data/research/economic_params.csv`):
  tariffs, fuel prices by fuel, discount rates, carbon values, VoLL, value of
  time, vehicle prices, maintenance, air-pollution damage per litre and charger
  costs.
- **Three feeder types per archetype** (`data/feeders/`): SimBench for
  Germany; IEEE 69/33-bus and an Indian rural 11 kV feeder for Bangladesh;
  IEEE 69/33-bus and the IEEE 34-node feeder for the least-developed
  archetype; the annual power flow is interpolated in the feeder total.
- **Surrogate.** A Gaussian process (ARD kernel) replaces the random forest;
  Sobol indices use the Janon first-order estimator with bootstrap intervals.

## What is here

```
digital_twin/                 the model and the pipeline that runs it
  evdt/                       the model package
    config.py                   device, vehicle and archetype parameters
    powerelectronics.py         device, converter, drive-cycle and thermal models
    battery.py                  equivalent circuit, charge acceptance, ageing
    mobility.py                 road load, Bass adoption, turnover cap, demand shapes
    charging.py                 site-level M/M/c queues, portfolio, capital cost
    grid.py                     radial feeders from data, backward/forward sweep
    environment.py              temperature, solar, availability, price
    economics.py                ownership cost, NPV, well-to-wheel emission factors
    policy.py                   the twenty-lever policy engine
    scenarios.py                archetypes and the seven policy packages
    engine.py                   the coupled annual and multi-year simulation
    metrics.py                  indicators, TOPSIS, weight sensitivity, MAC
    learning.py                 Gaussian-process surrogate
    uncertainty.py              Latin hypercube, Monte Carlo, Morris, Sobol
    optimization.py             NSGA-II
  run_all.py                  the whole pipeline, in order
  fit_devices.py              stage -1: device parameters from datasheets, ripple fit
  calibrate.py                stage 0: adoption calibration and transfer, inventory check
  run_deterministic.py        stage 1: 21 runs, converter characterisation, ranking
  run_revision_analyses.py    stage 1b: analyses added in the revision
  run_validation.py           stage 4: verification and validation
  run_uncertainty.py          stage 2: Monte Carlo and Morris screening
  run_optimization.py         stage 3: surrogate, Sobol, NSGA-II, frontier check
  data/                       calibration and inventory data with sources,
                              instrument-to-parameter mapping
    devices/                    datasheet points and measured inverter efficiencies
    cycles/                     standard drive cycles (1 Hz)
    feeders/                    benchmark feeders (FEEDERS.md: sources, checks)
    research/                   economic parameters, adoption series and feeder
                                weights with their sources
  configs/                    fitted device library, calibrated adoption coefficients
results/                      all generated datasets (CSV/JSON) and run logs
figures/                      the figures of the paper and its supplement,
                              600 dpi PNG and vector PDF
tables/                       the tables of the paper as CSV; supplementary/
                              the supplementary tables
literature/                   reference metadata (Crossref-verified) and the
                              scripts that draw the figures and tables
  tte_figures.py              all figures
  tte_tables.py               all tables
  tte_numbers.py              every number quoted in the text -> results/numbers.json
```

The manuscript text, the built documents and the scripts that typeset them are
not included.

## Requirements

| Requirement | Version used |
|---|---|
| Python | 3.14.10 |
| numpy | 2.5.5 |
| scipy | 1.18.1 |
| pandas | 3.1.1 |
| matplotlib | 3.11.2 |
| scikit-learn | 1.9.1 |

```bash
python -m pip install -r digital_twin/requirements.txt
```

No internet access is needed to run the model.

## Reproducing the results

```bash
cd digital_twin
python run_all.py          # full pipeline
python run_all.py --fast   # without the Monte Carlo and the optimisation
```

`run_all.py` runs, in order: `fit_devices.py`, `calibrate.py`, `run_deterministic.py`,
`run_revision_analyses.py`, `run_validation.py`, `run_uncertainty.py`,
`run_optimization.py`, then `literature/tte_tables.py`,
`literature/tte_figures.py` and `literature/tte_numbers.py`. The calibration
must run first: it writes `configs/calibrated_adoption.json`, which the
scenarios read. The Monte Carlo and the optimisation are the expensive stages
(tens of minutes each on one core); both accept `--arch <archetype>` to run one
archetype and `--merge` to combine the per-archetype outputs, so the three
archetypes can run in parallel.

## Tracing a result

Section S12 of the paper's Supplementary Material maps each figure and table
number of the paper to these scripts.

| Result | Produced by | Reads (results/) |
|---|---|---|
| Model structure | `tte_figures.py: f1_structure` | - |
| Calibration and validation (figure and table) | `tte_figures.py: f2_validation`, `tte_tables.py: validation` | `calibration_*.csv`, `emission_reconciliation.csv`, `validation_converter_literature.csv`, `validation_ieee33.csv`, `validation_benchmark_feeders.csv`, `device_fit.csv`, `light_load_fit.csv`, `calibration_transfer.csv`, `validation_queue.csv`, `validation_energy_balance.csv` |
| Converter performance | `tte_figures.py: f3_converters` | `converter_*.csv` |
| Device-level, lookup and constant representations | `tte_figures.py: f4_representation` | `pe_lever_marginal.csv`, `pe_mode_ranking.csv` |
| Package outcomes (figure and tables) | `tte_figures.py: f5_outcomes`, `tte_tables.py: outcomes`, `outcomes_full` | `scenario_records.csv`, `policy_ranking.csv`, `horizon_summary.csv`, `topsis_weight_sensitivity.json` |
| Abatement and charging emission intensity | `tte_figures.py: f5_outcomes` (second figure) | `policy_ranking.csv`, `emission_intensity_decomposition.csv` |
| Network and robustness | `tte_figures.py: f6_robustness` | `network_ablation.csv`, `feeder_concentration.csv`, `monte_carlo_samples.csv`, `topsis_weight_sensitivity.json` |
| Verification and inventory checks | `tte_figures.py: fs1_verification` | `emission_reconciliation.csv`, `validation_queue.csv` (IEEE 33-bus solved in place) |
| Surrogate accuracy and Sobol indices | `tte_figures.py: fs2_surrogate` | `sensitivity_sobol.csv`, `surrogate_performance.csv`, `pareto_verification.csv` |
| Converter and adoption calibration | `tte_figures.py: fs3_calibration` | `light_load_fit.csv`, `calibration_adoption.csv`, `calibration_transfer.csv` |
| Thermal swings | `tte_figures.py: fs5_thermal` | `converter_reliability.csv` |
| Instruments and model parameters | `tte_tables.py: s_instruments` | `digital_twin/data/instrument_mapping.csv` |
| Numbers in the text | `tte_numbers.py` | all of the above |

## Determinism

All stochastic streams use explicit seeds: `SEED = 20260801` in
`run_deterministic.py` (also used by the revision analyses), `4242` for the
Monte Carlo, `909` for the surrogate and NSGA-II with per-archetype design seeds
1-3. Nothing reads the wall clock, so reruns on the same package versions
reproduce the results.

## Verification and validation (this release)

| Check | Result |
|---|---|
| Adoption hold-out, German BEV share of new cars 2023-2025 | MAPE 15 % |
| Adoption hold-out, Indian two-wheeler sales 2023-2025 (panel fit) | MAPE 24 % |
| Adoption transfer, leave one of India/Indonesia/Kenya out | MAPE 53-170 % |
| Adoption transfer to Vietnam (no incentive) | MAPE 20 % |
| Price response, German series alone vs European panel | +8.1 % vs +5-7 % of sales per 1,000 EUR |
| Datasheet fit, power modules and discrete parts | every point within 8 % |
| Light-load efficiency, 2010 Prius inverter (225 V held out) | MAE 1.6 points (2.3 without ripple) |
| Si IGBT inverter peak efficiency | 98.4-98.7 % (production parts > 99 %) |
| Drive-cycle range gain, 800 V SiC vs 400 V Si IGBT (EPA combined) | 4.3 % (published 5.0 %) |
| Silicon-loss brackets: x1.1 (SiC gain 5.0 %) / x0.59 (IGBT peak 99 %) | German PE instruments 7.9 / 2.8 bn USD (base 6.9); no rank changes |
| Electric two-wheeler consumption, Bangladesh 2035 (IDC) | 27 Wh/km (reported 20-60) |
| Base-year road CO2, Germany vs CRF 2024 | 99.0 vs 102.85 Mt (4 %) |
| IEEE 33-bus losses / minimum voltage | 202.68 kW / 0.9131 pu (published 202.67 kW / 0.9131 pu) |
| IEEE 69-bus and Indian 28-bus losses / minimum voltage | within 0.01 kW / 0.0002 pu of published |
| Annual power flow, interpolated vs direct | error 4e-7 pu |
| Erlang-C queue vs discrete-event simulation | within 2.1 % |
| Energy-balance relative residual | 1.3e-16 |
| Gaussian-process surrogate, NPV on independent test runs | R2 0.99-1.00 (random forest 0.79-0.95) |
| Outputs inside reported literature ranges | 14 of 15 (the exception is reported in the paper) |

## Data sources

Kraftfahrt-Bundesamt (German stock and vehicle-kilometres), Eurostat UNFCCC CRF
inventory, Climate Watch transport totals, Bangladesh Road Transport Authority
registrations, Ember grid carbon intensity, ICCT and IEA Global EV Outlook
(Indian two-wheeler sales), U.S. EPA emission factors and the JEC well-to-wheels
report; Infineon and Transphorm datasheets; ORNL inverter benchmarking; UNECE,
EPA and ARAI drive cycles; SimBench and the IEEE/Indian benchmark feeders;
national regulators, statistics offices, the World Bank, IMF, IEA, ICCT and UBA
for the economic parameters. Each row of `digital_twin/data/calibration_data.csv`,
`adoption_panel.csv`, `inventory_data.csv`, `devices/datasheet_points.csv`,
`devices/datasheet_tables.csv` and
`research/economic_params.csv` names its source. Only the on-board charger's
silicon IGBT keeps representative device parameters.

## Known limitations

Stated in full in the paper: benchmark medium-voltage feeders (three types per
archetype) calibrated to national line lengths, and no low-voltage networks;
adoption calibrated for Germany and, for Bangladesh and the least-developed
archetype, transferred from a three-country two-wheeler panel with a large
transfer error; behaviour aggregated by segment; switching energies of most
discrete parts estimated from datasheet switching times and charges; the
converter model understates the peak efficiency of production silicon
inverters, which the silicon-loss brackets cover.

## Licence

Code is released under the MIT Licence (see `LICENSE`). The generated datasets,
figures and tables are released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## Citing this work

Please cite the paper. `CITATION.cff` carries the machine-readable metadata.
