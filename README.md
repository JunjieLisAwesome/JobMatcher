# JobMatcher

JobMatcher is an intelligent job‑matching application that allows users to upload their resume and automatically find highly relevant job postings from Indeed. The system uses a Large Language Model (LLM) to perform **semantic matching** based on:

* Work experience
* Required skill sets
* Job requirements

Jobs with a **matching score above 70%** are returned to the user.

---

## Processing Flow

![Processing](processing.png)

---

## Matching Result Example

![Result](result.png)

---

## Deploy Requirements

### **Environment**

* Python **3.12.3**
* At least **4 GB GPU**

### **Install Dependencies**

Install all required libraries:

```
pip install torch transformers pdfplumber PySide6 bs4 lxml selenium undetected_chromedriver webbrowser --user
```

If any library is missing during runtime, install it when prompted.

### **Model Requirement**

* Apply for **Llama‑3.2‑3B‑Instruct** on HuggingFace
* Wait until your request is approved before running the program

---

## Troubleshooting

If you encounter any errors:

1. Check whether all required libraries are installed
2. Verify that Llama‑3.2‑3B‑Instruct is approved and downloaded
3. Ask GPT for debugging help — the core logic is confirmed to work

---
## License

This project is released under the MIT License. You are free to use, modify, and distribute the software as long as the license terms are included.

## Notes

* Ensure GPU drivers are properly installed
* Selenium setup may require a compatible Chrome version and chromedriver

