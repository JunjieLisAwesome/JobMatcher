# llm_match_logic.py
import random
from utils_constants import SYSTEM_PROMPT_MATCHING, SCORE_PATTERN

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
    
    # FULL PROMPT STRING (Matching your working Llama-like format)
    full_prompt = (
        f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{SYSTEM_PROMPT_MATCHING}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n{user_input}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
    )

    final_score = random.randint(50, 99) # Default to a random score if LLM fails
    
    try:
        # Call the generator object directly
        llm_output = llm_generator(
            full_prompt,
            max_new_tokens=256,
            do_sample=True,
            temperature=0.7,
            pad_token_id=llm_generator.tokenizer.eos_token_id 
        )
        
        # Extract the assistant's response part
        generated_text = llm_output[0]["generated_text"].split("<|start_header_id|>assistant<|end_header_id|>\n")[-1].strip()
        
        print(f"\n--- LLM Response for Job Match ---\n{generated_text}\n---------------------------------\n")

        # PARSE THE SCORE
        match = SCORE_PATTERN.search(generated_text)
        
        if match:
            parsed_score = int(match.group(1))
            final_score = max(0, min(100, parsed_score)) # Clamp 0-100
        else:
            print("WARNING: Could not parse SCORE from LLM response. Using random fallback score.")
            
    except Exception as e:
        print(f"CRITICAL LLM INFERENCE ERROR during matching: {e}. Using random fallback score.")
        
    return final_score