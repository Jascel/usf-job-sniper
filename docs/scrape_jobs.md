# SOP: USF Job Sniper Scraper (`scrape_jobs.py`)

## Goal

Fetch, filter, score, and persist jobs from the USF Oracle Careers portal, and send Discord notifications for new jobs.

## Inputs

- `SUPABASE_URL`: (Environment Variable)
- `SUPABASE_KEY`: (Environment Variable)
- `DISCORD_WEBHOOK_URL`: (Environment Variable)

## Data Source

- URL: `https://jobs.usf.edu/hcmUI/CandidateExperience/en/sites/USF/jobs`
- Since this is an Oracle HCM site, it usually relies on a backend REST API for the real data, accessible at `https://jobs.usf.edu/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.reqFlexfieldsWithTrans,requisitionList.flexFieldsFacet.values&finder=findReqs;siteNumber=USF,facetsList=LOCATIONS%3BWORK_LOCATIONS%3BTITLES%3BCATEGORIES%3BORGANIZATIONS%3BPOSTING_DATES%3BFLEX_FIELDS`
- It's recommended to do a POST request to `https://jobs.usf.edu/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.reqFlexfieldsWithTrans,requisitionList.flexFieldsFacet.values&finder=findReqs;siteNumber=USF,facetsList=LOCATIONS%3BWORK_LOCATIONS%3BTITLES%3BCATEGORIES%3BORGANIZATIONS%3BPOSTING_DATES%3BFLEX_FIELDS`
  - Actually, a simple GET or POST to the endpoint should be investigated to find the exact JSON payload.

## Filtering Rules

### Hard Skips (Ignore these immediately)

- **Location:** If location contains "St. Petersburg" or "Sarasota". We only want Tampa-based or purely online/remote USF jobs.
- **Eligibility:** If the title or description contains "Federal Work Study", "FWS", or "Work Study". (Case-insensitive check).
- **Seniority:** If the title contains "Sr", "Sr.", or "Senior" as a standalone word.
- **Education Level (pre-fetch):** If the list API qualifications text contains "Bachelor's", "Master's", "PhD", or "Doctorate". (Case-insensitive).
- **Education Level (post-fetch):** If the detail API `StudyLevel` field contains "Bachelor", "Master", "PhD", or "Doctorate". This is the authoritative check.

### Categorization

- **Tier 1 (High Priority):** Titles matching (word-boundary for short terms): `IT`, `OPS`. Substring for: `Student`, `Assistant`, `Security`, `Programming`, `Audio`, `Help Desk`, `Helpdesk`, `Analytics`, `Bulls Media`, `Engineer`, `Engineering`, `Intern`, `Tech`. (Case-insensitive).
- **Tier 2 (General):** Anything else that passes the Hard Skips.

### Match Score (0-100)

Calculated based on the presence of technical keywords in the Title and Description:

- Keywords: `Python`, `SQL`, `Cloud`, `Hardware`, `Support`, `React`, `Node`, `Java`, `Data`, `Network`, `Security`, `API`, `Help Desk`, `Helpdesk`
- Give +15 points per match, up to a max of 100.

## Data Extraction (Detail API)

- **Salary:** Read from `requisitionFlexFields` → entry with `Prompt: "Hiring Salary"` → `Value`. Prefix with `$` if value starts with a digit. Falls back to "N/A" if missing.
- **Hours:** Read from `WorkHours` field first, then regex on `ExternalDescriptionStr` for patterns like "20 hours per week". Falls back to full-time/part-time detection, then "N/A".
- **Degree Level:** Read from `StudyLevel` field (e.g. "Bachelor's Degree", "High School Graduate").

## Outputs

- Supabase table `usf_jobs` entry for each processed job (id, title, salary, hours, match_score, is_tech_tier).
- Discord webhook notification for **new** jobs.
  - Tier 1: `🚨 **URGENT: RELEVANT ROLE FOUND**`
  - Tier 2: `🔵 **NEW GENERAL LISTING**`

## Edge Cases

- Missing Salary or Hours fields: default to "N/A"
- Rate limits on the Oracle API: Implement minor delays if necessary. But we run every 60 min, so 1 request is fine.
