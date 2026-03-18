"""
PIPELINE ORCHESTRATOR: src/main.py
----------------------------------
This is the entry point of the application. It coordinates the data flow between:
1. Pre-processing (Cleaning)
2. Extraction (Architect Agent)
3. Validation (Pydantic Schema Check)
4. Auditing (Verification Agent)

It implements a Self-Correction Loop that allows the AI to fix its own errors.
"""

import json
import os
from agents.extraction_agent import ExtractionAgent
from utils.rtl_preprocessor import preprocess_rtl
from utils.json_validator import validate_json_output
from agents.auditor_agent import AuditorAgent

def run_pipeline(file_name):
    """
    Executes the full agentic workflow for a single RTL file.
    
    Args:
        file_name (str): The name of the SystemVerilog file in data/raw/
    """
    print(f"--- Starting Agentic Pipeline for {file_name} ---")
    
    # 1. Path Management
    # Logic: Define where we read raw RTL and where we save processed JSON.
    raw_path = os.path.join("data", "raw", file_name)
    processed_dir = os.path.join("data", "processed")
    
    if not os.path.exists(processed_dir):
        os.makedirs(processed_dir)
    
    if not os.path.exists(raw_path):
        print(f"❌ Error: Source file not found at {raw_path}")
        return

    # 2. Pre-processing Phase
    # Logic: Strip comments and whitespace to optimize token usage and focus.
    clean_rtl = preprocess_rtl(raw_path)
    
    # Initialize our AI Agents
    extractor = ExtractionAgent() 
    auditor = AuditorAgent()

    # --- THE SELF-CORRECTION LOOP ---
    # Logic: We implement a "Try-Verify-Fix" pattern. If the Auditor finds a 
    # mistake, we pass those mistakes back to the Extractor as 'feedback'.
    max_retries = 3
    feedback = "" 

    for attempt in range(max_retries):
        print(f"\n🔄 Attempt {attempt + 1} of {max_retries}...")
        
        # 3. Extraction Step
        # If feedback exists, the Agent enters 'Revision Mode'.
        json_raw = extractor.extract_schema(clean_rtl, feedback=feedback)
        
        try:
            # 4. JSON Format & Schema Validation
            # Logic: First check if it is valid JSON, then check if it matches our Pydantic keys.
            data = json.loads(json_raw)
            validated_data = validate_json_output(data)
            
            if not validated_data:
                # Failure here means the AI used wrong keys (e.g., 'modules' instead of 'definitions')
                print("⚠️ Schema Validation Failed. Retrying...")
                feedback = "Your output did not match the Pydantic schema keys. Ensure 'design_name', 'definitions', and 'instantiations' are present."
                continue

            # 5. Hardware Audit Phase (The Critic)
            # Logic: Even if the JSON is valid, is the HARDWARE content correct?
            print("🔍 Starting Audit Phase...")
            audit_results_raw = auditor.audit_design(clean_rtl, json.dumps(validated_data))
            audit_results = json.loads(audit_results_raw)

            if audit_results["status"] == "PASSED":
                print("✅ Audit Passed: JSON is a faithful representation of RTL.")
                
                # 6. Finalization & Storage
                output_name = file_name.replace('.sv', '.json')
                output_path = os.path.join(processed_dir, output_name)
                
                with open(output_path, 'w') as f:
                    json.dump(validated_data, f, indent=2)
                
                print(f"📦 Successfully finalized and saved to {output_path}")
                return # Exit successfully
            
            else:       
                # Logic: If the audit fails, we collect the specific errors and loop back.
                print(f"❌ Audit Failed. Discrepancies found:")
                for i, error in enumerate(audit_results['errors']):
                    print(f"  {i+1}. {error}")
                
                # Prepare feedback for the next iteration
                feedback = (f"Your previous JSON was 90% correct but had these hardware bugs: "
                           f"{'; '.join(audit_results['errors'])}. PLEASE DO NOT CHANGE THE REST OF THE STRUCTURE.")    
                
        except json.JSONDecodeError:
            print("⚠️ AI returned invalid JSON format. Retrying...")
            feedback = "Your last response was not valid JSON. Please return ONLY a valid JSON object."

    print(f"\n🚨 Pipeline failed after {max_retries} attempts. Check audit errors for details.")

if __name__ == "__main__":
    # Example execution: Can be expanded to loop through all files in data/raw/
    run_pipeline("top.sv")