# GridForce quick guide

GridForce sizes and simulates solar PV and battery projects in Portugal. It calculates self-consumption, buying and selling in the OMIE day-ahead and intraday markets, and participation in REN's ancillary services (aFRR and mFRR), and turns it all into an investment case: NPV, IRR, payback and annual accounts.

This guide covers what you need to test and validate projects. It takes about 10 minutes to read.

## Before you start

- **Quality and Production.** There are two versions of the app. **Quality** (yellow banner at the top) is for testing new improvements and has its own project library. **Production** is the approved version. Results can differ between them while improvements are being tested.
- **Language.** Choose Português or English at the top right. Saved projects do not change with the language.
- **Version.** The version in use is at the bottom of the page, under "Version history", with a description of each change.

## 1. Open or create a project

Open **Project library** at the top of the page.

1. In **Library projects to open**, choose one or more projects (or use **Select all**).
2. You can also upload project files (.json) from your computer and save them to the library.
3. With several projects open, choose in **Project shown in the tabs** which one to view and edit. The **Run the N projects** button simulates all of them at once and shows the portfolio in tab 5.

The library is shared with the whole team. **Saving with the same name replaces the existing project**, so when you change something to test it, change the name (for example "Lousal - test Ana"). **Delete from library** cannot be undone.

To start a new project, click **➕ New project** (above the tabs). The project's own fields are cleared (name, location, consumption, unit costs, fixed price and variants) and the rest keep typical values, which you should check. If a required field is missing, the app tells you which one before running.

## 2. Fill in the tabs

**1. Site and load.** Name, scenario (optional, e.g. Investment Grade), latitude and longitude (PV production comes from PVGIS for those coordinates). Under **Site load**, choose a C&I typical profile with the annual consumption, upload a load profile CSV (one column in kW, 15-minute or hourly), or choose "No load" for generation and storage parks. Enter the import and export limits, if any.

**2. PV and battery.** Tilt, azimuth (180 = south), losses, DC/AC ratio, degradation and unit costs for PV. For the battery: efficiency, SOC window, capacity fade, wear cost, cycle limit per day and costs. The "More battery parameters" and "Degradation, end of life and replacements" sections hold advanced options (cycle-based degradation, capacity augmentation, PCS replacement).

**3. Markets, tariffs and finance.**

- **Markets:** OMIE price period (the 12 months up to the chosen date), day-ahead arbitrage, aFRR, intraday and mFRR. For ancillary services, the activation rate and "accepted bids" have a large impact. GridCog uses 50% accepted bids.
- **Tariffs:** voltage level (ERSE network tariffs), other purchase costs, and PV sales to the market or at a fixed price (PPA).
- **Finance:** start year, duration, discount rate, licensing and grid connection (separate from equipment capex), O&M and insurance (in EUR/year or EUR/day), grid emission factor, price escalation and residual value. Under **Financing and taxes** you can add debt and corporate tax. With these at zero, the case is pre-tax and all-equity, as in GridCog.
- **Fast mode** simulates the first and last year and interpolates the rest. It is enough to compare variants. Turn it off for a more precise final run.

**4. Variants.** One row per configuration to compare: PV kWp, battery kWh and kW. If you know a variant's total capex, enter it under "Total capex (EUR)". It then replaces the calculation from unit costs. To see the battery's value, add a PV-only row.

## 3. Run and read the results

Click **Run simulation**. A run usually takes between 15 seconds and 2 minutes, depending on the number of variants and markets. Tab **5. Results** shows:

- **Best variant, NPV, IRR and payback**, and the **Variant summary** table with every metric.
- **Value stack:** what each value stream gains or loses in year 1 compared with the baseline, which is the same site without the new assets.
- **Cumulative discounted cashflow:** where it crosses zero is the discounted payback.
- **Dispatch on one day:** choose a variant and a day to see what the PV, battery and grid do, with the OMIE price.
- **Annual accounts:** revenue, opex, EBITDA, capex, cashflow and, with financing, tax, interest, DSCR and equity cashflow.
- **Risks and sensitivities:** the tornado chart shows how much the NPV moves when each factor goes up or down. **Run price scenarios** re-simulates with prices from earlier years and gives the P90, P50 and P10 NPV. P90 is the most prudent value.
- **Year-1 energy** and **Baseline and incremental value:** compare a variant with the baseline (no assets) or with another variant (e.g. PV + battery vs PV only), with incremental NPV and IRR and the relative cashflow year by year.
- **Rates applied by year:** average market prices (day-ahead, intraday, aFRR, mFRR), PPA, O&M and insurance used each year.
- **Inter-asset energy flows and avoided emissions:** PV to grid, PV to battery, battery to grid, etc., and the tonnes of CO2 avoided.
- When several projects are run at once, **Scenarios side by side** shows each scenario's totals (e.g. Investment Grade and Ultra Conservative) and each park in each scenario.
- **Run audit:** engine version, data used and automatic checks of the energy balance and limits.

## 4. Export

- **Download report (Word):** full report for the chosen variant, with summary, energy, commercial analysis, sensitivities, variant comparison and assumptions, in the active language. If you run the price scenarios for that variant first, P90/P50/P10 is included too.
- **Download investment case (Excel):** every number, including the 15-minute dispatch for year 1.
- **Download project (.json):** the inputs, to keep or share outside the library.

## 5. How to validate and report

1. Compare with a reference you know (for example, the GridCog report for the same project): capex, PV production, year-1 gain, NPV and IRR. Use the same assumptions on both sides (discount rate, duration, aFRR prices, accepted bids).
2. When something does not match, look first at the **Value stack** and **Energy in year 1**. The difference is usually in one specific value stream.
3. To report a problem or a suggestion, send: project and variant name, the version (bottom of the page), what you expected and what you saw, and if possible the Word report or the Excel file.

## Limitations to keep in mind

- Battery dispatch uses **perfect price foresight**, so market gains are an upper bound. In real operation they are typically lower.
- Ancillary service prices come from ENTSO-E for the last 12 months and are repeated in later years with the chosen escalation. aFRR capacity prices have dropped sharply since June 2025. The "aFRR capacity price adjustment" field lets you test other levels.
- In fast mode, the intermediate years are interpolated.
