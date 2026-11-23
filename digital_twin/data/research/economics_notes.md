# Economic parameters: current model values vs sources

Companion to `economic_params.csv` (623 rows: DE 193, BD 178, LDC 252). 112 rows are marked `ESTIMATE:` (derived numbers with the derivation in `note`); 9 rest on search-result snippets only and say so in `note`. Every other value was read from the cited page or PDF.

**Conventions**
- Deviation = (current - source) / source. "In line" means within about 10%, "moderate" 10-30%, "large" above 30%.
- Germany vehicle prices are compared net of VAT (gross / 1.19) unless stated.
- Research was done in Nov 2026, so some sources are 2026 documents (ADAC catalogue, BERC June 2026 tariff, Bangladesh FY2026-27 budget). Where a 2025 value exists it is used for the comparison, and 2026 rows are labelled with year 2026 in the CSV.

## 1. LDC archetype (Tanzania and Ethiopia primary)

| Parameter | Current | Sources (USD) | Deviation | Verdict |
|---|---|---|---|---|
| Residential electricity (USD/kWh) | 0.090 | TZ (TANESCO/EWURA, unchanged since 2016): D1 <=75 kWh 0.039, D1 >75 kWh 0.137, T1 general 0.115. ET (EEU, Oct 2025 step, ETB 154/USD): blocks 0.005-0.033. NP 0.029-0.079. UG 0.070 (lifeline) and 0.213 (16-80 kWh). | -21% vs TZ T1; +172% (2.7x) vs ET top block | Plausible for Tanzania, far too high for Ethiopia. Ethiopia's top block equals 0.089 only at the pre-float rate (ETB 57), so the current value matches Ethiopia only if pre-float birr are used. |
| Industrial electricity | 0.080 | TZ T3-MV 0.062, T3-HV 0.060, T2 0.077. ET LV 0.020, MV 0.016 (plus a 2.1-2.9 USD/kW/month demand charge). NP 0.062-0.069. UG 0.057-0.100. | +30% vs TZ T3-MV; 4.0x ET LV | Moderately high for TZ; large for ET |
| Fuel (USD/L) | 1.28 | Dar es Salaam caps, Dec 2025: petrol 1.078, diesel 1.090. ET, Dec 2025: 0.838 for both (subsidised; 0.796 petrol and 0.756 diesel May-Dec 2025). NP 1.154 / 1.054. MZ 1.310 / 1.252. MW 2.00 at the official rate, 1.49 at the importers' market rate. 2026 oil shock: TZ 1.53 / 1.55, UG 1.65 / 1.62. | +19% vs TZ petrol; +53% vs ET; +34% vs TZ-ET mean (0.958) | High for 2025. Close only to Tanzania's Nov 2026 shock level (-16%). |
| Social discount rate | 0.12 | World Bank PADs: TZ 0.12 (2017), 0.10 (2016), 0.06 (2024); ET 0.061 (2016), 0.06 (2018), 0.12 (2023), 0.10 (2024); ASCENT E&S Africa 0.06 (2023) | Top of the 0.06-0.12 range; 2x the latest TZ value | Defensible only as the upper bound. Recent World Bank practice is 0.06-0.10. |
| WACC | 0.14 | No TZ/ET estimate. Kenya proxy 0.085-0.090 (IEA Cost of Capital Observatory, utility PV, 2022). World Bank ASCENT financial rate 0.10. TZ lending rate 0.167 (2020). ET policy rate 0.16 (2026). | +56 to +65% vs Kenya; -16% vs TZ lending rate | Unsourced; lies inside the 0.09-0.17 bracket |
| VoLL (USD/kWh) | 1.9 | ET 0.18 (World Bank PRIME-1, 2024, described as conservative). No TZ value. | 10.6x | Large. No LDC source supports 1.9. |
| Value of time (USD/h) | 1.1 | TZ: Dar BRT passengers 0.44 (2017); bus users 0.45 and car users 1.36 (2014 prices). ET (interurban, converted at ETB 55): work car 0.68, non-work car 0.20, work bus 0.23, non-work bus 0.07. | 2.5x TZ BRT; -19% vs TZ car users; +62% vs ET work car | Large for the transit, 2W and 3W users who dominate the LDC fleet |
| Carbon price (USD/t CO2) | 35 | No national appraisal price in TZ or ET. World Bank shadow price for 2025: 45 (low) to 89 (high), used in WB TZ (2024) and ET (2023, 42 for 2022) appraisals. US EPA 2023: 212 (2025 emissions, 2% discount, 2020 USD). | -22% vs WB low; -83% vs EPA | Below every sourced reference |
| Import duty | 0.42 | ET: fully built EVs 0.20 customs only, exempt from VAT and excise (Nov 2024; 0.15 in 2022). SKD/CKD kits 0.35/0.25 (Jan 2025, ambiguous). ICE cars 0.76-2.32 (ESTIMATE from the tax cascade), and ICE imports banned since 2024. TZ: EVs exempted from engine-capacity excise (2023); total incidence not sourced. | +110% vs ET EV rate | Not supported. Ethiopia taxes EVs and ICE vehicles very differently. |

## 2. BD archetype

| Parameter | Current | Sources (USD) | Deviation | Verdict |
|---|---|---|---|---|
| Residential electricity | 0.078 | BPDB average over all customers 0.079 (Tk 9.68, 2024 tariff); BREB 0.070. Residential blocks (SRO 43-Law/2024): 0.038 lifeline to 0.120 (>600 kWh); 76-200 kWh 0.059; 201-300 kWh 0.062. BERC June 2026: BPDB average 0.089; 76-200 kWh 0.068. | -2% vs BPDB average; +25 to +32% vs typical 76-300 kWh blocks | In line with the system average; high for a typical household. No residential-only average is published. |
| Industrial electricity | 0.089 | LT-C1 0.0882, MT-3 0.0892, HT-3 0.0881 (2024 tariff); June 2026: 0.102-0.103 | About 0%; -13% vs 2026 | In line for 2025 |
| EV charging (no current parameter) | - | BERC LT-D3 charging-station tariff: flat 0.079 (Tk 9.62), time-of-day 0.063-0.100; 2026 flat 0.091 | - | The model could use LT-D3 for charging. |
| Fuel (USD/L) | 1.10 | Nov-Dec 2025: octane 1.00-1.02, petrol 0.97-0.98, diesel 0.84-0.85. Nov 2026 (oil shock): 1.32 / 1.28 / 1.08. CNG Tk 43/m3 = 0.35/m3 = 0.33 per litre gasoline-equivalent (ESTIMATE). | +8 to +10% vs octane; +29 to +32% vs diesel; 3.4x vs CNG | Moderate for petrol 2W. Large for diesel buses, and for CNG 3W if the model applies 1.10 to them. |
| Social discount rate | 0.10 | World Bank 0.12 (2017-2020 PADs) and 0.06 (2021 PAD). ADB 0.09 standard, 0.06 for social/poverty projects. The Planning Commission's official rate was not found. | Within range | OK |
| WACC | 0.115 | India proxy 0.100-0.115 (IEA Cost of Capital Observatory, utility PV, 2024). BD lending rate 0.099 (2024), 0.086 (2025). | 0 to +15% vs India proxy | In line with the proxy |
| VoLL | 2.4 | World Bank PAD 0.50 (2017) | 4.8x | Large |
| Value of time | 1.6 | World Bank WeCARE 0.52-1.71 (interurban; varies by vehicle and purpose) | -6% vs top; 3.1x the bottom | At the top of the range, which fits only working-time car users |
| Carbon price | 45 | World Bank 2025 low 45, high 89. ADB 43.4 (2025 emissions, 2016 USD). WB Bangladesh PAD used 40 for 2020. EPA 212. | 0% vs WB low; -79% vs EPA | In line with the MDB low value |
| Import duty | 0.32 | Total tax incidence on EV cars <= USD 25k: 0.93 (FY2025-26), cut to 0.64 in the FY2026-27 proposal (0.80 up to USD 50k). ICE cars 1,200-1,600 cc: 1.32, rising to 1.56. Built-up e-bikes 0.37 (FY2025-26). E-buses exempt from all levies except VAT. | -66% vs EV cars 2025; -50% vs 2026; -14% vs e-2W | Large for cars; close for e-2W. ICE is taxed far more heavily than EVs. |

## 3. DE archetype

| Parameter | Current | Sources (USD) | Deviation | Verdict |
|---|---|---|---|---|
| Residential electricity | 0.320 | BDEW 2025 0.444 (39.3 ct); 2024 0.434 (40.1 ct). Eurostat DC band 2025 0.435. BDEW separately metered home-charging tariff, Oct 2026: 0.343. | -28% vs BDEW 2025 | Large as a residential price. Close (-7%) to a dedicated home-charging tariff. |
| Industrial electricity | 0.190 | BDEW industry 0.199 (2025), 0.187 (2024); 0.175 excluding levies; Eurostat 0.218 | -5% | In line |
| Public charging (no current parameter) | - | ADAC 2025 motorway fast charging: 0.59-0.89 by contract, 0.72-0.98 ad hoc. Eurostat commercial band IB 0.297. | - | Public DC charging costs 3-5x the industrial tariff. |
| Fuel (USD/L) | 1.85 | E10 1.907 (2025), 1.882 (2024); diesel 1.820 (2025) | -3% / +2% | In line |
| Social discount rate | 0.055 | BVWP 2030: 0.017 (secondary citation; the Methodenhandbuch could not be opened) | 3.2x | Large. No official German source for 5.5% was found. |
| WACC | 0.065 | Fraunhofer ISE 2024 nominal: utility PV 0.053, rooftop 0.050, onshore wind 0.058 (real 0.032-0.039). ECB deposit rate 0.020 (2025). | +12 to +30% | Moderate. No EV- or charging-specific source. |
| VoLL | 12 | ACER-commissioned 2024 study: DE-LU 12,240 EUR/MWh = 13.25 USD/kWh | -9% | In line (the country-to-value mapping should be checked against the slide) |
| Value of time | 24 | Not sourced (BVWP values unreachable) | - | Unverified |
| Carbon price | 110 | UBA MK 3.2: 300 EUR2024/t at 1% PRTP for 2024 = 325; 880 EUR at 0% PRTP = 953. UBA MK 4.0 (2026): 350 EUR2025 = 396. US EPA 212 (2025). BVWP 2030: 145 EUR2012 = 186; updated BMDV value 895 EUR2021 = 1,059. EU ETS 2025 average 83. BEHG 2025: 62. | -66% vs UBA 3.2; -48% vs EPA; +32% vs ETS | Large against every damage-cost value. Sits between market prices and the social cost of carbon. |
| Import duty | 0.06 | EU MFN duty 0.10 (cars, e-buses, e-vans, diesel vans); 0.16 (diesel buses). Chinese-built BEVs pay an extra 0.078-0.353 countervailing duty. Vehicles built in the EU pay 0. | -40% vs MFN | Matches neither 0 (EU-built) nor 0.10 (imported) |

## 4. Vehicle prices (currently the same in every archetype)

| Segment | Current EV / ICE | Sources (USD) | Deviation |
|---|---|---|---|
| 2W | 760 / 1,150 | BD: Walton Takyon Fusion 25RS 1,229; Runner eWave 836 (low-speed, lead-acid); 125 cc ICE 1,025-1,328 (Honda CB Shine SP 1,238). India: Ola Roadster X 1,152 (882 ex-battery, ESTIMATE); Honda Shine 125 960. Uganda (Spiro claim): 1,000, battery probably excluded, vs 1,480. TZ, ET: none. | EV: -38% vs BD Walton; -34% vs India with battery; -14% vs India ex-battery. ICE: -7% vs BD; +20% vs India; -22% vs Uganda. |
| 3W | 2,150 / 3,250 | India: Bajaj WEGO P5009 L5 e-auto 3,751 (2,757 ex-battery, ESTIMATE); Riki L3 e-rickshaw 2,409; RE CNG 2,771; RE petrol 2,424. BD: none. | EV: -43% vs L5 with battery; -22% ex-battery; -11% vs L3. ICE: +17% vs CNG; +34% vs petrol. |
| Car (EV ex-battery) | 17,800 / 21,500 | DE: ID.3 Pure 31,650 net (37,663 gross); ex-battery 24,442 net (ESTIMATE, BNEF Europe pack price 131 USD/kWh). Golf 1.5 TSI 30,971 net (36,855 gross). ICCT/Fraunhofer ISI 2025 medians (gross): BEV 61,020, ICE 51,980. | BEV -27% net (-39% gross); ICE -31% net (-42% gross). The current BEV/ICE ratio (0.83) is close to the sources' (0.79). |
| Van (EV ex-battery) | 24,500 / 28,500 | E-Transit Custom ex-battery 48,045 net; VW e-Transporter ex-battery 48,170 net. Diesel: Transit Custom automatic 50,059 net; VW Transporter TDI 39,811 net (2024). | EV -49%; ICE -28% to -43% |
| 12 m bus (EV ex-battery) | 192,000 / 205,000 | DE (PwC E-Bus-Radar 2026): e-bus 655,400 with battery (EUR 580k); diesel 350,300 (EUR 310k). 2024 e-bus average 624,545 (range 436k-777k). India: no purchase prices; gross-cost contracts 0.52-0.65 USD/km (e-bus) vs 1.14 (diesel). Addis Ababa 2022: about 136,000 per e-bus (scope unclear). No 12 m bus battery capacity was sourced, so no ex-battery figure was derived. | Diesel -41% vs DE 2025. The DE e-bus with battery is 3.4x the current ex-battery value. |

**Structural point.** With the battery included, the EV is dearer than the ICE vehicle in every sourced segment:
- DE car: +2% (list price) and +17% (median).
- DE vans: +15% (Ford) and +26% (VW).
- India 2W: +20%.
- India 3W: +35%.
- DE bus: +87%.

Removing the battery at BNEF pack prices brings the EV to roughly parity or below: car -21%, Ford van -4%, India 3W -1%, India 2W -8%.

The current values make EVs 34% cheaper in 2W and 3W. That is consistent with the sources only if those two prices also exclude the battery; this needs confirming.

German car and van prices are 1.4-2x the current values. A single set of vehicle prices for all archetypes is not supported by the sources.

## 5. Maintenance per km (EV / ICE)

| Segment | Current | Sources (USD/km) | Deviation |
|---|---|---|---|
| 2W | 0.006 / 0.014 | India: ICCT 2021 EV 0.0007-0.0035, ICE 0.0038; ICCT 2024 0.0012 / 0.0073; IEA 0.0020 / 0.0045. Uganda boda (CISL 2025, per-km ESTIMATE): 0.0040 / 0.0074. | EV +50% vs Uganda (5x ICCT 2024); ICE +90% vs Uganda. Both about 2x too high. |
| 3W | 0.011 / 0.026 | India: EV 0.0021-0.0049; CNG 0.0048-0.0070; petrol 0.0047-0.0058 | EV 2.2-5.3x; ICE 3.7-5.4x. Large. |
| Car | 0.030 / 0.062 | ADAC, ID.3 vs Golf (workshop and tyres, incl. VAT): 0.067 / 0.0615. IEA Germany: 0.016 / 0.043. India: 0.0017 / 0.0029. | EV -55% vs ADAC but +83% vs IEA; ICE +1% vs ADAC. ADAC shows near parity between EV and ICE. |
| Van | 0.038 / 0.079 | ADAC Tourneo Custom (passenger version used as proxy): 0.076 / 0.0805 | EV -50%; ICE -2% |
| Bus | 0.19 / 0.335 | IEA EU heavy-truck proxy 0.19 / 0.26. India, Indore (9-10 m buses): 0.092 / 0.229. | EV 0% / +107%; ICE +29% / +46% |

## 6. Charger capex per site (current = hardware + civil)

| Charger | Current | Sources (USD) | Deviation |
|---|---|---|---|
| AC 3.7 kW | 1,000 | US proxy (ICCT 2019, Level 2 outlet upgrade): 680-3,300. No DE, BD or LDC source. ADAC 11 kW home wallbox: 1,356-3,955. | Within the US range (low end) |
| AC 11 kW x2 | 6,500 | Agora Verkehrswende (2021 EUR, public): 4,731 per point = 9,462 per 2-point site, plus 1,183 grid connection. NREL 2023 commercial L2: 4,400-10,600 per port. ICCT 2019: 5,098-7,275 per charger. | -31% vs Agora (-39% with grid connection) |
| DC 50 kW x2 | 49,500 | Agora 35,482 per point = 70,964. ICCT 2019: 46,093-73,907 per charger. IEA EU 2024: 22,000 per (depot) charger. IEA China: 4,500. | -30% vs Agora; within ICCT if one dual-connector charger; +12% vs 2x IEA EU; 5.5x vs 2x China |
| DC 150 kW x2 | 120,000 | Agora 70,964 per point = 141,928. NREL 2023: 112,200-196,200 per port. ICCT 2019: 93,577-122,781 per charger. | -15% vs Agora; -47% to -69% vs 2 NREL ports |
| DC 350 kW x2 | 264,000 | Agora 177,411 per point = 354,822. IEA EU 218,500 per charger. NREL 180,100-285,300 per port. IEA China 31,500. | -26% vs Agora; -40% vs 2x IEA EU; 4.2x vs 2x China |

**Grid connection.** This is missing from the current values unless "civil" includes it. Agora puts it at 118,274 / 236,548 / 473,096 USD per 10-point DC 50 / 150 / 350 kW site, i.e. 11,800-47,300 per point.

**O&M.** IEA uses 5% of capex per year; Agora implies 0.4-6.25%.

**BD and LDC.** The only Asian capex figures are IEA's China values. The current European-level costs probably overstate hardware there, but LDC import, logistics and installation costs were not sourced.

## 7. Parameters not sourced per country

- **Energy**
  - DE: average public AC charging price.
  - BD: the original 2022 BERC EV-charging order (the 2024 government tariff and the 2026 BERC tariff are given instead).
  - UG: a 2025 fuel price (2026 only).
  - MW, MZ: electricity tariffs.
  - TZ, ET: have no regulated EV-charging tariff (flag rows).
- **Vehicle prices**
  - 2W: TZ, ET, NP, MW and MZ have no price; UG has only an operator's claim.
  - 3W: no BD prices (CNG baby-taxi or easybike).
  - Buses: no BD or India purchase prices, and no 12 m e-bus battery capacity.
  - Cars and vans: none for any LDC.
  - Germany: no Mercedes van pair and no ICCT van TCO study.
- **Vehicle taxes**
  - BD: no component breakdown (CD/SD/VAT/RD/AIT/AT), no FY2023-24 or FY2024-25 rates, and no ICE motorcycle total.
  - TZ: the EAC tariff and VAT on vehicles (so no total).
- **Operating costs**
  - BD: nothing country-specific (India used instead).
  - TZ, ET: nothing; Uganda and Kenya are used for 2W only.
  - LDC: no 3W, car or bus maintenance.
  - DE: no 12 m bus maintenance (EU truck proxy).
- **Charging capex**
  - No AC 22 kW figure anywhere.
  - No DE 3.7 kW figure (US proxy used).
  - No India AC or DC 50 kW figure.
  - No African figures (China proxy used).
- **Valuation**
  - DE: BVWP value of time; the BMF discount rate; CEPA 2022 VoLL by consumer type.
  - BD: the Planning Commission discount rate; cost of unserved energy in the IEPMP 2023; Dhaka urban value of time; a BD-specific WACC.
  - TZ: VoLL.
  - TZ, ET: WACC.
  - Addis Ababa: urban value of time.
  - All countries: waiting-time multipliers.
  - BD, TZ, ET: none has a national carbon price.
- **Grid**
  - IEA direct emission factors are paywalled; the direct values for BD and the LDCs are ESTIMATEs from the Ember mix.
  - Malawi: T&D losses.
  - SAIDI/SAIFI: none for BD, ET, NP or MW, and no German SAIFI from BNetzA.
  - Air pollution: no IMF 2023 per-litre country data (the IMF 2017 database, in 2016 USD, is used instead).

## 8. Caveats

- **2026 oil shock.** A Middle East conflict raised fuel prices sharply in 2026: Tanzania's caps are about 49% above Dec 2025, and BD diesel went from Tk 104 to Tk 135. BD, TZ and ET returned to below-cost pricing. The 2026 rows are kept alongside the 2025 values.
- **Ethiopian birr.** The ETB floated in July 2024 (about 57 to about 154 per USD by Nov 2025). Ethiopian tariffs in USD therefore fell about 63% from the exchange rate alone. The World Bank value-of-time figures converted at ETB 55 are overstated in today's dollars.
- **Malawi** fuel is shown at the official rate (MWK 1,751); importers paid about MWK 2,350.
- **UBA cost convention.** UBA Methodenkonvention 4.0 (2026) supersedes 3.2; both are given.
- **US EPA.** The EPA SC-GHG page is withdrawn; its values are from the January 2025 archived copy.
- **World Bank shadow carbon price.** The 2017 guidance note is the newest found.
- **BVWP.** The discount rate and CO2 values come from secondary citations, not the Methodenhandbuch.
- **Ember** values were read through Our World in Data's republished dataset. UBA's 2024 German factor (414 g CO2e/kWh with upstream, per kWh consumed) differs from Ember's 336 (lifecycle, per kWh generated) because of the different basis.
- **Tanzania's grid is gas-dominated** (63% gas, 345 g/kWh). Ethiopia, Nepal, Uganda, Malawi and Mozambique are 82-99% hydro (23-129 g/kWh), so the LDC grid intensity depends strongly on which country is used.
- **Enterprise Surveys.** The 2022-2025 surveys publish median outage durations. The outage hours per year derived from them (BD 157, ET 239, MW 406, NP 82, UG 70, MZ 14 h/yr) are lower bounds. Earlier surveys (2013-2018), which report means, give 104-929 h/yr.

## Exchange rates used

Rates are local currency per USD, except EUR, which is USD per EUR.

- **EUR:** 1.0824 (ECB 2024 average), 1.1300 (ECB 2025 average, via Bank of Finland). Older sources: 1.1827 (2021), 1.2848 (2012).
- **BDT:** 122.0 (Bangladesh Bank, 2025); 124.75 (19 Nov 2026).
- **TZS:** 2,550 (approximate 2025 average of Bank of Tanzania monthly rates); 2,665.69 (21 Nov 2026); 1,653 (2014).
- **ETB:** 154.0 (NBE, Nov 2025); 133.0 (May 2025); 156.66 (implied, about Mar 2026); 55 (pre-float rate used in a World Bank PAD).
- **INR:** 83.67 (RBI 2024); 87.17 (RBI 2025); 82.60 (2023); 73.92 (2021).
- **NPR:** 139.5 (pegged at 1.6 per INR).
- **UGX:** 3,552 (Aug 2025); 3,778 (May 2026).
- **MWK:** 1,751 (official, Sep 2025).
- **MZN:** 63.8 (implied, Jun 2025).
- **GBP:** 0.7824 (2024).
