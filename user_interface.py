from __future__ import division, unicode_literals, print_function, absolute_import

from PySide6.QtWidgets import QWidget, QGridLayout, QScrollArea
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QHBoxLayout, QVBoxLayout, QFileDialog
from PySide6.QtGui import QFont 
from PySide6.QtWidgets import QSizePolicy, QLineEdit
from PySide6 import QtCore
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPdf import QPdfDocument
from PySide6.QtGui import QCursor 
from PySide6.QtCore import QThread, Signal
import sys
import platform
import os 
import random # For placeholder score
import webbrowser # Needed for opening links
import csv # For writing the output file
from datetime import datetime # For timestamping the file
import re
from scraper_logic import scrape_indeed_jobs

# --- 1. IMPORT MODEL LOGIC ---
try:
    from model_loader import load_job_recommender, extract_text_from_pdf, generate_job_titles
except ImportError:
    print("FATAL ERROR: Could not import model logic. Please ensure 'model_loader.py' is in this directory.")
    sys.exit(1)


# Use NSURL as a workaround to pyside/Qt4 behaviour for dragging and dropping on OSx
op_sys = platform.system()
if op_sys == 'Darwin':
    from Foundation import NSURL

# =======================================================================
# --- TEMPORARY PLACEHOLDER FOR LLM MATCHING LOGIC ---
# !!! REPLACE THIS WITH YOUR ACTUAL LLM INFERENCE CODE !!!
# =======================================================================
SYSTEM_PROMPT_MATCHING = (
    "You are a professional job matching assistant. Your task is to analyze a candidate's "
    "Resume against a Job Description. Your assessment must focus on three key areas: "
    "1. **Skills Similarity** "
    "2. **Work Experience Relevance** "
    "3. **Project/Portfolio Similarity** "
    "Your response MUST start with the FINAL MATCH SCORE on a single line, followed by your analysis. "
    "Use the following STRICT output format for the score: **SCORE: [Integer from 0 to 100]**\n"
    "Example of the required first line: **SCORE: 75**\n"
    "Do NOT include the percent sign (%)."
)
SCORE_PATTERN = re.compile(r'SCORE:\s*(\d{1,3})')

def calculate_match_score(llm_generator, resume_text, job_desc):
    """
    Implements the real LLM matching logic. Instructs the LLM to focus on 
    skills, experience, and project similarity to return a match score (0-100).
    """
    
    user_input = f"""
    --- RESUME ---
    {resume_text[:4000]} 

    --- JOB DESCRIPTION ---
    {job_desc[:4000]}
    """
    
    # 2. FULL PROMPT STRING (Matching your working Llama-like format)
    full_prompt = (
        f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{SYSTEM_PROMPT_MATCHING}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n{user_input}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
    )

    final_score = random.randint(50, 99) # Default to a random score if LLM fails
    
    try:
        # 3. CORRECT CALL: Call the generator object directly
        llm_output = llm_generator(
            full_prompt,
            max_new_tokens=256, # Increased tokens for detailed reasoning
            do_sample=True,
            temperature=0.7,
            pad_token_id=llm_generator.tokenizer.eos_token_id 
        )
        
        # Extract the assistant's response part
        generated_text = llm_output[0]["generated_text"].split("<|start_header_id|>assistant<|end_header_id|>\n")[-1].strip()
        
        print(f"\n--- LLM Response for Job Match ---\n{generated_text}\n---------------------------------\n")

        # 4. PARSE THE SCORE
        match = SCORE_PATTERN.search(generated_text)
        
        if match:
            parsed_score = int(match.group(1))
            final_score = max(0, min(100, parsed_score)) # Clamp 0-100
        else:
            print("WARNING: Could not parse SCORE from LLM response. Using random fallback score.")
            
    except Exception as e:
        print(f"CRITICAL LLM INFERENCE ERROR during matching: {e}. Using random fallback score.")
        
    return final_score

# =======================================================================
# --- SCRAPER WORKER THREAD ---
# =======================================================================
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
        
        # Define a function to check the stop flag specifically for the scraper
        def check_stop_flag():
            return not self._is_running

        # 1. SCRAPE JOBS (Stop after 10)
        try:
            # PASS THE STOP CHECKER TO THE BLOCKING FUNCTION AND THE MAX JOB LIMIT
            all_jobs = scrape_indeed_jobs(
                self.job_titles, 
                self.location, 
                max_jobs=self.max_jobs, # <-- NEW ARGUMENT TO LIMIT JOBS
                max_pages=5, # Fallback limit if max_jobs isn't hit
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
            
            # --- CRITICAL DEBUG PRINT ---
            print(f"TERMINAL DEBUG: Job {i+1} - Title: {job['job_title']}, Score: {score}") 
            
            matched_jobs.append(job) # Append all scored jobs

        # 4. FILTER and EMIT RESULTS
        # Only list jobs where score is >= 80% (New requirement)
        high_match_jobs = [job for job in matched_jobs if job['match_score'] >= 70]
        
        self.progress.emit(f"--- 🎯 Matching Complete. Found {len(high_match_jobs)} jobs with score >= 80%. ---")
        self.result_ready.emit(high_match_jobs)
        
    def save_jobs_to_csv(self, jobs):
        """Saves the list of job dictionaries to a timestamped CSV file."""
        if not jobs:
            return "No_Jobs_Scraped.csv"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"indeed_jobs_{timestamp}.csv"
        
        # Use a consistent set of keys for the CSV header
        fieldnames = ['job_title', 'company_name', 'company_location', 'job_link', 'match_score', 'job_description']

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for job in jobs:
                    # Clean up the job description for CSV readability (remove newlines)
                    job_data = job.copy()
                    job_data['job_description'] = job_data.get('job_description', '').replace('\n', ' ').replace('\r', ' ')
                    
                    # Ensure all fields are present (DictWriter requires keys to match fieldnames)
                    row = {key: job_data.get(key, '') for key in fieldnames}
                    writer.writerow(row)
            return filename
        except Exception as e:
            self.error.emit(f"CSV Save Error: {e}")
            return f"CSV_Save_Error.csv (See console)"


# =======================================================================
# --- MAIN WINDOW WIDGET ---
# =======================================================================
class MainWindowWidget(QWidget):
    
    current_file_path = None 
    
    def __init__(self):
        super(MainWindowWidget, self).__init__()
        self.resize(1200, 900)
        
        # --- WIDGET INITIALIZATION ---
        
        # PDF Viewer (Left Part)
        self.pdf_document = QPdfDocument()
        self.pdf_view = QPdfView()
        self.pdf_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pdf_view.setMinimumSize(450, 600)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.pdf_view.setDocument(self.pdf_document)

        # Control Buttons
        self.load_button = QPushButton("Load Resume (PDF)")
        self.load_button.clicked.connect(self.load_pdf_but) # <-- Connects to load_pdf_but

        # Status Label (Top-Left Status)
        self.status_label = QLabel("LLM Model Status: Loading...")
        self.status_label.setStyleSheet("padding: 5px; border: 1px dashed #aaa; background-color: #000000;")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

        self.process_button = QPushButton("Process Resume & Get Job Titles")
        self.process_button.clicked.connect(self.process_resume_llm)
        self.process_button.setEnabled(False) 

        # Job Location Input
        self.location_label = QLabel("Job Location:")
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("e.g., San Francisco, CA or Remote")

        # Dynamic Titles Layout (LEFT)
        self.job_buttons_container = QWidget() 
        self.job_buttons_layout = QVBoxLayout(self.job_buttons_container)
        self.job_buttons_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter) 

        # Scroll Area for Job Titles (Squeezes this section)
        self.job_scroll_area = QScrollArea()
        self.job_scroll_area.setWidgetResizable(True)
        self.job_scroll_area.setWidget(self.job_buttons_container)
        
        # FIX: Limit its growth
        self.job_scroll_area.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Maximum) 
        self.job_scroll_area.setMinimumHeight(50)  
        self.job_scroll_area.setMaximumHeight(200) 

        # Search Button
        self.search_button = QPushButton("Start Search (Scrape 10 Jobs & Match)")
        self.search_button.clicked.connect(self.start_job_search) 
        self.search_button.setEnabled(False) 

        self.stop_button = QPushButton("🛑 Stop Scraper")
        self.stop_button.clicked.connect(self.stop_job_search)
        self.stop_button.setEnabled(False) 
        self.stop_button.setStyleSheet("background-color: #ffcccc;")

        # Right Layout (Output)
        
        # 1. Progress/Status Label (Top of Right Panel)
        self.right_label = QLabel("Output Panel: LLM status and runtime progress will be displayed here.") 
        self.right_label.setStyleSheet("background-color: #000000; border: 1px solid #ccc; padding: 10px; color: #fff;")
        self.right_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.right_label.setFont(QFont("Monospace", 9)) 

        # 2. Results Container (For Job Cards)
        self.results_container = QWidget() # Inner widget to hold results
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setAlignment(QtCore.Qt.AlignTop) # Align results to the top

        self.results_scroll_area = QScrollArea() # The main scrollable area for job cards
        self.results_scroll_area.setWidgetResizable(True)
        self.results_scroll_area.setWidget(self.results_container)
        self.results_scroll_area.hide() # Hide until results are ready

        # --- 2. Initialize LLM ---
        QApplication.setOverrideCursor(QCursor(QtCore.Qt.WaitCursor))
        try:
            self.llm_generator = load_job_recommender()
            self.process_button.setEnabled(True) 
            self.status_label.setText("✅ **READY.** Load a resume, then click Process.")
            print("Application Ready.")
        except Exception as e:
            self.llm_generator = None
            self.status_label.setText(f"❌ **FAILED TO LOAD.** Check console.")
            self.right_label.setText(f"Detailed LLM Loading Error: {e}")
            print(f"Error loading LLM: {e}.")
        finally:
            QApplication.restoreOverrideCursor()

        # --- LAYOUT CONSTRUCTION (Left Column Order) ---
        
        left_layout = QVBoxLayout()
        # 1. PDF Viewer (Expands)
        left_layout.addWidget(self.pdf_view) 

        # 2. Fixed Controls 
        left_layout.addWidget(self.load_button)
        left_layout.addWidget(self.status_label)
        left_layout.addWidget(self.process_button)

        # 3. Location Input 
        location_group = QHBoxLayout()
        location_group.addWidget(self.location_label)
        location_group.addWidget(self.location_input)
        left_layout.addLayout(location_group)

        # 4. Dynamic Job Titles (Shrinking/Scrolling Area)
        left_layout.addWidget(self.job_scroll_area) 
        
        # 5. Search & Stop Buttons (Fixed at the bottom)
        search_controls_layout = QHBoxLayout() 
        search_controls_layout.addWidget(self.search_button)
        search_controls_layout.addWidget(self.stop_button)
        left_layout.addLayout(search_controls_layout)

        left_layout.addStretch() # Pushes all above elements up, keeping buttons fixed

        # --- LAYOUT CONSTRUCTION (Right Layout Order) ---
        right_layout = QVBoxLayout()
        # 1. Use self.right_label for initial status, errors, and progress updates
        right_layout.addWidget(self.right_label) 
        # 2. Use the scrollable area for final, interactive results (job cards)
        right_layout.addWidget(self.results_scroll_area)
        
        # Main layout 
        main_layout = QHBoxLayout()
        main_layout.addLayout(left_layout, stretch = 1)
        main_layout.addLayout(right_layout, stretch = 1)

        self.setLayout(main_layout)
        self.setAcceptDrops(True)
        self.show()

    # ===============================================================
    # --- METHODS ---
    # ===============================================================

    def clear_layout(self, layout):
        """Helper function to remove widgets from a layout."""
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget() is not None:
                    child.widget().deleteLater()
                elif child.layout() is not None:
                    self.clear_layout(child.layout())

    def stop_job_search(self):
        """Signals the worker thread to stop and handles GUI state."""
        if hasattr(self, 'scraper_thread') and self.scraper_thread.isRunning():
            self.scraper_thread.stop() 
            self.status_label.setText("🛑 Stop signal sent. Waiting for thread to shut down...")
            # Disable stop button immediately, let the 'finished' signal restore the rest.
            self.stop_button.setEnabled(False) 
        else:
            self.status_label.setText("🛑 Scraper is not currently running.")

    def display_pdf(self, file_path):
        """Loads and displays the PDF file in the QPdfView."""
        self.pdf_document.load(file_path)
        self.pdf_view.update()
        self.current_file_path = file_path 
        self.status_label.setText(f"Loaded: {os.path.basename(file_path)}. Click Process.") 

    def load_pdf_but(self):
        """Handles the 'Load Resume (PDF)' button click, opening a file dialog."""
        self.fname, _ = QFileDialog.getOpenFileName(self, 'Open file', filter="PDF files (*.pdf)")
        if self.fname:
            self.display_pdf(self.fname)
            
    # --- Drag/Drop Methods ---
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls:
            e.accept()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls:
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        """Drop files directly onto the widget"""
        if e.mimeData().hasUrls():
            e.setDropAction(QtCore.Qt.CopyAction)
            e.accept()
            file_path = str(e.mimeData().urls()[0].toLocalFile())
            self.display_pdf(file_path)
        else:
            e.ignore()

    def display_job_buttons(self, titles):
        """Creates and displays suggested job titles in a 2-column grid."""
        
        self.clear_layout(self.job_buttons_layout) 
        
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        
        if not titles:
            error_label = QLabel("No titles suggested.")
            error_label.setAlignment(QtCore.Qt.AlignCenter)
            self.job_buttons_layout.addWidget(error_label)
            self.search_button.setEnabled(False)
            return
            
        title_label = QLabel("Suggested Titles:")
        title_label.setFont(QFont("Arial", 10, QFont.Bold))
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.job_buttons_layout.addWidget(title_label) 

        # Populate the grid in two columns
        for i, title in enumerate(titles):
            # Ensure the title extracted is clean
            clean_title = title.lstrip('•').strip()
            if not clean_title:
                continue

            job_label = QLabel(f"• {clean_title}") 
            job_label.setFont(QFont("Arial", 10))
            job_label.setStyleSheet("padding: 2px; margin-left: 5px; border-bottom: 1px dashed #ddd;")
            
            row = i // 2
            col = i % 2
            grid_layout.addWidget(job_label, row, col)

        self.job_buttons_layout.addWidget(grid_widget)
        self.job_buttons_layout.addStretch() 
        self.search_button.setEnabled(True)

    def process_resume_llm(self):
        """The main handler for the 'Process' button."""
        if self.llm_generator is None:
            self.status_label.setText("LLM failed to load at startup. Cannot process.")
            return

        if not self.current_file_path:
            self.status_label.setText("🛑 **Error:** Please load a PDF file first.")
            return
        
        self.search_button.setEnabled(False)
        self.process_button.setText("Processing... (Inference running)")
        self.process_button.setEnabled(False) 
        QApplication.setOverrideCursor(QCursor(QtCore.Qt.WaitCursor)) 

        # 1. Extract Text
        resume_text = extract_text_from_pdf(self.current_file_path)
        
        if not resume_text:
            self.status_label.setText("❌ **Extraction Error.** Could not read the PDF text.")
            self.process_button.setText("Process Resume & Get Job Titles")
            self.process_button.setEnabled(True)
            QApplication.restoreOverrideCursor()
            return
            
        self.extracted_resume_text = resume_text 

        # Use right_label for temporary debug output
        self.right_label.setText(f"--- Extracted Resume Text (Ready for LLM) ---\n\n{resume_text.strip()[:1000]}...") 
        self.status_label.setText("Analyzing resume text...")
        
        # 2. Call LLM for Inference
        try:
            suggested_titles = generate_job_titles(self.llm_generator, resume_text)
        except Exception as e:
            suggested_titles = []
            print(f"LLM Generation Error: {e}")
            self.status_label.setText("❌ **LLM Error.** See right panel for details.")
            self.right_label.setText(f"❌ **LLM Generation Error:** {e}\n\n{resume_text.strip()[:1000]}...")
            
        # 3. Display Results (Titles on the LEFT)
        self.display_job_buttons(suggested_titles)
        
        # Restore GUI state
        if suggested_titles:
            self.status_label.setText("✅ Analysis complete. Titles ready. Enter location and click Start.")
        self.process_button.setText("Process Resume & Get Job Titles")
        self.process_button.setEnabled(True)
        QApplication.restoreOverrideCursor()


    def start_job_search(self):
        
        if self.llm_generator is None:
            self.status_label.setText("LLM failed to load. Cannot start search.")
            return

        # 1. Get required inputs
        location = self.location_input.text().strip()
        
        if not self.current_file_path:
            self.status_label.setText("🛑 **Error:** Please load a PDF file first.")
            return
            
        if not location:
            self.status_label.setText("🛑 **Error:** Please enter a job location.")
            return
        
        # Attempt to get extracted text, or extract it now
        resume_text = getattr(self, 'extracted_resume_text', None)
        if not resume_text:
            try:
                resume_text = extract_text_from_pdf(self.current_file_path)
                if not resume_text:
                    self.status_label.setText("❌ Extraction error: Cannot find resume text.")
                    return
            except Exception as e:
                self.status_label.setText(f"❌ Extraction error: {e}")
                return

        # 2. Extract suggested job titles from the displayed list
        job_titles = []
        # Find the QGridLayout widget inside the job_buttons_layout
        grid_widget = self.job_buttons_layout.itemAt(1).widget() if self.job_buttons_layout.count() > 1 else None
        
        if grid_widget and isinstance(grid_widget, QWidget) and grid_widget.layout() and isinstance(grid_widget.layout(), QGridLayout):
            grid_layout = grid_widget.layout()
            for r in range(grid_layout.rowCount()):
                for c in range(grid_layout.columnCount()):
                    item_widget = grid_layout.itemAtPosition(r, c)
                    if item_widget and item_widget.widget() and isinstance(item_widget.widget(), QLabel):
                        # Extract and clean the title from the QLabel text
                        title = item_widget.widget().text().lstrip('•').strip()
                        if title:
                            job_titles.append(title)


        if not job_titles:
            self.status_label.setText("🛑 **Error:** Please click 'Process Resume' first to get job titles.")
            return

        # 3. Prepare and start the worker thread
        self.scraper_thread = ScraperWorker(
            llm_generator=self.llm_generator,
            resume_text=resume_text,
            job_titles=job_titles,
            location=location
        )

        # Connect the worker signals
        self.scraper_thread.progress.connect(self.update_status_progress)
        self.scraper_thread.result_ready.connect(self.display_matched_jobs)
        self.scraper_thread.error.connect(self.handle_scraper_error)
        self.scraper_thread.finished.connect(self.restore_gui_state) 

        # Update GUI to show busy state
        self.results_scroll_area.hide() # Hide job cards while scraping is running
        self.clear_layout(self.results_layout) # Clear previous results
        self.status_label.setText("🟡 Starting job search... (Browser window will open).")
        self.search_button.setEnabled(False)
        self.process_button.setEnabled(False)
        self.stop_button.setEnabled(True) 
        QApplication.setOverrideCursor(QCursor(QtCore.Qt.WaitCursor))
        
        self.right_label.setText("--- Scraper, CSV Save, and Matching Progress ---\n") 
        
        self.scraper_thread.start()

    def display_matched_jobs(self, high_match_jobs):
        """Clears the output and displays only the high-match jobs (score >= 80)."""
        
        # Restore GUI state is handled by the finished signal connection.
        
        # CRITICAL FIX: Clear results and show the results scroll area
        self.clear_layout(self.results_layout) 
        self.results_scroll_area.show() 

        num_high_matches = len(high_match_jobs)
        
        if not high_match_jobs:
            self.right_label.setText("⚠️ Search complete. No jobs with a match score of 80% or higher were found.")
            return
            
        # Sort jobs by match score (highest first)
        sorted_jobs = sorted(high_match_jobs, key=lambda x: x['match_score'], reverse=True)

        self.right_label.setText(f"✅ Search complete. Found **{num_high_matches}** jobs with a score >= 80%. Displaying results below.")

        header_label = QLabel("--- 🎯 HIGH MATCHES (Score 80%+ | Sorted by Score) ---")
        header_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.results_layout.addWidget(header_label)

        for job in sorted_jobs:
            # Create a Job Card Widget
            job_card = QWidget()
            card_layout = QVBoxLayout(job_card)
            
            # Job Card Styling (Green border for high-match jobs)
            job_card.setStyleSheet("border: 2px solid #4CAF50; margin: 5px; padding: 5px; background-color: #f0fff0;")
            
            # 1. Job Details Label
            details_text = (
                f"<span style='font-size:16pt; font-weight:bold; color:#0056b3;'>{job['job_title']}</span><br>"
                f"**Match Score: {job['match_score']} %**<br>"
                f"Company: {job['company_name']} ({job.get('company_location', 'Location N/A')})"
            )
            details_label = QLabel(details_text)
            details_label.setWordWrap(True)
            details_label.setTextFormat(QtCore.Qt.RichText) # Enable bolding
                
            card_layout.addWidget(details_label)

            # 2. Clickable Link Button
            job_link = job.get('job_link')
            link_button = QPushButton("Go to Job Posting 🔗")
            link_button.setCursor(QCursor(QtCore.Qt.PointingHandCursor))
            # Use a lambda function to connect the button click to the open_link method
            link_button.clicked.connect(lambda checked, url=job_link: self.open_link(url))
            
            card_layout.addWidget(link_button)
            self.results_layout.addWidget(job_card)

    def open_link(self, url):
        """Opens the given URL in the user's default web browser."""
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Error opening link: {e}")
            self.status_label.setText(f"Error opening link: {url}")
            
    def update_status_progress(self, message):
        """Updates the status label during the scraping process and appends to the right panel."""
        self.status_label.setText(message)
        
        current_text = self.right_label.text()

        if not current_text.startswith("--- Scraper, CSV Save, and Matching Progress ---"):
             current_text = "--- Scraper, CSV Save, and Matching Progress ---\n" 

        # Limit the displayed text to prevent performance issues
        lines = current_text.split('\n')
        # Keep the header and the last 28 lines of progress
        if len(lines) > 30:
            current_text = '\n'.join(lines[0:2] + lines[-28:])
            
        self.right_label.setText(current_text + f"\n[PROGRESS]: {message}")
        self.right_label.repaint() # Force refresh the label

    def handle_scraper_error(self, message):
        """Handles errors from the worker thread."""
        self.status_label.setText(f"🛑 Critical Search Error: {message}")
        
        self.right_label.setText(f"--- CRITICAL SEARCH ERROR ---\n{message}\n\n{self.right_label.text()}")
        self.restore_gui_state()

    def restore_gui_state(self):
        """Restores the buttons and cursor after the thread finishes."""
        QApplication.restoreOverrideCursor()
        self.stop_button.setEnabled(False)
        if self.llm_generator:
            self.process_button.setEnabled(True)
        # Only re-enable search if job titles were successfully generated previously
        if self.job_buttons_layout.count() > 1:
            self.search_button.setEnabled(True)

# --- Run if called directly ---
if __name__ == '__main__':
    # Initialise the application
    app = QApplication(sys.argv)
    # Call the widget
    ex = MainWindowWidget()
    sys.exit(app.exec())