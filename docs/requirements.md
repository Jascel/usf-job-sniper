# PRD: USF Job Sniper (v1.0)

**Project Goal:** A headless automation that monitors the USF Oracle Careers portal, filters for Tampa-based student roles, calculates a "Match Score" for IT/Tech interests, and persists data to Supabase with instant Discord notifications.

---

### 1. Data Source & Extraction
* **Target URL:** `https://jobs.usf.edu/hcmUI/CandidateExperience/en/sites/USF/jobs`
* **Method:** Python `requests` targeting the internal JSON/REST endpoint to minimize resource impact on macOS.
* **Frequency:** Runs every **60 minutes**.

---

### 2. Filtering & Logic
* **Hard Skips (Immediate Drop):**
    * **Location:** Any listing containing "St. Petersburg" or "Sarasota".
    * **Eligibility:** Any listing containing "Federal Work Study", "FWS", or "Work Study".
    * **Education Level:** Any listing explicitly containing "Bachelor's", "Master's", "PhD", or "Doctorate" in the degree/requirements field.
* **Categorization:**
    * **Tier 1 (High Priority):** Titles containing *Student, Assistant, IT, Security, Programming, Audio, Help Desk, Analytics, Bulls Media, or OPS*. 
    * **Tier 2 (General):** Any other listing that passes the Hard Skip filters.
* **IT Match Score:** A 0-100 integer calculated based on the presence of technical keywords (e.g., Python, SQL, Cloud, Hardware, Support) within the job description.

---

### 3. Database Schema (Supabase)
**Table Name:** `usf_jobs`
* `id`: BIGINT PRIMARY KEY (Uses the original Oracle Job ID).
* `title`: TEXT.
* `salary`: TEXT (Extract if available, else "N/A").
* `hours`: TEXT (Extract if available, else "N/A").
* `match_score`: INT.
* `is_tech_tier`: BOOLEAN (True if Tier 1).
* `created_at`: TIMESTAMP WITH TIME ZONE DEFAULT NOW().

---

### 4. Notification Schema (Discord Webhook)
* **Tier 1 Format:** 🚨 **URGENT: RELEVANT ROLE FOUND**
* **Tier 2 Format:** 🔵 **NEW GENERAL LISTING**
* **Payload Contents:** * **Job Title**
    * **Salary & Hours**
    * **Summary:** 2-sentence description generated from the job posting.
    * **IT Match Score** (e.g., 85/100)
    * **Apply Link:** Direct URL to the specific USF job ID.
---

### 5. Technical Implementation Plan
1.  **Phase 1: Cloud Setup**
    * Create Supabase project and the `usf_jobs` table via SQL Editor.
    * Generate Discord Webhook URL in Server Settings.
2.  **Phase 2: The Scraper**
    * Use Python to intercept the JSON payload from the Oracle HCM site.
    * Implement logic-based filters for "Tampa" and "Degree Requirements."
3.  **Phase 3: Integration**
    * Implement `supabase-py` to check for existing IDs before firing webhooks.
    * Calculate the IT Match Score using a weighted keyword list.
4.  **Phase 4: Deployment**
    * Store all credentials in a `.env` file.
    * Configure a `launchd` plist on macOS to ensure the script executes every hour in the background.

---

### 6. Security & Constraints
* **No Hardcoding:** All API keys and Webhook URLs must reside in `.env`.
* **Environment:** Must run as a low-impact background process on macOS.