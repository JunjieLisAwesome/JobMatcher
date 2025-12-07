# model_logic.py (Revised to use pdfplumber)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline, BitsAndBytesConfig
import pdfplumber  # <-- Using the library you provided
import os

# Set a persistent model ID (Using your working 3B model)
MODEL_ID = "meta-llama/Llama-3.2-3B-Instruct" 

# --- 1. Model Initialization (No Change Needed) ---

def load_job_recommender():
    """
    Loads the quantized Llama 3.2 3B model and returns the text generation pipeline.
    This function should only be called once when the application starts.
    """
    print("Initializing Job Recommender Model...")
    
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    
    # Use hf-cli login token (or replace None with your "hf_..." token if not logged in)
    hf_token = os.environ.get("HF_TOKEN", None) 
    
    # Load Tokenizer & Model
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=hf_token)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.float16,
        token=hf_token
    )

    # Create Pipeline
    generator = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer
    )

    print("Model loaded successfully! Ready for inference.")
    return generator

# --- 2. Inference Function (No Change Needed) ---

def generate_job_titles(generator, resume_text):
    """
    Uses the loaded pipeline to generate job recommendations from resume text.
    Returns a list of job titles.
    """
    system_prompt = (
        "You are an expert career counselor. Analyze the following resume text and "
        "suggest 3 to 5 highly relevant, modern job titles the person is qualified for. "
        "The output MUST be a comma-separated list of only the job titles, with no "
        "other text, introduction, or explanation. "
        "Example: Senior Software Engineer, Data Scientist, Solutions Architect"
    )
    
    prompt = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n{resume_text}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"

    output = generator(
        prompt,
        max_new_tokens=100,
        do_sample=True,
        temperature=0.7,
        pad_token_id=generator.tokenizer.eos_token_id 
    )
    
    generated_text = output[0]["generated_text"].split("<|start_header_id|>assistant<|end_header_id|>\n")[-1].strip()
    
    return [title.strip() for title in generated_text.split(',') if title.strip()]

# --- 3. PDF Extraction Utility (REVISED) ---

def extract_text_from_pdf(file_path):
    """
    Extracts all text content from a given PDF file path using pdfplumber.
    """
    if not file_path or not os.path.exists(file_path):
        return ""
        
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # Use extract_text for robust text extraction
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        return text
    except Exception as e:
        print(f"Error extracting text from PDF with pdfplumber: {e}")
        return ""

def calculate_match_score(llm_generator, resume_text, job_description):
    """
    Uses the LLM to calculate a compatibility score (0-100) between a resume and a job description.
    """
    
    # Construct the prompt for the LLM
    prompt = (
        f"Analyze the following RESUME and JOB DESCRIPTION. Based ONLY on the skills, experience, and requirements mentioned, "
        f"provide a numerical match score from 0 to 100 indicating compatibility. "
        f"Output ONLY the score as a plain integer, nothing else.\n\n"
        f"RESUME: {resume_text}\n\n"
        f"JOB DESCRIPTION: {job_description}"
    )
    
    try:
        # Assume llm_generator.generate_text is your function to call the model
        response = llm_generator.generate_text(prompt)
        
        # Clean the response to ensure we get a pure integer
        score_str = "".join(filter(str.isdigit, response.strip()))
        
        if score_str:
            score = int(score_str)
            return min(100, max(0, score)) # Ensure score is between 0 and 100
        else:
            print(f"LLM returned non-score response: {response}")
            return 0 # Default to 0 if the LLM fails to provide a clear score
            
    except Exception as e:
        print(f"Error during match score generation: {e}")
        return 0
    
    
# If you run this file directly, it will test the model logic
if __name__ == '__main__':
    # This block allows you to test the model loader directly
    print("--- Testing model_logic.py ---")
    test_generator = load_job_recommender()
    
    # You'll need to create a test PDF named 'test_resume.pdf' 
    # in the same directory to run this test successfully.
    test_pdf_path = "test_resume.pdf"
    
    if os.path.exists(test_pdf_path):
        sample_resume = extract_text_from_pdf(test_pdf_path)
        if sample_resume:
            print(f"Extracted Text (first 500 chars): {sample_resume[:500]}...")
            titles = generate_job_titles(test_generator, sample_resume)
            print("\n--- Test Output (Generated Titles) ---")
            print(titles)
        else:
            print("Could not extract text from test_resume.pdf.")
    else:
        print(f"Skipping LLM test: Please create a '{test_pdf_path}' file to test extraction and generation.")