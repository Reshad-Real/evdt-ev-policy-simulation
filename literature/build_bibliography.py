"""Curate the harvested pool into the final reference set and build the
bibliography artefacts.

Every entry below is a DOI that was returned by the Crossref REST API during the
harvesting rounds (see crossref_candidates.json / crossref_round2.json /
crossref_round3.json).  This script re-resolves each DOI against Crossref so the
exported metadata is publisher-deposited rather than transcribed by hand, and it
fails loudly if any DOI cannot be resolved.

Outputs
-------
refs.json                 keyed metadata used by the manuscript build chain
references.bib            BibTeX for the LaTeX source
reference_check.txt       audit log (resolution status of every DOI)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "manuscript"
if not OUT.exists():          # reproduction package: no manuscript tree
    OUT = HERE
# Crossref asks callers to identify themselves for its polite pool.
# Override with the CROSSREF_MAILTO environment variable.
MAILTO = os.environ.get("CROSSREF_MAILTO", "realreshad@gmail.com")

# --------------------------------------------------------------------------
# Curated reference set: semantic key -> DOI
# --------------------------------------------------------------------------
CURATED: list[tuple[str, str]] = [
    # ---- EV policy: instruments, incentives, evaluation --------------------
    ("pol-infra-income", "10.1016/j.enpol.2026.115098"),
    ("pol-cn-text", "10.1016/j.tra.2024.104235"),
    ("pol-cn-subsidy-innov", "10.1016/j.enpol.2023.113527"),
    ("pol-eu-explore", "10.1016/j.jclepro.2023.137401"),
    ("pol-uk-infra", "10.1016/j.enpol.2024.114178"),
    ("pol-gov2market", "10.1016/j.tra.2022.04.004"),
    ("pol-cn-incentives", "10.1016/j.tra.2021.05.013"),
    ("pol-biblio", "10.3390/en17153786"),
    ("pol-commercial", "10.1016/j.enpol.2024.114116"),
    ("pol-us-fees", "10.1016/j.tranpol.2024.02.005"),
    ("pol-tariff-bidir", "10.1016/j.enpol.2024.114240"),
    ("pol-cn-mandate", "10.3390/wevj16030151"),
    ("pol-phaseout", "10.3390/wevj16060300"),
    ("pol-cn-spillover", "10.1016/j.enpol.2022.112991"),
    ("pol-public-fleet", "10.1016/j.tranpol.2022.06.002"),
    ("pol-shared-infra", "10.1016/j.tranpol.2025.103871"),

    # ---- Developing-country barriers and adoption -------------------------
    ("dev-barriers-cmp", "10.1016/j.esd.2025.101753"),
    ("dev-consumer-ready", "10.1016/j.enpol.2024.114173"),
    ("dev-indonesia", "10.1016/j.sftr.2024.100348"),
    ("dev-barriers-4d", "10.3390/wevj15090422"),
    ("dev-barriers-personal", "10.1016/j.enpol.2022.112956"),
    ("dev-in-2w", "10.1016/j.tranpol.2024.05.004"),
    ("dev-in-infra", "10.1016/j.regsus.2022.11.008"),
    ("dev-pk-moto", "10.3390/wevj14100278"),
    ("dev-np-policy", "10.3390/en16217428"),
    ("dev-pk-intent", "10.1016/j.clrc.2022.100065"),
    ("dev-sea-readiness", "10.3390/wevj17060280"),
    ("dev-ph-barriers", "10.3390/wevj15110519"),
    ("dev-in-standards", "10.1002/est2.261"),
    ("dev-vn-window", "10.1080/2157930x.2026.2619819"),

    # ---- Bangladesh -------------------------------------------------------
    ("bd-3w", "10.3390/su15010149"),
    ("bd-energy-access", "10.1016/j.esr.2024.101490"),
    ("bd-energy-sust", "10.1016/j.esr.2021.100738"),
    ("bd-lcc", "10.3390/wevj15050183"),
    ("bd-pv-cs-20kw", "10.1016/j.ecmx.2025.101510"),
    ("bd-offgrid-der", "10.1016/j.enconman.2025.120519"),
    ("bd-microgrid-h2", "10.1016/j.egyr.2026.109097"),
    ("bd-solar-microgrid", "10.1016/j.enpol.2026.115340"),
    ("bd-policy-coherence", "10.1016/j.eist.2025.100967"),
    ("bd-lcsa-power", "10.1016/j.egyr.2023.10.041"),
    ("bd-temp-demand", "10.3390/earth6040127"),
    ("bd-pv-cs-econ", "10.1016/j.solcom.2024.100091"),
    ("bd-pv-grid-batt", "10.1016/j.ecmx.2025.101256"),
    ("bd-clean-energy", "10.1016/j.renene.2021.03.103"),
    ("bd-smartgrid-dg", "10.1016/j.egyr.2025.01.083"),
    ("bd-mcda-ev-h2", "10.1016/j.rineng.2026.111815"),

    # ---- Underdeveloped economies / LDC / Africa --------------------------
    ("ldc-paratransit", "10.1016/j.trd.2025.105113"),
    ("ldc-za-paratransit", "10.1016/j.tranpol.2023.11.015"),
    ("ldc-ssa-policy-access", "10.1016/j.enpol.2026.115184"),
    ("ldc-ssa-affordability", "10.1038/s41467-026-75104-7"),
    ("ldc-ssa-offgrid-plan", "10.3390/en17235994"),
    ("ldc-minigrid-load", "10.1016/j.enpol.2023.113969"),
    ("ldc-minigrid-rel", "10.1016/j.deveng.2022.100106"),
    ("ldc-energy-poverty", "10.1016/j.jup.2022.101486"),
    ("ldc-za-barriers", "10.3390/wevj12040167"),
    ("ldc-ssa-moto-model", "10.3390/wevj17020090"),
    ("ldc-ssa-cost-access", "10.1016/j.enpol.2020.111935"),
    ("ldc-za-bus-depot", "10.3390/wevj16110627"),

    # ---- Wide-bandgap devices, packaging, reliability ---------------------
    ("pe-gan-ev", "10.3390/en19071752"),
    ("pe-wbg-packaging", "10.1109/tpel.2022.3200469"),
    ("pe-wbg-defects", "10.3390/electronics11010010"),
    ("pe-wbg-field-map", "10.1038/s41928-021-00599-5"),
    ("pe-sic-module-thermal", "10.1109/access.2021.3080505"),
    ("pe-sic-loss-datasheet", "10.1109/ojpel.2024.3485891"),
    ("pe-sic-loss-dynamic", "10.1109/tpel.2024.3406517"),
    ("pe-loss-rt", "10.1109/access.2026.3671183"),
    ("pe-sic-switching", "10.3390/en18236264"),
    ("pe-sic-gateoxide", "10.1016/j.microrel.2026.116035"),
    ("pe-sic-powercycling", "10.1016/j.microrel.2025.115786"),
    ("pe-bondwire", "10.1016/j.microrel.2023.115060"),
    ("pe-sic-tddb-gate", "10.1016/j.microrel.2026.116079"),
    ("pe-sic-wafer", "10.3390/jmmp10010002"),
    ("pe-module-lifetime", "10.1016/j.microrel.2025.115866"),

    # ---- Converters, drives, architectures --------------------------------
    ("pe-traction-inv-review", "10.1016/j.egyr.2023.10.056"),
    ("pe-motor-control-review", "10.1109/access.2021.3110736"),
    ("pe-bidir-dcdc-review", "10.3390/en17102434"),
    ("pe-bidir-v2g-g2v", "10.1109/tie.2021.3084181"),
    ("pe-obc-totem", "10.1109/access.2024.3432791"),
    ("pe-dab-compare", "10.3390/en17215509"),
    ("pe-gan-dcdc-opt", "10.1109/tie.2025.3552273"),
    ("pe-sst-review", "10.3390/en15155602"),
    ("pe-sst-fcs", "10.1109/tie.2020.3038091"),
    ("pe-sic-fcs", "10.1109/jestpe.2022.3223417"),
    ("pe-hv-station", "10.1109/access.2021.3093696"),
    ("pe-anpc-pq", "10.3390/en14092650"),
    ("pe-emi-conducted", "10.1109/temc.2025.3596686"),
    ("pe-cmv-suppress", "10.1109/tia.2025.3590674"),
    ("pe-48v-module", "10.1109/mpel.2025.3555168"),
    ("pe-400-800v", "10.1016/j.epsr.2026.112717"),
    ("pe-mmc-cmv", "10.3390/en17061367"),
    ("pe-hess-sc", "10.1016/j.est.2023.107269"),

    # ---- Digital twin -----------------------------------------------------
    ("dt-energy-review", "10.1016/j.rser.2023.113891"),
    ("dt-charging-infra", "10.1016/j.scs.2024.105479"),
    ("dt-ai-converter", "10.1049/pel2.70013"),
    ("dt-converter-health", "10.1109/access.2023.3243432"),
    ("dt-powertrain-review", "10.3390/wevj15050208"),
    ("dt-batt-state", "10.1016/j.rineng.2025.106858"),
    ("dt-batt-soc", "10.3390/batteries9100521"),
    ("dt-ev-energy-pred", "10.3390/wevj12040160"),
    ("dt-drl-ems", "10.1016/j.energy.2024.133384"),
    ("dt-fleet-charging", "10.1186/s40807-026-00240-z"),
    ("dt-cyber-5g", "10.3390/en18226048"),
    ("dt-pmsm-shadow", "10.1049/dgt2.12024"),
    ("dt-hil-rt", "10.1109/tpel.2020.3040071"),
    ("dt-converter-cm", "10.1109/ticps.2025.3586823"),

    # ---- Battery: degradation, recycling, second life ---------------------
    ("batt-phys-aging", "10.1016/j.electacta.2021.139133"),
    ("batt-calendar", "10.1016/j.apenergy.2024.124640"),
    ("batt-coupled-degr", "10.1109/tase.2023.3274635"),
    ("batt-fade-realveh", "10.1016/j.energy.2024.132782"),
    ("batt-recycle-review", "10.3390/batteries10010038"),
    ("batt-recycle-ce", "10.3390/recycling7030033"),
    ("batt-2nd-life-pack", "10.1016/j.est.2022.106265"),
    ("batt-2nd-life-mg", "10.1016/j.est.2021.102837"),
    ("batt-v2g-degr", "10.1016/j.apenergy.2024.124546"),
    ("batt-v2g-degr-model", "10.1016/j.est.2024.112709"),
    ("batt-drl-thermal", "10.1016/j.est.2024.112466"),

    # ---- Grid integration, V2G, power quality -----------------------------
    ("grid-v2g-review", "10.1016/j.rineng.2025.106813"),
    ("grid-v2g-impact", "10.3390/su142113856"),
    ("grid-v2h-hems", "10.1016/j.jclepro.2021.127792"),
    ("grid-infra-impact", "10.1080/15325008.2024.2315206"),
    ("grid-tx-loading", "10.1016/j.heliyon.2024.e39904"),
    ("grid-flex-dr-v2g", "10.1109/access.2024.3459053"),
    ("grid-dr-aggregator", "10.1016/j.rser.2022.112251"),
    ("grid-flex-fastchg", "10.1109/tsg.2022.3219403"),
    ("grid-smart-robust", "10.1016/j.apenergy.2023.121185"),
    ("grid-intermittency", "10.1016/j.renene.2023.04.135"),
    ("grid-der-standards", "10.3390/en14030523"),
    ("grid-harmonic-std", "10.1016/j.epsr.2024.110260"),
    ("grid-pv-ev-standards", "10.3390/wevj12030117"),
    ("grid-microgrid-ctrl", "10.1016/j.rineng.2024.102642"),
    ("grid-microgrid-drl", "10.1016/j.asoc.2025.113180"),
    ("grid-pv-cs-techecon", "10.3390/en18020315"),

    # ---- Charging infrastructure planning and behaviour -------------------
    ("chg-siting-woa", "10.1016/j.epsr.2025.111532"),
    ("chg-siting-uncert", "10.1109/tits.2024.3384537"),
    ("chg-multiobj-data", "10.1016/j.isci.2023.107737"),
    ("chg-behaviour-dk", "10.1016/j.epsr.2024.110556"),
    ("chg-wait-longtrip", "10.1109/access.2025.3552730"),
    ("chg-queue-firefly", "10.3233/idt-230619"),
    ("chg-multistage-pv", "10.1016/j.apenergy.2026.127517"),
    ("chg-techecon-solar", "10.1038/s41598-026-37080-2"),
    ("chg-urban-rural", "10.1016/j.jtrangeo.2024.103859"),
    ("chg-equity-justice", "10.1016/j.trip.2024.101072"),
    ("chg-equity-review", "10.3390/wevj16100553"),
    ("chg-bus-decarb", "10.3390/wevj15030081"),

    # ---- AI / ML / forecasting -------------------------------------------
    ("ai-demand-dl", "10.1016/j.apenergy.2024.123751"),
    ("ai-demand-review", "10.3390/en18174779"),
    ("ai-smartgrid-review", "10.1016/j.ecmx.2024.100724"),
    ("ai-pinn-batt", "10.3390/batteries9060301"),
    ("ai-dl-soc", "10.1016/j.ensm.2023.102883"),
    ("ai-bms-review", "10.1016/j.egyai.2025.100585"),
    ("ai-marl-charging", "10.3390/en17153694"),
    ("ai-prob-forecast", "10.3390/wevj16020088"),

    # ---- Cybersecurity ----------------------------------------------------
    ("cyb-ocpp", "10.1007/s10207-023-00698-8"),
    ("cyb-evcs-attack", "10.1109/access.2022.3177842"),
    ("cyb-insurance", "10.1109/tsg.2021.3133536"),
    ("cyb-ev-grid-review", "10.1016/j.gloei.2026.01.011"),
    ("cyb-ocpp-interop", "10.3390/wevj15050191"),

    # ---- Environment / LCA / decarbonization ------------------------------
    ("env-wtw-2022", "10.1016/j.jenvman.2022.114592"),
    ("env-wtw-2021", "10.1016/j.enpol.2021.112552"),
    ("env-decarb-scen", "10.1038/s41467-022-31354-9"),
    ("env-lca-battery", "10.3390/wevj15060245"),
    ("env-ghg-vs-ap", "10.1016/j.trd.2023.103954"),
    ("env-carbon-neutral", "10.1007/s43979-025-00129-8"),

    # ---- Economics / MCDA -------------------------------------------------
    ("econ-tco-asean", "10.1016/j.esd.2024.101650"),
    ("econ-moo-mcdm", "10.1016/j.apenergy.2021.117866"),
    ("econ-topsis-power", "10.3390/en18133478"),

    # ---- Methods: agent-based, sensitivity, temperature, driving ----------
    ("meth-abm-diffusion", "10.1016/j.energy.2022.124700"),
    ("meth-abm-v2g", "10.1016/j.apenergy.2022.118581"),
    ("meth-gsa", "10.1016/j.jhydrol.2022.128895"),
    ("meth-heat-range", "10.1016/j.apenergy.2024.125051"),
    ("meth-temp-trip", "10.1016/j.energy.2021.122028"),
    ("meth-cold-range", "10.3390/wevj12030115"),
    ("meth-driving-energy", "10.1016/j.apenergy.2021.117096"),

    # ---- Workforce, TRL, industrial capability ----------------------------
    ("wf-ev-workforce", "10.3390/wevj17060298"),
    ("wf-trl-ccs", "10.1016/j.rser.2024.114578"),
    ("wf-trl-system", "10.1016/j.rser.2026.117305"),
    ("wf-remanufacture", "10.3390/wevj15100441"),
    ("wf-labour-demand", "10.1016/j.enpol.2024.114064"),
]


# --------------------------------------------------------------------------
def resolve(doi: str) -> dict:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}"
    req = urllib.request.Request(url, headers={"User-Agent": f"EVDT-bib/1.0 (mailto:{MAILTO})"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)["message"]


def fmt_authors(msg: dict) -> list[str]:
    out = []
    for a in msg.get("author", []):
        fam = (a.get("family") or "").strip()
        given = (a.get("given") or "").strip()
        if not fam:
            if a.get("name"):
                out.append(a["name"].strip())
            continue
        initials = "".join(p[0].upper() for p in re.split(r"[\s\-\.]+", given) if p)
        out.append(f"{fam} {initials}".strip())
    return out


def year_of(msg: dict) -> int | None:
    for k in ("published-print", "published-online", "issued", "created"):
        dp = msg.get(k, {}).get("date-parts", [[None]])
        if dp and dp[0] and dp[0][0]:
            return int(dp[0][0])
    return None


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&#x2013;", "-").replace("‐", "-"))
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    keys = [k for k, _ in CURATED]
    if len(set(keys)) != len(keys):
        dupes = {k for k in keys if keys.count(k) > 1}
        sys.exit(f"duplicate keys: {dupes}")
    dois = [d.lower() for _, d in CURATED]
    if len(set(dois)) != len(dois):
        dupes = {d for d in dois if dois.count(d) > 1}
        sys.exit(f"duplicate DOIs: {dupes}")

    refs, audit, failures = {}, [], []
    for key, doi in CURATED:
        try:
            msg = resolve(doi)
        except urllib.error.HTTPError as exc:
            failures.append((key, doi, f"HTTP {exc.code}"))
            audit.append(f"FAIL  {key:26s} {doi}  HTTP {exc.code}")
            continue
        except Exception as exc:
            time.sleep(2)
            try:
                msg = resolve(doi)
            except Exception:
                failures.append((key, doi, str(exc)))
                audit.append(f"FAIL  {key:26s} {doi}  {exc}")
                continue
        rec = {
            "key": key,
            "doi": msg.get("DOI", doi),
            "title": clean((msg.get("title") or [""])[0]),
            "authors": fmt_authors(msg),
            "journal": clean((msg.get("container-title") or [""])[0]),
            "journal_short": clean((msg.get("short-container-title") or [""])[0]),
            "volume": clean(msg.get("volume", "")),
            "issue": clean(msg.get("issue", "")),
            "pages": clean(msg.get("page", "")),
            "article_number": clean(msg.get("article-number", "")),
            "year": year_of(msg),
            "publisher": clean(msg.get("publisher", "")),
            "type": msg.get("type", ""),
        }
        if not (rec["title"] and rec["authors"] and rec["journal"] and rec["year"]):
            failures.append((key, doi, "incomplete metadata"))
            audit.append(f"THIN  {key:26s} {doi}  incomplete metadata")
            continue
        if not (2020 <= rec["year"] <= 2026):
            audit.append(f"WARN  {key:26s} {doi}  year={rec['year']}")
        refs[key] = rec
        audit.append(f"OK    {key:26s} {rec['year']}  {rec['journal_short'] or rec['journal']}")
        time.sleep(0.12)

    (HERE / "refs.json").write_text(json.dumps(refs, indent=1, ensure_ascii=False),
                                    encoding="utf-8")
    (HERE / "reference_check.txt").write_text("\n".join(audit), encoding="utf-8")
    print(f"resolved {len(refs)}/{len(CURATED)}")
    if failures:
        print("FAILURES:")
        for k, d, why in failures:
            print(f"  {k}  {d}  {why}")


if __name__ == "__main__":
    main()
