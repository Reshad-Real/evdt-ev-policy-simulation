# Allca-Pekarovic et al.: IGBT vs SiC inverter loss at 400 V and 800 V

## Which paper

Two papers by this group fit the description. The exact title you gave belongs to a 2020 conference paper. The "around 2024" paper is the journal follow-up, and the manuscript already cites it as [7].

| | Conference paper (exact title) | Journal paper (2024) |
|---|---|---|
| Title | Comparison of IGBT and SiC Inverter Loss for 400V and 800V DC Bus Electric Vehicle Drivetrains | Loss Modeling and Testing of 800-V DC Bus IGBT and SiC Traction Inverter Modules |
| Venue | 2020 IEEE Energy Conversion Congress and Exposition (ECCE), pp. 6338-6344 | IEEE Trans. Transport. Electrific., vol. 10, no. 2, pp. 2923-2935, Jun. 2024 (online Aug. 2023) |
| Authors | A. Allca-Pekarovic, P. J. Kollmeyer, P. Mahvelatishamsabadi, T. Mirfakhrai, P. Naghshtabrizi, A. Emadi | Same authors, plus J. Reimers (Tesla) |
| DOI | https://doi.org/10.1109/ECCE44975.2020.9236202 | https://doi.org/10.1109/TTE.2023.3300669 |
| Access | Closed (IEEE) | Closed (IEEE) |

## Access limitation (read this first)

Neither full text could be read. Both papers are closed access: OpenAlex and Semantic Scholar list no open-access copy. The IEEE Xplore pages did not load for automated access.

Everything marked as confirmed below comes from the official abstracts, retrieved through Crossref/OpenAlex by DOI, and from the Crossref reference list of the journal paper. Anything that needs the paper body is marked **NOT CONFIRMED**.

The first author's open-access PhD thesis probably contains the same study:

- Allca-Pekarovic, *Dynamometer Characterization of Electric Powertrain Components for Accurate Modeling and Control Design of a Dual-Motor All-Wheel-Drive Electric Vehicle*, McMaster University, 2025.
- DOI https://doi.org/10.71548/24809, MacSphere handle 11375/31014.
- Its abstract says it covers the same inverter study: the Bolt EV model, 1200 V inverters on 160+ kW machines, loss within 100 W, range within 6 km.
- MacSphere sits behind a bot-check page, which I did not bypass. **A person can download it manually from the DOI link above**, and it should answer the open items below.

## Drive cycle(s) and vehicle

- **Vehicle (journal paper, confirmed in abstract):** Chevrolet Bolt EV model. The reference list also cites "2017 Chevrolet Bolt EV" (ref. 34).
- **Vehicle (conference paper):** the abstract says only "a full electro-mechanical vehicle model". It does not name the vehicle.
- **Drive cycles (journal paper):** the abstract says only "simulated over standard drive cycles". **The named cycles are NOT CONFIRMED.** The reference list cites "EPA Test Procedures for Electric Vehicles and Plug-in Hybrids" (2017, ref. 33) and EPA "Annual Certification Data" (2019, ref. 32). That suggests EPA cycles, but it is an inference, not a confirmed fact.

## Reported energy and range differences (all confirmed numbers)

| Comparison | Reported result | Where it appears |
|---|---|---|
| 400 V Si IGBT (600 V devices) to 800 V Si IGBT (1200 V devices) | EV range **+1.2 %** | Journal paper (TTE 2024), abstract |
| 400 V Si IGBT to 800 V all-SiC (1200 V) | EV range **+5.0 %** | Journal paper (TTE 2024), abstract |
| Variable pack voltage and junction temperature vs. fixed-V, fixed-T assumptions | **16 to 27 %** more inverter loss | Journal paper (TTE 2024), abstract |
| Analytical model vs. measurement | measured loss "typically within 100 W" of the model | Journal paper (TTE 2024), abstract |
| Analytical model vs. empirical loss model fitted to measured inverter data | range estimate "within 6 km" | Journal paper (TTE 2024), abstract |
| Full SiC inverter (800 V), normalized to a 600 V IGBT inverter (400 V) | "around a 5% reduction" in energy consumption and "a 5% increase in range" | Conference paper (ECCE 2020), abstract |
| All 1200 V devices (IGBT, hybrid SiC, full SiC) vs 600 V IGBT | all more efficient; SiC shows the largest improvement (no number given) | Conference paper (ECCE 2020), abstract |

**There is no 400 V SiC case in either abstract.** Both papers compare a 600 V IGBT at 400 V with 1200 V devices at 800 V: IGBT, hybrid SiC (Si IGBT with SiC diode) and all-SiC. Whether the body has a separate 400 V SiC configuration is **NOT CONFIRMED**. Any table that cites these papers for a "400 V SiC" result should be checked against the full text.

Per-cycle values (Wh/km, kWh or km for each cycle and configuration) are in the paper body and **NOT CONFIRMED** here.

## Switching frequency, devices modelled, motor losses

- **Device classes modelled (confirmed in both abstracts):** 600 V IGBT, 1200 V IGBT, 1200 V hybrid SiC and 1200 V all-SiC (journal) or "full SiC" (conference).
- **Device part numbers:** NOT CONFIRMED; the abstracts name no parts. The journal reference list includes the SEMIKRON Application Manual (ref. 29) for the loss modelling method.
- **Experimental validation hardware (confirmed):**
  - Journal: a 1200 V IGBT inverter and a 1200 V SiC inverter, "both powering 160+ kW rated traction machines".
  - Conference: "a 180kW traction machine and a 1200V IGBT inverter".
- **Switching frequency:** NOT CONFIRMED (not in the abstracts).
- **Whether motor losses changed with dc-bus voltage:** NOT CONFIRMED (not in the abstracts).

## Cross-check with the manuscript

`build/tables/T02_validation.csv` attributes +5.0 % (800 V SiC vs 400 V IGBT) and +1.2 % (800 V IGBT vs 400 V IGBT) to [allca-2024]. Both numbers match the TTE 2024 abstract exactly. The reference list entry [7] (TTE vol. 10, no. 2, pp. 2923-2935, doi 10.1109/tte.2023.3300669) matches the Crossref metadata.

## Sources used

- Crossref works record (metadata and reference list): https://api.crossref.org/works/10.1109/tte.2023.3300669
- Crossref works record, conference paper: https://api.crossref.org/works/10.1109/ecce44975.2020.9236202
- OpenAlex works records (abstract and open-access status): https://api.openalex.org/works/doi:10.1109/tte.2023.3300669 and https://api.openalex.org/works/doi:10.1109/ecce44975.2020.9236202
- Thesis record: https://api.openalex.org/works/doi:10.71548/24809
