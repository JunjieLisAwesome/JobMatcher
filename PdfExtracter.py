import pdfplumber

with pdfplumber.open("junjie.pdf") as pdf:
    text = ""
    for page in pdf.pages:          # iterate over all pages
        text += page.extract_text() + "\n"

print(text)