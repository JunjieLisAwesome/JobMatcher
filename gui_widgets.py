# gui_widgets.py
import os
import sys
import webbrowser
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QScrollArea, QPushButton, QLabel, QHBoxLayout, 
    QVBoxLayout, QFileDialog, QSizePolicy, QLineEdit, QApplication
)
from PySide6.QtGui import QFont, QCursor
from PySide6 import QtCore

# Import refactored modules
from utils_constants import clear_layout
#from llm_pdf_logic import load_job_recommender, extract_text_from_pdf, generate_job_titles
from scraper_worker import ScraperWorker
from scraper_logic import scrape_indeed_jobs
try:
    from model_loader import load_job_recommender, extract_text_from_pdf, generate_job_titles
except ImportError:
    print("FATAL ERROR: Could not import model logic. Please ensure 'model_loader.py' is in this directory.")
    sys.exit(1)


class MainWindowWidget(QWidget):
    
    current_file_path = None 
    
    def __init__(self):
        super(MainWindowWidget, self).__init__()
        self.resize(1200, 900)
        self.extracted_resume_text = None
        self.scraper_thread = None
        
        # --- WIDGET INITIALIZATION (Importing from constants needed PySide classes) ---
        from PySide6.QtPdfWidgets import QPdfView
        from PySide6.QtPdf import QPdfDocument
        
        # PDF Viewer (Left Part)
        self.pdf_document = QPdfDocument()
        self.pdf_view = QPdfView()
        self.pdf_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pdf_view.setMinimumSize(450, 600)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.pdf_view.setDocument(self.pdf_document)

        # Control Buttons
        self.load_button = QPushButton("Load Resume (PDF)")
        self.load_button.clicked.connect(self.load_pdf_but)

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

        # Scroll Area for Job Titles
        self.job_scroll_area = QScrollArea()
        self.job_scroll_area.setWidgetResizable(True)
        self.job_scroll_area.setWidget(self.job_buttons_container)
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
        self.right_label = QLabel("Output Panel: LLM status and runtime progress will be displayed here.") 
        self.right_label.setStyleSheet("background-color: #000000; border: 1px solid #ccc; padding: 10px; color: #fff;")
        self.right_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.right_label.setFont(QFont("Monospace", 9)) 

        # Results Container (For Job Cards)
        self.results_container = QWidget() 
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setAlignment(QtCore.Qt.AlignTop) 

        self.results_scroll_area = QScrollArea() 
        self.results_scroll_area.setWidgetResizable(True)
        self.results_scroll_area.setWidget(self.results_container)
        self.results_scroll_area.hide() 

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

        # --- LAYOUT CONSTRUCTION ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.pdf_view) 
        left_layout.addWidget(self.load_button)
        left_layout.addWidget(self.status_label)
        left_layout.addWidget(self.process_button)

        location_group = QHBoxLayout()
        location_group.addWidget(self.location_label)
        location_group.addWidget(self.location_input)
        left_layout.addLayout(location_group)

        left_layout.addWidget(self.job_scroll_area) 
        
        search_controls_layout = QHBoxLayout() 
        search_controls_layout.addWidget(self.search_button)
        search_controls_layout.addWidget(self.stop_button)
        left_layout.addLayout(search_controls_layout)

        left_layout.addStretch()

        right_layout = QVBoxLayout()
        right_layout.addWidget(self.right_label) 
        right_layout.addWidget(self.results_scroll_area)
        
        main_layout = QHBoxLayout()
        main_layout.addLayout(left_layout, stretch = 1)
        main_layout.addLayout(right_layout, stretch = 1)

        self.setLayout(main_layout)
        self.setAcceptDrops(True)
        self.show()

    # ===============================================================
    # --- METHODS ---
    # ===============================================================

    def stop_job_search(self):
        """Signals the worker thread to stop and handles GUI state."""
        if self.scraper_thread and self.scraper_thread.isRunning():
            self.scraper_thread.stop() 
            self.status_label.setText("🛑 Stop signal sent. Waiting for thread to shut down...")
            self.stop_button.setEnabled(False) 
        else:
            self.status_label.setText("🛑 Scraper is not currently running.")

    def display_pdf(self, file_path):
        """Loads and displays the PDF file in the QPdfView."""
        self.pdf_document.load(file_path)
        self.pdf_view.update()
        self.current_file_path = file_path 
        self.status_label.setText(f"Loaded: {os.path.basename(file_path)}. Click Process.") 
        self.process_button.setEnabled(True)

    def load_pdf_but(self):
        """Handles the 'Load Resume (PDF)' button click, opening a file dialog."""
        self.fname, _ = QFileDialog.getOpenFileName(self, 'Open file', filter="PDF files (*.pdf)")
        if self.fname:
            self.display_pdf(self.fname)
            
    # --- Drag/Drop Methods (Kept for completeness) ---
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
        
        clear_layout(self.job_buttons_layout) 
        
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
        if self.llm_generator is None or not self.current_file_path:
            self.status_label.setText("LLM not loaded or no PDF loaded. Cannot process.")
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

        location = self.location_input.text().strip()
        
        if not self.current_file_path or not self.extracted_resume_text:
            self.status_label.setText("🛑 **Error:** Please load and 'Process Resume' first.")
            return
            
        if not location:
            self.status_label.setText("🛑 **Error:** Please enter a job location.")
            return
        
        # 2. Extract suggested job titles from the displayed list
        job_titles = []
        grid_widget = self.job_buttons_layout.itemAt(1).widget() if self.job_buttons_layout.count() > 1 else None
        
        if grid_widget and isinstance(grid_widget, QWidget) and grid_widget.layout() and isinstance(grid_widget.layout(), QGridLayout):
            grid_layout = grid_widget.layout()
            for r in range(grid_layout.rowCount()):
                for c in range(grid_layout.columnCount()):
                    item_widget = grid_layout.itemAtPosition(r, c)
                    if item_widget and item_widget.widget() and isinstance(item_widget.widget(), QLabel):
                        title = item_widget.widget().text().lstrip('•').strip()
                        if title:
                            job_titles.append(title)

        if not job_titles:
            self.status_label.setText("🛑 **Error:** Please click 'Process Resume' first to get job titles.")
            return

        # 3. Prepare and start the worker thread
        self.scraper_thread = ScraperWorker(
            llm_generator=self.llm_generator,
            resume_text=self.extracted_resume_text,
            job_titles=job_titles,
            location=location
        )

        # Connect the worker signals
        self.scraper_thread.progress.connect(self.update_status_progress)
        self.scraper_thread.result_ready.connect(self.display_matched_jobs)
        self.scraper_thread.error.connect(self.handle_scraper_error)
        self.scraper_thread.finished.connect(self.restore_gui_state) 

        # Update GUI to show busy state
        self.results_scroll_area.hide()
        clear_layout(self.results_layout)
        self.status_label.setText("🟡 Starting job search... (Browser window will open).")
        self.search_button.setEnabled(False)
        self.process_button.setEnabled(False)
        self.stop_button.setEnabled(True) 
        QApplication.setOverrideCursor(QCursor(QtCore.Qt.WaitCursor))
        
        self.right_label.setText("--- Scraper, CSV Save, and Matching Progress ---\n") 
        
        self.scraper_thread.start()

    def display_matched_jobs(self, high_match_jobs):
        """Clears the output and displays only the high-match jobs."""
        
        clear_layout(self.results_layout) 
        self.results_scroll_area.show() 

        num_high_matches = len(high_match_jobs)
        
        if not high_match_jobs:
            self.right_label.setText("⚠️ Search complete. No jobs with a match score of 70% or higher were found.")
            return
            
        sorted_jobs = sorted(high_match_jobs, key=lambda x: x['match_score'], reverse=True)

        self.right_label.setText(f"✅ Search complete. Found **{num_high_matches}** jobs with a score >= 70%. Displaying results below.")

        header_label = QLabel("--- 🎯 HIGH MATCHES (Score 70%+ | Sorted by Score) ---")
        header_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.results_layout.addWidget(header_label)

        for job in sorted_jobs:
            # Create a Job Card Widget
            job_card = QWidget()
            card_layout = QVBoxLayout(job_card)
            
            # Job Card Styling
            job_card.setStyleSheet("border: 2px solid #4CAF50; margin: 5px; padding: 5px; background-color: #f0fff0;")
            
            # 1. Job Details Label
            details_text = (
                f"<span style='font-size:16pt; font-weight:bold; color:#0056b3;'>{job['job_title']}</span><br>"
                f"**Match Score: {job['match_score']} %**<br>"
                f"Company: {job['company_name']} ({job.get('company_location', 'Location N/A')})"
            )
            details_label = QLabel(details_text)
            details_label.setWordWrap(True)
            details_label.setTextFormat(QtCore.Qt.RichText)
                
            card_layout.addWidget(details_label)

            # 2. Clickable Link Button
            job_link = job.get('job_link')
            link_button = QPushButton("Go to Job Posting 🔗")
            link_button.setCursor(QCursor(QtCore.Qt.PointingHandCursor))
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

        lines = current_text.split('\n')
        if len(lines) > 30:
            current_text = '\n'.join(lines[0:2] + lines[-28:])
            
        self.right_label.setText(current_text + f"\n[PROGRESS]: {message}")
        self.right_label.repaint()

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
        
        # Check if job titles were displayed before restoring the search button state
        if self.job_buttons_layout.count() > 1 and self.job_buttons_layout.itemAt(1).widget():
             self.search_button.setEnabled(True)
        else:
             self.search_button.setEnabled(False)