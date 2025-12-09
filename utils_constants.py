# utils_constants.py
import platform
import re
from PySide6.QtWidgets import QWidget
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtCore import QThread, Signal

# --- OS Specifics ---
op_sys = platform.system()
# Use NSURL as a workaround to pyside/Qt4 behaviour for dragging and dropping on OSx
if op_sys == 'Darwin':
    try:
        from Foundation import NSURL
    except ImportError:
        pass # Not critical if we're not running on MacOS

# --- LLM Constants ---
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

# --- Helper Functions ---
def clear_layout(layout):
    """Helper function to remove widgets from a layout."""
    if layout is not None:
        while layout.count():
            child = layout.takeAt(0)
            if child.widget() is not None:
                child.widget().deleteLater()
            elif child.layout() is not None:
                clear_layout(child.layout())