# Profiling Notes
*Write what you find while profiling (Phase 1). This becomes evidence of your analytical process.*

| # | File | Field | What looks wrong | Example value | How I'll fix it |
|---|---|---|---|---|---|
| 1 | accounts_export |Country| Country grouping incorrect | Germany has value : "GER","Germany"; Franch has :"FR", "FRANCE", etc |  I'll all the fuzzy matches and group them together and rename them in standardized format for proper dimensional grouping on the dashboard
|2 |Opportunities_YYYY_MM|Sales_Stage|The grouping is improper |stage 1 looks: "Stage 1: Discovery (0-50%)","Discovery"|fuzzy match or text containing workflow to standardized names in this column| 
|3 |Opportunities_YYYY_MM|Probability (%) (v1) / Win_Probability (v2)|Rep-entered probability is not in a standard format: whole numbers, percentages and decimals are mixed, and some are blank|"75", "75%", "0.75", "0.5", "1.0", ""|1) Remove "%" 2) Convert to a number 3) If the raw value contained "." and the number is ≤ 1, multiply by 100 (so 0.5 → 50, 1.0 → 100). Keep blanks as Null. Result = `rep_probability` (0–100), used only to measure forecast honesty; the forecast uses governed probabilities from `stage_rules.csv` (Phase 4)|
|4 |Opportunities_YYYY_MM||Explicit stage status is not present if it is active/lost/stale ||Put in a formula logic to check if the deal has been jumping stages using Last_Activity date and first data this opportunity was introduced in the pipeline, first date it was introduced in the current confidence stage | 
|5 |Opportunities_YYYY_MM|Deal_Currency|the currency names are inconsistent and have null values |euro currency has values: "EUR","eur"|use uppercase function to group the currencies together, handle null currency columns in some way|
|6|Opportunities_YYYY_MM|Deal_Value|Values have null values, some have commas, decimals, space trails, alphabets|"9,200.00","1 506 600", " ", "44,500.00", "PLN 331,000"|use regex cleaning to correct number format and change data type to numerical to perform mathematical additions, etc functions for analysis|
|7|Opportunities_YYYY_MM|Deal_Value|Each Deal has a set of currency so total pipeline value in single currency is difficult to measure on dashboard | | we use a standardized currency and convert it to a single currency (Euro) to understand each deal's value in the same currency|
|8|Opportunities_YYYY_MM|Owner_Email|the table has email id of the lead owner and not employee ID to map with Sales team roaster file to extract lead owner related data via join||We have to be careful, perhaps standardize the Owner_Email column to avoid not matching with Sales Leads roaster file so we can extract all related data from dimensional table or we can extract first& last name to match to get employee id into Opportunities_YYYY_MM table and then join Sales lead roaster dimension table using employee IDs|
|9|Accounts_export|Industry|incorrect segmentation for proper grouping|Mixed values like : "Manufacturing", "Manufacturing and Automative", "Automative"|create a new industry grouping logic to correctly group |
|10|Opportunities_YYYY_MM (all 24 files)|All columns|Schema drift: from `opps_2025_07` the column names and order change (v1 → v2), v2 has no Account Name and adds `Forecast_Category`|v1 `Stage`, `Amount`, `Opportunity Owner` → v2 `Sales_Stage`, `Deal_Value`, `Owner_Email`|Batch macro reads one file at a time and renames columns with `crm_field_mapping_v1_v2.csv` (Dynamic Rename), then stacks them (Phase 2)|
|11|Opportunities_YYYY_MM|Opportunity ID / Opp_ID|Two ID formats for the same kind of key|"OPP-1595" (v1) vs "OPP-003750" (v2)|Keep only the digits and pad to 6: `"OPP-" + PadLeft(REGEX_Replace([id], "[^0-9]", ""), 6, "0")` (Phase 4)|
|12|Opportunities_YYYY_MM|All date fields|Three date formats, sometimes mixed in the same row|"2026-05-18", "27/03/2026", "30.04.2026"|Multi-Field Formula: REGEX_Match each pattern, then DateTimeParse with the matching format. Assume slash dates are European DD/MM/YYYY (Phase 4)|
|13|accounts_export.xlsx|Whole sheet|3 junk rows above the header ("Report: All Accounts - Europe", "Exported by…", blank) and 2 footer rows ("Total records: 765", "Confidential…")|Header is on line 4|Input tool → Start Data Import on Line 4; Filter `StartsWith([Account ID], "ACC-")` to drop the footer (Phase 1/3)|
|14|Opportunities_YYYY_MM|Department / Business_Unit|Many spellings of the same department; v2 uses codes|"Data&AI", "Data and AI", "DATA & AI", "DATA_AI", "CLOUD", "ERP & Apps", "Cyber"|Add every spelling to `value_aliases.csv` (domain = department) → Find Replace (Phase 4)|
|15|Opportunities_YYYY_MM (v1)|Opportunity Owner|v1 has no email, only the owner's name written in different ways|"Hughes, Oliver", "S. Andersson"|Join to roster in passes: reorder "Last, First" → match on name; unmatched → match on initial + surname; rest → aliases. v2 joins directly on lowercase email (Phase 4)|

## Profiling results (Phase 1)
Counted across **all 24 opportunity files** (5,012 rows), the stage history log, the accounts file (765 records) and the sales roster. Originally profiled with an Alteryx workflow (`archive/alteryx_v1/alteryx/00_profiling.yxmd`); in dbt the same counts are enforced by `not_null` tests on every alias-mapped column.

| Domain | Distinct raw spellings | Standard values | Where |
|---|---|---|---|
| Stage | 29 (26 ignoring upper/lower case) | 6 | opportunities + stage history |
| Department | 19 (16) | 4 | opportunities + roster |
| Country | 59 (57) | 18 | accounts |
| Industry | 32 (29) | 8 | accounts |
| Company size | 14 | 5 | accounts (`Employees` column) |
| Loss reason | 21 (18) | 6 | opportunities |
| Lead source | 18 | 6 | opportunities |
| Owner (v1 names) | 108 (81) | 29 AEs | opportunities v1 – most solved by the join passes, only initials + one misspelling need the alias table |

**Result:** `data/reference/value_aliases.csv` now holds 210 rows. Checked in Python: every raw spelling found in the data (ignoring case) has a row, so Find Replace will leave nothing unmapped.
