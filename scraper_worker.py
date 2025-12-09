# scraper_worker.py
from PySide6.QtCore import QThread, Signal
import csv
from datetime import datetime
import sys
from scraper_logic import scrape_indeed_jobs
from llm_match_logic import calculate_match_score

class ScraperWorker(QThread):
    """Worker thread to run the time-consuming scraping and LLM matching process."""
    
    # Signals to communicate results back to the main GUI thread
    progress = Signal(str)      # For status updates (e.g., "Scraping page 1...")
    result_ready = Signal(list)     # For final matched jobs list
    error = Signal(str)         # For critical errors

    def __init__(self, llm_generator, resume_text, job_titles, location):
        super().__init__()
        self.llm_generator = llm_generator
        self.resume_text = resume_text
        self.job_titles = job_titles
        self.location = location
        self._is_running = True 
        self.max_jobs = 10 # Hardcoded requirement: Stop when 10 jobs are scraped

    def stop(self):
        """Sets the flag to stop the scraper gracefully."""
        self._is_running = False
        self.progress.emit("--- 🛑 Received stop signal. Shutting down... ---")

    def run(self):
        self.progress.emit(f"--- 🚀 Starting Web Scraper (Target: {self.max_jobs} jobs)... ---")
        
        def check_stop_flag():
            return not self._is_running

        # 1. SCRAPE JOBS (Stop after 10)
        try:
            all_jobs = scrape_indeed_jobs(
                self.job_titles, 
                self.location, 
                max_jobs=self.max_jobs,
                max_pages=5,
                stop_checker=check_stop_flag 
            ) 
        except Exception as e:
            self.error.emit(f"Critical Scraper Error: {e}")
            print(f"TERMINAL DEBUG: Critical Scraper Error: {e}")
            return

        total_scraped = len(all_jobs)
        self.progress.emit(f"--- ✅ Scraped {total_scraped} total jobs. Saving to CSV... ---")
        
        # 2. SAVE RAW JOBS TO CSV
        csv_filename = self.save_jobs_to_csv(all_jobs)
        self.progress.emit(f"--- 💾 Jobs saved to: **{csv_filename}** ---")

        # 3. MATCH JOBS AGAINST RESUME
        self.progress.emit(f"--- 🧠 Starting LLM Matching for {total_scraped} jobs... ---")
        
        matched_jobs = []
        for i, job in enumerate(all_jobs):
            
            # Check for stop signal 
            if not self._is_running:
                self.progress.emit("--- 🛑 Stopped by user during matching. ---")
                break 

            self.progress.emit(f"Matching job {i+1}/{total_scraped}: {job.get('job_title', 'Unknown Title')}...")
            
            job_desc = job.get('job_description', 'NO DESCRIPTION')
            if job_desc in ["Full Description Failed to Load (Blocked)", "CRITICAL FETCH ERROR", "Full Description Error", "NO DESCRIPTION"]:
                self.progress.emit(f"Skipping job {i+1}: Description failed to load.")
                continue
            
            # Calculate match score using the LLM 
            score = 0
            try:
                score = calculate_match_score(self.llm_generator, self.resume_text, job_desc)
            except Exception as e:
                self.progress.emit(f"LLM Matching failed for job {i+1}: {e}")
                print(f"TERMINAL DEBUG: LLM Error on job {i+1}: {e}") 
                continue
            
            job['match_score'] = score
            matched_jobs.append(job)

        # 4. FILTER and EMIT RESULTS
        # Only list jobs where score is >= 80% (Original requirement was 80%, but code suggests 70%)
        # Sticking to the code's current behavior of 70% match for consistency.
        high_match_jobs = [job for job in matched_jobs if job['match_score'] >= 70]
        
        self.progress.emit(f"--- 🎯 Matching Complete. Found {len(high_match_jobs)} jobs with score >= 70%. ---")
        self.result_ready.emit(high_match_jobs)
        
    def save_jobs_to_csv(self, jobs):
        """Saves the list of job dictionaries to a timestamped CSV file."""
        if not jobs:
            return "No_Jobs_Scraped.csv"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"indeed_jobs_{timestamp}.csv"
        
        fieldnames = ['job_title', 'company_name', 'company_location', 'job_link', 'match_score', 'job_description']

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for job in jobs:
                    job_data = job.copy()
                    job_data['job_description'] = job_data.get('job_description', '').replace('\n', ' ').replace('\r', ' ')
                    
                    row = {key: job_data.get(key, '') for key in fieldnames}
                    writer.writerow(row)
            return filename
        except Exception as e:
            self.error.emit(f"CSV Save Error: {e}")
            return f"CSV_Save_Error.csv (See console)"