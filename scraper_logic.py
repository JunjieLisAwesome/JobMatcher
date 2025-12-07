# scraper_logic.py (Save this as a new file)
# scraper_logic.py (Revised and Complete)

from bs4 import BeautifulSoup
from lxml import etree as et
import random
import csv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchWindowException, InvalidSessionIdException, TimeoutException
import time
import undetected_chromedriver as uc
import os

# --- 1. CONFIGURATION: UPDATE THIS PATH ---
CHROME_EXECUTABLE_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" 
# ------------------------------------------

# define base and pagination URLs
base_url = 'https://www.indeed.com'
paginaton_url = "https://www.indeed.com/jobs?q={}&l={}&start={}"

# Global driver variable is now initialized to None
driver = None 

# =====================================================================
# --- DRIVER SETUP & RESTART FUNCTIONS ---
# =====================================================================

def setup_driver():
    global driver
    if driver:
        # If the driver already exists (e.g., from a previous restart attempt), quit it first.
        try:
            driver.quit()
        except:
            pass
        
    print("Initializing Chrome Driver...")
    
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    # options.add_argument("--headless")
    
    options.binary_location = CHROME_EXECUTABLE_PATH

    try:
        driver = uc.Chrome(options=options) 
    except Exception as e:
        print(f"FATAL SETUP ERROR: Could not start the driver. Check your CHROME_EXECUTABLE_PATH. Error: {e}")
        return None

    driver.get("https://www.indeed.com/q-USA-jobs.html?vjk=823cd7ee3c203ac3")
    
    print("Waiting 15-25 seconds before starting search...")
    time.sleep(random.uniform(15, 25))
    
    print("Driver started successfully.")
    return driver

def restart_driver():
    global driver
    print("\nAttempting to restart driver session...")
    try:
        driver.quit()
    except Exception as e:
        print(f"Error during driver quit: {e}")
    
    driver = None
    time.sleep(random.uniform(5, 10))
    driver = setup_driver()
    return driver 

# --- GET DOM FUNCTION ---
def get_dom(url, is_job_page=False):
    global driver
    
    if driver is None:
        print("Driver is None. Cannot load page.")
        return None
        
    # Try to navigate and handle fatal session errors
    try:
        driver.get(url)
    except (NoSuchWindowException, InvalidSessionIdException) as e:
        print(f"FATAL ERROR: Driver session lost while loading {url}. Restarting driver...")
        driver = restart_driver()
        if driver is None:
            print("Restart failed. Giving up on this page.")
            return None
            
        # Retry the get operation after restart
        try:
            driver.get(url)
        except Exception as restart_e:
            print(f"Restart failed for {url}. Giving up on this page. Error: {restart_e}")
            return None
    except Exception as e:
        print(f"Error during driver.get: {e}")
        # Force a restart on a general error
        print("ACTION: Forcing driver restart due to general load error.") 
        driver = restart_driver()
        return None

    # Element waiting based on page type
    try:
        if is_job_page:
            WebDriverWait(driver, 15).until( 
                EC.presence_of_element_located((By.ID, 'jobDescriptionText'))
            )
        else:
            WebDriverWait(driver, 20).until( 
                EC.presence_of_element_located((By.XPATH, '//a[starts-with(@id, "sj_")]'))
            )
    except TimeoutException:
        print(f"FAILURE: Element not found on page {url} within timeout (20s).") 
        print("ACTION: Forcing driver restart due to suspected block.") 
        driver = restart_driver() 
        return None
    except Exception as e:
        print(f"FAILURE: Page {url} failed to load properly. Error: {e}")
        print("ACTION: Forcing driver restart due to general wait error.") 
        driver = restart_driver() 
        return None
    
    page_content = driver.page_source
    if not page_content:
        return None
    
    product_soup = BeautifulSoup(page_content, 'html.parser')
    dom = et.HTML(str(product_soup))
    return dom

# --- NEW FUNCTION FOR FULL DESCRIPTION (WITH ERROR HANDLING) ---
def get_full_job_desc(full_url):
    print(f"   -> Navigating to job page: {full_url}")
    
    job_dom = get_dom(full_url, is_job_page=True)
    
    if job_dom is None:
        return "Full Description Failed to Load (Blocked)"
        
    try:
        # Extract all inner HTML/text content from the stable ID
        description_elements = job_dom.xpath('//div[@id="jobDescriptionText"]//text()')
        
        # Join and clean the text
        description = " ".join([d.strip() for d in description_elements if d.strip()])
        
        # Remove extra whitespace introduced by joining
        description = " ".join(description.split())
        return description
        
    except Exception as e:
        print(f"   -> Error extracting full description: {e}")
        return "Full Description Error"


# --- DATA EXTRACTION FUNCTIONS ---
def get_job_link(job):
    try:
        job_link = job.xpath('.//a[starts-with(@id, "sj_")]/@href')[0]
    except:
        job_link = 'Not available'
    return job_link

def get_job_title(job):
    try:
        job_title = job.xpath('.//a[starts-with(@id, "sj_")]/span/@title')[0]
    except:
        job_title = 'Not available'
    return job_title

def get_company_name(job):
    try:
        company_name = job.xpath('.//span[contains(@class, "companyName")]/text()')[0]
    except:
        company_name = 'Not available'
    return company_name

def get_company_location(job):
    try:
        # XPath to find the location span
        location_elements = job.xpath('.//div[contains(@class, "companyLocation")]//text()')
        location = "".join([l.strip() for l in location_elements if l.strip()])
        return location if location else 'Not available'
    except:
        return 'Not available'

def get_salary(job):
    try:
        salary_elements = job.xpath('.//div[contains(@class, "salary-snippet")]//text()')
        if salary_elements:
            salary = "".join([s.strip() for s in salary_elements if s.strip()])
        else:
            salary = 'Not available'
    except:
        salary = 'Not available'
    return salary

def get_job_type(job):
    try:
        job_type = job.xpath('.//div[contains(@class, "metadata") and not(contains(@class, "salary"))]/div/text()')[0]
    except:
        job_type = 'Not available'
    return job_type

def get_rating(job):
    try:
        # XPath to find the rating span
        rating = job.xpath('.//span[contains(@class, "ratingNumber")]//text()')[0].strip()
        return rating
    except:
        return 'Not available'

# =====================================================================
# --- MAIN SCRAPER FUNCTION (Callable) ---
# =====================================================================
def scrape_indeed_jobs(job_keywords, location_keyword, max_jobs=10, max_pages=5, stop_checker=None):
    """
    Initializes the driver, scrapes Indeed for the given job titles and location, 
    and then quits the driver. Stops when max_jobs is reached.
    """
    global driver
    
    # --- DRIVER INITIALIZATION MOVED HERE ---
    driver = setup_driver()
    if driver is None:
        return [] # Return empty list if setup fails
    
    job_records = []
    
    print(f"Starting Scrape for Titles: {job_keywords} in Location: {location_keyword}")

    try:
        for job_keyword in job_keywords:
            if (stop_checker and stop_checker()) or len(job_records) >= max_jobs: # CHECK 1
                print("Stop signal received before loading new job type.")
                break
                
            # Use max_pages * 10 for the start index in the loop (start at page 0, then 10, 20, ...)
            # Max pages is a safety limit now, max_jobs is the primary limit
            for page_no in range(0, max_pages * 10, 10): 
                
                if (stop_checker and stop_checker()) or len(job_records) >= max_jobs: # CHECK 2
                    print("Stop signal received before loading new page.")
                    break
                    
                # Format keywords for URL (replacing space with +)
                formatted_job = job_keyword.replace(' ', '+')
                formatted_location = location_keyword.replace(' ', '+')
                
                url = paginaton_url.format(formatted_job, formatted_location, page_no)
                
                print(f"\n--- Loading Search Page {page_no//10 + 1} for {job_keyword} in {location_keyword} ---")
                
                # get_dom is a blocking operation
                search_dom = get_dom(url)
                
                if search_dom is None:
                    print(f"Skipping search URL {url} due to block or load failure. Moving to next search combination.")
                    break 
                
                jobs = search_dom.xpath('//a[starts-with(@id, "sj_")]/ancestor::li')
                
                if not jobs:
                    print("Warning: No job cards found. Assuming end of results.")
                    time.sleep(random.uniform(10, 20)) 
                    break 
                
                jobs_scraped_on_page = 0
                
                for job in jobs:
                    
                    if (stop_checker and stop_checker()) or len(job_records) >= max_jobs: # CHECK 3
                        print("Stop signal received while processing job cards on page.")
                        break

                    job_link_partial = get_job_link(job)
                    if job_link_partial == 'Not available':
                        continue 
                    
                    full_job_url = base_url + job_link_partial
                    
                    try:
                        # get_full_job_desc is a blocking operation
                        full_description = get_full_job_desc(full_job_url)
                    except Exception as e:
                        print(f"   -> CRITICAL ERROR fetching description for {full_job_url}: {e}. Skipping this job.")
                        full_description = "CRITICAL FETCH ERROR"

                    record = {
                        'job_link': full_job_url, 
                        'job_title': get_job_title(job), 
                        'company_name': get_company_name(job), 
                        'company_location': get_company_location(job), 
                        'salary': get_salary(job), 
                        'job_type': get_job_type(job), 
                        'rating': get_rating(job), 
                        'job_description': full_description, 
                        'searched_job': job_keyword, 
                        'searched_location': location_keyword
                    }
                    job_records.append(record)
                    jobs_scraped_on_page += 1
                    
                    time.sleep(random.uniform(3, 7)) 

                    # --- NEW CODE: Check the job limit after adding a job ---
                    if len(job_records) >= max_jobs:
                        print(f"Goal reached! Scraped {len(job_records)} jobs. Stopping search immediately.")
                        break # Exits the 'for job in jobs:' loop
                    # --------------------------------------------------------

                # If we broke out of the inner job loop due to stop or limit, break the page loop too
                if (stop_checker and stop_checker()) or len(job_records) >= max_jobs:
                    break
                    
                print(f"Processed {jobs_scraped_on_page} jobs from page {page_no//10 + 1}. Total scraped: {len(job_records)}")
                
                time.sleep(random.uniform(10, 20)) 

            # If we broke out of the page loop due to stop or limit, break the keyword loop too
            if (stop_checker and stop_checker()) or len(job_records) >= max_jobs:
                break

        print(f"Finished search for {job_keywords} in {location_keyword}. Total Jobs: {len(job_records)}")
        return job_records

    except KeyboardInterrupt:
        print("\n\n*** Scraping manually interrupted by user (Ctrl+C). ***")
        return job_records
    
    finally:
        # Crucial: Close the browser when the scraping thread finishes
        if driver:
              print("\nShutting down WebDriver after scraping completion...")
              try:
                  driver.quit()
              except Exception as e:
                  print(f"Error during final driver quit: {e}")
              time.sleep(2) 
              driver = None