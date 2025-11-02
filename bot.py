#!/usr/bin/env python3
"""
AIS Job Alert Webhook Bot
Monitors GitHub repositories for new job postings and sends Discord notifications.
"""

import json
import re
import hashlib
import logging
import time
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import requests
from urllib.parse import urlparse, parse_qs, urlunparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# File paths
CONFIG_FILE = 'config.json'
CACHE_FILE = 'job_cache.json'


def load_config() -> dict:
    """Load configuration from config.json"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"{CONFIG_FILE} not found!")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {CONFIG_FILE}: {e}")
        raise


def load_cache() -> dict:
    """Load job cache from job_cache.json"""
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"{CACHE_FILE} not found, creating new cache")
        return {"posted_jobs": []}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {CACHE_FILE}: {e}")
        return {"posted_jobs": []}


def save_cache(cache: dict) -> None:
    """Save job cache to job_cache.json"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
        logger.info(f"Cache saved with {len(cache['posted_jobs'])} jobs")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")
        raise


def clean_url(url: str) -> str:
    """Remove tracking parameters from URL for consistent hashing"""
    try:
        parsed = urlparse(url)
        # Remove common tracking parameters
        query_params = parse_qs(parsed.query)
        tracking_params = ['utm_source', 'utm_medium', 'utm_campaign', 'ref', 'source']
        cleaned_params = {k: v for k, v in query_params.items() if k not in tracking_params}

        # Reconstruct query string
        query_string = '&'.join([f"{k}={v[0]}" for k, v in cleaned_params.items()])
        cleaned = parsed._replace(query=query_string)
        return urlunparse(cleaned)
    except Exception as e:
        logger.warning(f"Failed to clean URL {url}: {e}")
        return url


def generate_job_id(company: str, role: str, location: str, url: str) -> str:
    """Generate unique job ID using hash of key fields"""
    # Clean and normalize inputs
    clean_company = company.strip().lower()
    clean_role = role.strip().lower()
    clean_location = location.split('/')[0].strip().lower()  # Take first location if multiple
    clean_application_url = clean_url(url)

    # Create composite string and hash it
    composite = f"{clean_company}|{clean_role}|{clean_location}|{clean_application_url}"
    return hashlib.sha256(composite.encode('utf-8')).hexdigest()[:16]


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text"""
    # Remove bold/italic
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # Remove links but keep text
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    return text.strip()


def extract_url_from_markdown_image(text: str) -> Optional[str]:
    """Extract URL from markdown image syntax, HTML anchor tag, or plain markdown link"""
    # Try HTML anchor tag first: <a href="url">
    html_match = re.search(r'<a\s+href=["\']([^"\']+)["\']', text, re.IGNORECASE)
    if html_match:
        return html_match.group(1)

    # Try markdown image syntax: ![text](url)
    markdown_image_match = re.search(r'!\[.*?\]\((https?://[^\)]+)\)', text)
    if markdown_image_match:
        return markdown_image_match.group(1)

    # Try plain markdown link: [text](url)
    markdown_link_match = re.search(r'\[.*?\]\((https?://[^\)]+)\)', text)
    if markdown_link_match:
        return markdown_link_match.group(1)

    # Try to find any bare URL in the text
    url_match = re.search(r'(https?://[^\s\)]+)', text)
    if url_match:
        return url_match.group(1)

    return None


def clean_text(text: str) -> str:
    """Clean text by removing HTML tags, extra whitespace, and special symbols"""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove special symbols like ↳
    text = text.replace('↳', '').strip()
    # Remove extra whitespace
    text = ' '.join(text.split())
    # Strip markdown
    text = strip_markdown(text)
    return text


def detect_job_status(role: str) -> dict:
    """Detect job status from emoji indicators in role"""
    status = {
        'is_closed': '🔒' in role,
        'no_sponsorship': '🛂' in role,
        'requires_citizenship': '🇺🇸' in role
    }
    return status


def is_posted_today(date_posted: str) -> bool:
    """Check if a job was posted today based on the date string (e.g., 'Oct 30', 'Oct 31')"""
    if not date_posted:
        return False

    try:
        # Parse the date string (format: "Oct 30", "Nov 01", etc.)
        # Get current date
        today = datetime.now()
        current_year = today.year

        # Parse the posted date
        posted_date = datetime.strptime(f"{date_posted} {current_year}", "%b %d %Y")

        # If the posted date is in the future (e.g., we're in Dec and job says "Jan 01"),
        # it likely refers to next year, so skip it
        if posted_date > today:
            return False

        # Check if it's today
        return posted_date.date() == today.date()

    except Exception as e:
        logger.warning(f"Failed to parse date '{date_posted}': {e}")
        return False


def is_posted_within_days(date_posted: str, days_back: int = 7) -> bool:
    """Check if a job was posted within the last N days based on the date string"""
    if not date_posted:
        return False

    try:
        # Get current date
        today = datetime.now()
        current_year = today.year

        # Parse the posted date (format: "Oct 30", "Nov 01", etc.)
        posted_date = datetime.strptime(f"{date_posted} {current_year}", "%b %d %Y")

        # If the posted date is in the future (e.g., we're in Dec and job says "Jan 01"),
        # it likely refers to next year, so skip it
        if posted_date > today:
            return False

        # Calculate days difference
        days_diff = (today - posted_date).days

        # Check if within the specified number of days
        return 0 <= days_diff <= days_back

    except Exception as e:
        logger.warning(f"Failed to parse date '{date_posted}': {e}")
        return False


def is_posted_within_hours(date_posted: str, hours_back: int = 3) -> bool:
    """Check if a job was posted within the last N hours based on the date string

    Args:
        date_posted: Date string in format "Oct 30", "Nov 01", etc.
        hours_back: Number of hours to look back from now (default: 3)

    Returns:
        True if job was posted within the specified hours, False otherwise
    """
    if not date_posted:
        return False

    try:
        # Get current datetime
        now = datetime.now()
        current_year = now.year

        # Parse the posted date (format: "Oct 30", "Nov 01", etc.)
        # This gives us the date at midnight
        posted_date = datetime.strptime(f"{date_posted} {current_year}", "%b %d %Y")

        # If the posted date is in the future, it likely refers to next year
        if posted_date > now:
            return False

        # Calculate time difference in hours
        time_diff = now - posted_date
        hours_diff = time_diff.total_seconds() / 3600

        # Check if within the specified number of hours
        # Since we only have the date (not time), we check if it's within hours_back + 24 hours
        # This ensures we catch jobs from "today" even if posted at midnight
        return 0 <= hours_diff <= (hours_back + 24)

    except Exception as e:
        logger.warning(f"Failed to parse date '{date_posted}': {e}")
        return False


def parse_markdown_table(markdown_content: str, only_today: bool = False, hours_back: int = 0) -> List[Dict]:
    """Parse markdown table to extract job listings

    Args:
        markdown_content: The markdown content to parse
        only_today: If True, only include jobs posted today
        hours_back: If > 0, only include jobs posted within last N hours (overrides only_today)
    """
    jobs = []

    # Find the table section
    # Look for the header row
    header_pattern = r'\|\s*Company\s*\|\s*Role\s*\|\s*Location\s*\|\s*Application/?Link\s*\|\s*Date Posted\s*\|'
    header_match = re.search(header_pattern, markdown_content, re.IGNORECASE)

    if not header_match:
        logger.warning("Could not find job table header in markdown")
        return jobs

    # Start parsing from the line after the separator
    start_pos = header_match.end()
    lines = markdown_content[start_pos:].split('\n')

    # Skip the separator line (------|------|)
    if lines and re.match(r'^\|[\s\-\|]+\|$', lines[0]):
        lines = lines[1:]


    for line in lines:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Stop at non-table content
        if not line.startswith('|'):
            break

        # Skip separator lines
        if re.match(r'^\|[\s\-\|]+\|$', line):
            continue

        # Split by pipe and clean
        parts = [p.strip() for p in line.split('|')]

        # Valid row should have 7 parts (empty, company, role, location, application, date, empty)
        if len(parts) < 6:
            continue

        try:
            company = clean_text(parts[1])
            role = clean_text(parts[2])
            location = clean_text(parts[3])
            application_cell = parts[4].strip()
            date_posted = parts[5].strip() if len(parts) > 5 else ''

            # Skip empty rows or subsidiary markers without actual jobs
            if not company or not role or company == '↳':
                continue

            # Extract application URL
            application_url = extract_url_from_markdown_image(application_cell)
            if not application_url:
                logger.warning(f"No application URL found for {company} - {role}")
                continue

            # Detect job status
            status = detect_job_status(parts[2])  # Use raw role text with emojis

            # Skip closed positions
            if status['is_closed']:
                logger.debug(f"Skipping closed position: {company} - {role}")
                continue

            # Date filtering logic
            if hours_back > 0:
                # Filter by hours (e.g., last 3 hours)
                if not is_posted_within_hours(date_posted, hours_back):
                    logger.debug(f"Skipping job outside time window: {company} - {role} (posted: {date_posted})")
                    continue
            elif only_today:
                # Filter by today only
                if not is_posted_today(date_posted):
                    logger.debug(f"Skipping job not posted today: {company} - {role} (posted: {date_posted})")
                    continue
            # Otherwise, no date filtering - rely on cache for deduplication

            # Clean emojis from role name for display
            role = re.sub(r'[🛂🇺🇸🔒]', '', role).strip()

            job = {
                'company': company,
                'role': role,
                'location': location,
                'application_url': application_url,
                'date_posted': date_posted,
                'no_sponsorship': status['no_sponsorship'],
                'requires_citizenship': status['requires_citizenship']
            }

            jobs.append(job)

        except Exception as e:
            logger.error(f"Error parsing row: {line[:100]}... Error: {e}")
            continue

    logger.info(f"Parsed {len(jobs)} jobs from markdown table")
    return jobs


def fetch_readme(repo_url: str) -> Optional[str]:
    """Fetch README.md content from GitHub repository"""
    try:
        # Convert GitHub repo URL to raw README URL
        # e.g., https://github.com/vanshb03/Summer2026-Internships
        # to https://raw.githubusercontent.com/vanshb03/Summer2026-Internships/main/README.md

        if 'github.com' in repo_url:
            parts = repo_url.rstrip('/').split('github.com/')[-1]
            raw_url = f"https://raw.githubusercontent.com/{parts}/main/README.md"
        else:
            logger.error(f"Invalid GitHub URL: {repo_url}")
            return None

        logger.info(f"Fetching README from {raw_url}")
        response = requests.get(raw_url, timeout=10)
        response.raise_for_status()

        logger.info(f"Successfully fetched README ({len(response.text)} bytes)")
        return response.text

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch README from {repo_url}: {e}")
        return None


def send_discord_notification(webhook_url: str, job: Dict, repo_config: Dict) -> bool:
    """Send job posting notification to Discord via webhook"""
    try:
        # Prepare embed
        embed = {
            "title": f"{repo_config['badge']} New {repo_config['type']} Posted",
            "color": int(repo_config['color'].replace('#', ''), 16),
            "fields": [
                {"name": "Company", "value": job['company'], "inline": True},
                {"name": "Role", "value": job['role'], "inline": True},
                {"name": "Location", "value": job['location'], "inline": True}
            ],
            "url": job['application_url'],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"Source: {repo_config['name']}"}
        }

        # Add additional info if job has restrictions
        restrictions = []
        if job.get('no_sponsorship'):
            restrictions.append("⚠️ No visa sponsorship")
        if job.get('requires_citizenship'):
            restrictions.append("⚠️ Requires U.S. citizenship")

        if restrictions:
            embed['fields'].append({
                "name": "Requirements",
                "value": "\n".join(restrictions),
                "inline": False
            })

        payload = {"embeds": [embed]}

        logger.info(f"Sending notification for {job['company']} - {job['role']}")
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()

        logger.info("Discord notification sent successfully")
        return True

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Discord notification: {e}")
        return False


def process_repository(repo_config: Dict, webhook_url: str, cache: dict, only_today: bool = False, hours_back: int = 0) -> List[Dict]:
    """Process a single repository and return new jobs found

    Args:
        repo_config: Repository configuration
        webhook_url: Discord webhook URL
        cache: Job cache for deduplication
        only_today: If True, only include jobs posted today
        hours_back: If > 0, only include jobs posted within last N hours
    """
    logger.info(f"Processing repository: {repo_config['name']}")

    # Fetch README
    readme_content = fetch_readme(repo_config['url'])
    if not readme_content:
        logger.error(f"Failed to fetch README for {repo_config['name']}")
        return []

    # Parse jobs
    jobs = parse_markdown_table(readme_content, only_today=only_today, hours_back=hours_back)
    logger.info(f"Parsed {len(jobs)} jobs from {repo_config['name']}")

    if not jobs:
        logger.warning(f"No jobs found in {repo_config['name']}")
        return []

    # Check for new jobs
    new_jobs = []
    cached_job_ids = {job['id'] for job in cache['posted_jobs']}

    for job in jobs:
        job_id = generate_job_id(
            job['company'],
            job['role'],
            job['location'],
            job['application_url']
        )

        if job_id not in cached_job_ids:
            logger.info(f"New job found: {job['company']} - {job['role']}")

            # Send Discord notification with rate limiting
            if send_discord_notification(webhook_url, job, repo_config):
                # Add to new jobs list
                job_record = {
                    'id': job_id,
                    'company': job['company'],
                    'role': job['role'],
                    'location': job['location'],
                    'application_url': job['application_url'],
                    'date_posted': job['date_posted'],
                    'source_repo': repo_config['name'],
                    'timestamp': datetime.utcnow().isoformat()
                }
                new_jobs.append(job_record)

                # Rate limiting: Wait 0.5 seconds between notifications to respect Discord limits
                # Discord allows ~5 requests per second, so 0.5s delay = 2 req/sec (safe buffer)
                time.sleep(0.5)
        else:
            logger.debug(f"Job already posted: {job['company']} - {job['role']}")

    duplicates_count = len(jobs) - len(new_jobs)
    logger.info(f"Found {len(new_jobs)} new jobs in {repo_config['name']} ({duplicates_count} duplicates filtered)")
    return new_jobs


def main():
    """Main execution function"""
    logger.info("=" * 60)
    logger.info("Starting AIS Job Alert Webhook Bot")
    logger.info("=" * 60)

    try:
        # Load configuration
        config = load_config()
        webhook_url = config['discord_webhook_url']
        repositories = config['repositories']
        only_today_jobs = config.get('settings', {}).get('only_today_jobs', True)
        hours_back = config.get('settings', {}).get('hours_back', 0)

        # Load cache
        cache = load_cache()
        initial_cache_size = len(cache['posted_jobs'])
        logger.info(f"Loaded cache with {initial_cache_size} existing jobs")

        # Log filtering mode
        if hours_back > 0:
            logger.info(f"Mode: Posting jobs from last {hours_back} hours (deduplication via cache)")
        elif only_today_jobs:
            logger.info("Mode: Only posting jobs from today")
        else:
            logger.info("Mode: Posting all new jobs (deduplication via cache)")

        # Process each repository
        all_new_jobs = []
        for repo_config in repositories:
            new_jobs = process_repository(repo_config, webhook_url, cache, only_today=only_today_jobs, hours_back=hours_back)
            all_new_jobs.extend(new_jobs)

        # Update cache with new jobs
        if all_new_jobs:
            cache['posted_jobs'].extend(all_new_jobs)
            save_cache(cache)
            logger.info(f"Added {len(all_new_jobs)} new jobs to cache")
        else:
            logger.info("No new jobs found")

        # Summary
        logger.info("=" * 60)
        logger.info(f"Bot execution completed successfully")
        logger.info(f"Cache size: {initial_cache_size} -> {len(cache['posted_jobs'])}")
        logger.info(f"New jobs posted: {len(all_new_jobs)}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Bot execution failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
