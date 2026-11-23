# EV adoption data for the developing and LDC archetypes: assessment

Compiled 2026-11-21. Files in this folder:
- `adoption_series.csv`: 186 rows.
- `policy_history.csv`: 77 rows.

Every number has a URL and a quoted or paraphrased source detail. The `note` column flags DERIVED, ESTIMATE, DIGITIZED, PARTIAL, CONFLICT and UPPER BOUND values. Shares are fractions.

**Limits of this compilation**
- The shared web-search budget ran out mid-task. These items were therefore not researched or not verified:
  - Uganda, Tanzania, Malawi and Mozambique;
  - Ethiopia's annual national import counts and its 2025 policy status;
  - Philippines and Sri Lanka policy details;
  - Pakistan's e-bike prices and subsidy disbursement;
  - India's state subsidies, and e-rickshaw and L5 prices.
- The India MHI annexure, the BRTA yearwise table and the Indonesian SRUT figures were checked by me against the primary text. Other rows rely on the source pages as read by research subagents.

## 1. Bangladesh: what exists and what does not

**No published electric share of Bangladeshi two-wheeler sales or registrations exists.**
- BRTA's official yearwise registration table has no fuel or EV split. It gives motorcycle registrations for 2015 to Aug 2026; 2025 was 289,830.
- The motorcycle industry association and the National Board of Revenue (NBR) publish nothing on electric 2W that I could find.

The only official EV figures are cumulative BRTA counts reported in the press:
- **Around 20 EV cars** by March 2023 (Daily Star).
- **"Just over 400" EVs** by April 2024 (The Business Standard via LightCastle).
- **396 EVs as of 13 March 2025** (Bonik Barta), counted from the first registration in October 2021. Of these:
  - 243 motorcycles;
  - 94 jeeps;
  - 54 cars;
  - 3 microbuses;
  - 1 delivery van;
  - 1 auto-rickshaw.

**Implied electric share of new motorcycle registrations: about 0.02%.** This compares 243 e-motorcycles with about 1.08 million motorcycle registrations in 2022–2024. It is DERIVED and cumulative, not annual.

Market-side hints are weak and conflict with each other:
- LightCastle, citing the Dhaka Tribune, says e-bike sales went from about 10 a month around 2018–19 to about 50 a month in 2025. Annualised, that is about 0.2% of registrations; it is indicative only.
- Future Startup (2026) claims more than 50,000 registered e-2W. This contradicts BRTA and probably counts unregistered low-speed scooters.

**Easy-bikes are the large, informal EV segment.** They are battery three-wheelers with lead-acid batteries. They are not registered, and they are explicitly excluded from the 2023 EV Registration and Operation Guideline. All stock estimates are rough:

| Date | Estimate | Source |
|---|---|---|
| 2016 | about 0.2 million | Economist, via Wikipedia; not verified |
| Dec 2021 | 1.2–2.0 million | Daily Star |
| May 2022 | 1–4 million | LiCAS |
| mid-2025 | about 4 million | Economist, via Wikipedia |
| Dec 2025 | 5–5.5 million | LightCastle expert interviews |
| late 2025 | 2.5–6 million | Future Startup |

Against about 330k CNG auto-rickshaws ever registered with BRTA, Bangladesh's three-wheeler stock is roughly 75–95% electric (DERIVED, rough). The two segments are therefore very different:
- **Three-wheelers:** already majority-electric, driven by low upfront cost and informality, not subsidy.
- **Motorcycles:** about 0% electric.

There is no annual easy-bike sales series, so no sales-share diffusion fit is possible for this segment.

**Policy.** There is no purchase subsidy, so there is no price lever with which to identify a Bangladesh-specific price response. The documented items, mostly secondary and partly unverified against NBR tariff orders, are:
- **2020:** BRTA circular allowing EV registration.
- **April 2023:** the EV registration guideline, with a target of 30% EVs by 2030.
- **Import duty on fully built e-bikes:** about 37%. The duty on comparable petrol motorcycles was not found, so the EV tax advantage cannot be computed.
- **FY2025/26 budget:** duty on e-bike parts and battery materials cut from 60% to 1%.
- **Four-wheelers:** EV import duty of about 89% against 150–450% for petrol and diesel cars.
- **Registration and income tax:** a reported 50% registration-fee cut and an advance-income-tax waiver to 2030 (date and legal instrument not verified).

**Implication for the model.** Calibrating the developing archetype's 2W adoption on Bangladesh's own data is not possible. Bangladesh can only provide:
- an order-of-magnitude check: e-2W share of about 0.02–0.2% through 2025, far below India's 5–6%;
- the structural fact that its three-wheeler segment electrified informally.

The 45% hold-out miss is consistent with India-based parameters over-predicting Bangladeshi uptake. That is an inference, not a test.

## 2. Which series can support a sales-share diffusion fit

The test is at least 5 annual points with a policy change inside the window.

| Series | Years | Policy variation inside | Verdict |
|---|---|---|---|
| **India e-2W** registration share (Vahan; MHI official 2018–22, FADA 2023–25) | CY2018–2025 (8) | FAME-II starts Apr 2019 (≈0.19 of price); raised Jun 2021 (≈0.38); cut Jun 2023 (≈0.14); EMPS Apr 2024 (≈0.085); PM E-DRIVE halved Apr 2025 (≈0.042); GST on EVs 12%→5% Aug 2019; ICE-2W GST 28%→18% Sep 2025 | **Best fit candidate.** Clean official series; large up-and-down subsidy swings. Confounded by model launches in 2021–22 and the fuel-price spike. Share kept rising slowly after the cuts (4.0→5.0→6.1→6.3%). Use the MHI/FADA series (no Telangana) consistently; JMK (with Telangana) is the alternative. |
| **India e-3W, all categories** | CY2018–2025 (8) | Same schemes, but lead-acid e-rickshaws were ineligible | Good data, weak price identification. The share rises from 14% to 61% largely without subsidy. Useful as an informal-electrification analogue for Bangladesh's three-wheelers. |
| India e-rickshaw/L3 share of all 3W | CY2019–2025 (7) | Little; L3 mostly unsubsidised | Descriptive only |
| India L5 e-share | Reliable CY2023–2025 only; 2019–22 are upper bounds | PM E-DRIVE cap halved in 2025 | Too short for a fit |
| **Indonesia e-2W** sales share (Ministry of Transport type-approval (SRUT) certificates ÷ industry association (AISI) total sales) | CY2020–2025 (6) | IDR 7M subsidy (≈0.33 of price) Mar 2023–2024; none in 2020–22 or 2025 | **Adequate.** Clean on/off/on/off design, but shares stay below 1.3%, so only the early tail is identified. Basis conflicts in 2023–24: SRUT 62k/77k against subsidised 11.5k/62.5k and IEA's 105k. |
| **Nepal** EV share of four-wheeler imports, by fiscal year | FY2019/20, 2021/22, 2023/24, 2024/25, 2025/26 (5 shares). Units only for FY2020/21 and FY2022/23; FY2018/19 missing | Tax hike FY2020/21; big cut FY2021/22; ICE import ban Apr–Dec 2022; kW-banded rises in FY2023/24 and FY2024/25; credit (loan-to-value) cap Apr 2025; value-based levy FY2026/27 | **Usable but needs harmonisation.** Computed EV tax advantage is 0.37–0.65 of price. Denominators mix cars-only and cars-plus-buses, and some are partial-year. The best price-response variation of any LDC. The shares (2%→12%→76%→73%→74–80%) are an LDC leapfrog case. |
| **Kenya** e-motorcycle share of new motorcycle registrations | CY2021–2025 (5; 2022 only an upper bound) | VAT zero-rating plus excise exclusion from 1 Jul 2023 (≈0.16–0.21 of price); rollback proposals in 2024–26 not enacted | **Marginal fit.** Shares 0.05%, ≤0.4%, 3.6%, 7.1% (4.1% on the revised denominator), and 15.0% (10.5%). The policy change is inside the window. Denominator revisions in Economic Survey 2026 are large, so run sensitivity cases. Good LDC-adjacent analogue for motorcycle electrification. |
| **Vietnam** e-2W sales share | CY2019–2025 (7), plus partial 2026 | **No purchase incentive** (fraction 0 throughout). Hanoi ban announced Jul 2025, later softened. | Cannot identify a price response. Useful for the no-subsidy baseline (5–14% plateau) and as an out-of-sample test. The 2025 jump to 16–22% is a regulatory shock. Mixed ICCT, IEA and commercial sources. |
| **Ethiopia** EV share of Addis Ababa new car registrations | CY2020–2024 (5) | Sep 2022 tax exemptions; Jan 2024 de facto ban on petrol and diesel imports; Aug 2024 VAT reinstated | Technically 5 points, but read off a chart (±15 units), 2024 is itself estimated, and the 2024 driver is a quantity ban, not price. **Out-of-sample or heavily caveated short fit.** No tax-advantage fraction computed. |

## 3. Out-of-sample candidates

- **India e-2W 2024–2025.** Hold out after fitting 2018–2023; this tests the response to the subsidy cuts.
- **Indonesia 2025.** The year after the subsidy ended, when the share fell from 1.22% to 0.86%. This is a direct test of the model's response to withdrawing an incentive.
- **Nepal FY2025/26 and FY2026/27.** FY2026/27 brings a value-based levy that sharply raises tax on more expensive EVs.
- **Kenya 2025.** Fit 2021–2024 and predict 2025.
- **Sri Lanka electric motorcycle registration share:** 8.0% (2022), 9.9% (Jan–Sep 2023), 13.4% (2025), from official Department of Motor Traffic (DMT) tables. Distorted by the import suspension; 2024 is missing. A good point check for a lower-middle-income 2W market.
- **Vietnam 2025–2026 partial** (22–32%), and Ethiopia 2024 (57–60% of new cars).
- **Rwanda.** Company fleet points only: about 4% of motorcycles in Dec 2024 and 13% of Kigali moto-taxis in May 2025. Imports were 4 in 2019 and 5,781 in 2024 (source not named). Plus a ban on new petrol moto-taxi registrations in Kigali from Jan 2025. Qualitative check only.

## 4. Gaps: what does not exist or was not found

- **Bangladesh:**
  - no annual electric 2W sales or registration share;
  - no annual EV registrations by category, only cumulative snapshots;
  - no easy-bike sales series;
  - no verified tariff schedule giving the EV versus petrol-motorcycle tax gap;
  - no e-2W price data.
- **Least-developed country (LDC) motorcycle markets:** Uganda, Tanzania, Malawi and Mozambique are not covered (search budget); Rwanda has no official registrations by fuel. The leads not pursued are the National Institute of Statistics of Rwanda (NISR) statistical yearbooks, Rwanda Revenue Authority (RRA) tax statistics, the Uganda Revenue Authority (URA), and Tanzania's Land Transport Regulatory Authority (LATRA).
- **Nepal:** FY2018/19 is missing; total-car denominators for FY2020/21 and FY2022/23 are missing; the FY2019/20 count is disputed (236 or 575). The Department of Customs annual HS-level spreadsheets (customs.gov.np) would likely close these gaps but were not downloaded.
- **Ethiopia:**
  - no national annual import counts;
  - EV stock figures conflict by up to 7× (15k, 30k, 100k);
  - status of the 2025 import ban unknown;
  - no prices in Ethiopian birr (ETB).
- **Pakistan:** no annual e-2W sales series; only cumulative stock (more than 80k EVs by Jun 2025) and Pakistan Automotive Manufacturers Association (PAMA) totals for petrol 2W and 3W.
- **Philippines:** a single point (2024, about 1.5%).
- **IEA's African e-2W estimate** (about 9,000 in 2024) undercounts Kenya and Rwanda combined. Do not use it as an LDC calibration target.
- **Typical price for e-rickshaw and L5 three-wheelers in India:** not verified, so their subsidy fractions are given as ranges (0.05–0.15).

## 5. Suggested use

- **Developing archetype (2W):** keep India e-2W as the calibration series. Pair it with the derived calendar-year subsidy fraction (`policy_history.csv`: 0.144, 0.190, 0.297, 0.381, 0.241, 0.099, 0.053 for 2019–2025). Use Indonesia 2020–2025 as a second price-identified series. Treat Bangladesh only as a level check (e-2W at or below 0.2%).
- **LDC archetype:** Nepal's four-wheeler import share is the best-documented LDC series with price variation. Kenya's e-motorcycle registration share is the best two-wheeler analogue: Kenya is lower-middle income, not an LDC, but borders the LDC group. Ethiopia and Rwanda are out-of-sample checks.

All three are thin. Report the calibration as indicative and show the denominator-sensitivity cases.
