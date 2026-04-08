import os
import sys
import re
import json
import time
import logging
import requests
from dotenv import load_dotenv
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
USF_JOBS_API_URL = "https://jobs.usf.edu/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder=findReqs;siteNumber=USF,facetsList=LOCATIONS%3BWORK_LOCATIONS%3BTITLES%3BCATEGORIES%3BORGANIZATIONS%3BPOSTING_DATES,limit=50"

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Tech Keywords for Match Score
HIGH_VALUE_KEYWORDS = ["it", "security", "programming", "analytics", "engineer", "engineering"]
STANDARD_KEYWORDS = [
    "python", "sql", "cloud", "hardware", "support", "react", "node", 
    "java", "data", "network", "api", "help desk", "helpdesk"
]

def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials not found. Database operations will be skipped.")
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None

def fetch_jobs():
    """Fetch job listings from the USF Oracle Careers API."""
    logger.info("Fetching jobs from USF API...")
    try:
        response = requests.get(USF_JOBS_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # The jobs are in items[0]['requisitionList']
        items = data.get("items", [])
        if items and "requisitionList" in items[0]:
            jobs = items[0]["requisitionList"]
        else:
            jobs = []
            
        logger.info(f"Fetched {len(jobs)} job listings.")
        return jobs
    except Exception as e:
        logger.error(f"Failed to fetch jobs: {e}")
        return []

def fetch_job_detail(job_id):
    """Fetch full job description from the Oracle Cloud detail API.
    
    Returns: (salary, hours, description, study_level)
    - salary: from requisitionFlexFields 'Hiring Salary', falls back to regex
    - hours: from WorkHours field or regex on description
    - description: cleaned text from ExternalDescriptionStr
    - study_level: from StudyLevel field (e.g. "Bachelor's Degree", "High School Graduate")
    """
    detail_url = f'https://fa-ewkd-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id="{job_id}",siteNumber=CX_1'
    salary = "N/A"
    hours = "N/A"
    description = ""
    study_level = ""
    try:
        resp = requests.get(detail_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Detail API returned {resp.status_code} for job {job_id}")
            return salary, hours, description, study_level
        
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return salary, hours, description, study_level
        
        item = items[0]
        
        # --- Study Level (for degree filtering) ---
        study_level = (item.get("StudyLevel") or "").strip()
        
        # --- Salary: read from structured requisitionFlexFields first ---
        flex_fields = item.get("requisitionFlexFields", []) or []
        for field in flex_fields:
            if field.get("Prompt") == "Hiring Salary":
                raw_salary = (field.get("Value") or "").strip()
                if raw_salary:
                    # Add $ prefix if it's just a number (e.g. "15.00")
                    if raw_salary and raw_salary[0].isdigit():
                        salary = f"${raw_salary}"
                    else:
                        salary = raw_salary
                break
        
        # --- Description: clean HTML ---
        raw_desc = str(item.get("ExternalDescriptionStr") or "") + " " + \
                   str(item.get("ExternalResponsibilitiesStr") or "") + " " + \
                   str(item.get("ExternalQualificationsStr") or "")
        description = re.sub(r'<[^>]+>', ' ', raw_desc)
        description = re.sub(r'&nbsp;', ' ', description)
        description = re.sub(r'\s+', ' ', description).strip()
        
        # --- Salary fallback: regex on description if structured field was empty ---
        if salary == "N/A" and description:
            salary_match = re.search(
                r'\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?(?:\s*-\s*\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?)?(?:\s*/\s*(?:hr|hour|week|wk|month|mo|year|yr))?',
                description, re.IGNORECASE
            )
            if salary_match:
                salary = salary_match.group(0).strip()
        
        # --- Hours: check structured field first, then regex ---
        work_hours = item.get("WorkHours")
        if work_hours:
            hours = str(work_hours)
        else:
            hours_match = re.search(
                r'(\d+)\s*[-–]?\s*(\d+)?\s*(?:hours?|hrs?)\s*(?:per|/)\s*(?:week|wk)',
                description, re.IGNORECASE
            )
            if hours_match:
                low_hrs = hours_match.group(1)
                high_hrs = hours_match.group(2)
                if high_hrs:
                    hours = f"{low_hrs}-{high_hrs} hrs/week"
                else:
                    hours = f"{low_hrs} hrs/week"
            else:
                ft_match = re.search(r'(full[\s-]?time|part[\s-]?time)', description, re.IGNORECASE)
                if ft_match:
                    hours = ft_match.group(1).strip().title()
    except Exception as e:
        logger.warning(f"Could not fetch detail for job {job_id}: {e}")
    
    return salary, hours, description, study_level

def apply_hard_skips(job) -> bool:
    """Returns True if the job should be skipped.
    
    This runs BEFORE the detail API call to cheaply filter out obvious mismatches.
    Degree-level filtering from the StudyLevel field happens later in process_jobs()
    after the detail fetch.
    """
    title = (job.get("Title", "") or "").lower()
    description = (job.get("ShortDescriptionStr", "") or "").lower()
    location = (job.get("PrimaryLocation", "") or "").lower()
    
    # Check Location
    if any(x in location for x in ["st. petersburg", "saint petersburg", "st. pete", "saint pete", "sarasota"]):
        return True
        
    # Check Eligibility
    if "federal work study" in title or "federal work study" in description or "fws" in title or "work study" in title or "work study" in description:
        return True
    
    # Check Seniority (title only)
    title_words = title.split()
    if "sr" in title_words or "sr." in title_words or "senior" in title_words:
        return True
        
    # Check Education Qualifications (from list API text — rough pre-filter)
    qualifications = (job.get("ExternalQualificationsStr", "") or "").lower()
    all_text = title + " " + description + " " + qualifications
    
    for degree in ["bachelor's", "master's", "phd", "doctorate", "bachelors", "masters"]:
        if degree in all_text:
            return True
            
    return False

def determine_tier(title: str) -> int:
    """Determine if a job is Tier 1 (High Priority 1) or Tier 2 (General 2)."""
    title_lower = title.lower()
    
    # Keywords for Tier 1: Highly specific IT/Security/High-Value Tech roles
    tier1_exclusive = ["security", "programming", "analytics", "engineer", "engineering"]
    # Keywords that need word-boundary matching to avoid false positives
    exact_keywords = ["it"]
    # Keywords for Tier 2: General student assistant/media/intern roles
    # These will NOT trigger Tier 1 unless they also have keywords above
    
    for kw in exact_keywords:
        if re.search(rf'\b{kw}\b', title_lower):
            return 1
    for kw in tier1_exclusive:
        if kw in title_lower:
            return 1
    return 2

def calculate_match_score(title: str, description: str) -> float:
    """Calculate the IT Match Score (0-5.0)."""
    score = 0.0
    text_to_check = f"{title.lower()} {description.lower()}"
    
    # Check High Value Keywords (3.5 pts each)
    for kw in HIGH_VALUE_KEYWORDS:
        if re.search(rf'\b{kw}\b', text_to_check):
            score += 3.5
            
    # Check Standard Keywords (1.0 pt each)
    for kw in STANDARD_KEYWORDS:
        if kw in text_to_check:
            score += 1.0
            
    return min(score, 5.0)

def send_discord_notification(job_data):
    """Send a notification to the Discord Webhook."""
    if not DISCORD_WEBHOOK_URL:
        logger.warning(f"No Discord Webhook configured. Skipping notification for Job ID: {job_data['id']}")
        return

    tier = 1 if job_data['is_tech_tier'] else 2
    
    if tier == 1:
        prefix = "@everyone 🚨 **URGENT: RELEVANT ROLE FOUND**"
        color = 15158332 # Red
    else:
        prefix = "🔵 **NEW GENERAL LISTING**"
        color = 3447003 # Blue
        
    job_id = job_data['id']
    apply_link = f"https://jobs.usf.edu/hcmUI/CandidateExperience/en/sites/USF/job/{job_id}"
    
    score = job_data['match_score']
    formatted_score = int(score) if isinstance(score, (int, float)) and score == int(score) else score
    
    embed = {
        "title": job_data['title'],
        "url": apply_link,
        "color": color,
        "fields": [
            {"name": "💰 Salary", "value": job_data['salary'], "inline": True},
            {"name": "🕐 Hours", "value": job_data['hours'], "inline": True},
        ],
        "footer": {"text": f"Job ID: {job_id}  •  IT Match: {formatted_score}/5"}
    }

    payload = {
        "content": prefix,
        "embeds": [embed]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        logger.info(f"Successfully sent Discord notification for Job {job_id}")
    except Exception as e:
        logger.error(f"Failed to send Discord notification for Job {job_id}: {e}")

def process_jobs():
    supabase = get_supabase_client()
    jobs = fetch_jobs()
    
    if not jobs:
        logger.info("No jobs to process.")
        return
        
    new_jobs_count = 0
    
    for job in jobs:
        job_id = job.get("Id") or job.get("RequisitionNumber")
        if not job_id:
            continue
            
        # Clean ID to just numbers if possible
        try:
            job_id = int(str(job_id).replace("REQ", "").strip())
        except ValueError:
            logger.warning(f"Could not parse typical integer ID from {job_id}")
            # we'll try to use it as an int later or skip it if it's really non-integer since schema expects BIGINT
            continue
            
        # Check if job already exists in db
        if supabase:
            try:
                result = supabase.table("usf_jobs").select("id").eq("id", job_id).execute()
                if result.data and len(result.data) > 0:
                    logger.debug(f"Job {job_id} already exists. Skipping.")
                    continue
            except Exception as e:
                logger.error(f"Error checking Supabase for job {job_id}: {e}")
                # decide to continue or not. we'll continue and try to process.
                continue
        
        if apply_hard_skips(job):
            logger.debug(f"Job {job_id} skipped due to hard filters.")
            continue
            
        title = job.get("Title", "Unknown Title")
        short_desc = job.get("ShortDescriptionStr", "") or ""
        
        # Fetch the full job detail from the Oracle Cloud API for salary, hours, description, and study level
        salary, hours, full_description, study_level = fetch_job_detail(job_id)
        time.sleep(0.3)  # Be polite to the server
        
        # Post-fetch degree filter using the structured StudyLevel field
        skip_degree = False
        if study_level:
            study_lower = study_level.lower()
            for degree in ["bachelor", "master", "phd", "doctorate"]:
                if degree in study_lower:
                    logger.info(f"Job {job_id} skipped: StudyLevel='{study_level}'")
                    skip_degree = True
                    break
        if skip_degree:
            continue
        
        # Use the full description for match scoring if available, otherwise fall back to short description
        desc_for_scoring = full_description if full_description else short_desc
        
        # --- Filter out Full-Time jobs based on hours, title, or high annual salaries ---
        is_full_time = False
        hours_lower = hours.lower()
        title_lower = title.lower()
        
        if "full time" in hours_lower or "full-time" in hours_lower or "40 hrs" in hours_lower or "40  hrs" in hours_lower or "40 hours" in hours_lower:
            is_full_time = True
            
        if "full time" in title_lower or "full-time" in title_lower:
            is_full_time = True
            
        if is_full_time:
            logger.info(f"Job {job_id} skipped: Explicitly marked as Full Time")
            continue
            
        # If salary > $20,000, it's an annual full-time salary
        try:
            salary_cleaned = salary.replace('$', '').replace(',', '')
            sal_matches = re.findall(r'\d+(?:\.\d+)?', salary_cleaned)
            if any(float(match) > 20000 for match in sal_matches):
                logger.info(f"Job {job_id} skipped: Salary implies full-time work ({salary})")
                continue
        except Exception:
            pass
        
        tier = determine_tier(title)
        match_score = int(calculate_match_score(title, desc_for_scoring))
        
        job_record = {
            "id": job_id,
            "title": title,
            "salary": salary,
            "hours": hours,
            "match_score": match_score,
            "is_tech_tier": tier == 1
        }
        
        # Insert into DB
        insert_success = True
        if supabase:
            try:
                supabase.table("usf_jobs").insert(job_record).execute()
                logger.info(f"Inserted Job {job_id} into database.")
            except Exception as e:
                logger.error(f"Failed to insert Job {job_id} into database: {e}")
                insert_success = False
                
        if insert_success:
            # Send Notification
            send_discord_notification(job_record)
            new_jobs_count += 1
        
    logger.info(f"Processed {len(jobs)} total jobs, found {new_jobs_count} new valid jobs.")

if __name__ == "__main__":
    process_jobs()
