"""
RTL Pre-processing Utility
--------------------------
This script 'cleans' raw SystemVerilog files before they are sent to the LLM.
By stripping comments and whitespace, we reduce the 'Token Count' (lowering cost)
and ensure the AI focuses only on functional hardware logic.
"""

import re

def preprocess_rtl(file_path):
    """
    Reads an RTL file and extracts only the functional code.
    
    Args:
        file_path (str): Path to the .sv or .v file (e.g., 'data/raw/top.sv').
        
    Returns:
        str: A 'minified' version of the RTL, optimized for LLM processing.
    """
    try:
        # Load the raw source code
        with open(file_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: RTL file not found at {file_path}")
        return ""

    # --- NOISE REDUCTION STEPS ---

    # 1. Remove Multi-line Block Comments: /* comment */
    # We use re.DOTALL so the '.*?' matches across multiple lines.
    # This removes large headers or licensing text that doesn't affect logic.
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # 2. Remove Single-line Inline Comments: // comment
    # This prevents the AI from being confused by commented-out code 
    # or developer notes that might contradict the active logic.
    content = re.sub(r'//.*', '', content)
    
    # 3. Token & Formatting Optimization:
    # - splitlines(): Breaks the code into a list of lines.
    # - line.strip(): Removes leading/trailing spaces (indentation).
    # - if line.strip(): Filters out lines that are now empty after stripping.
    # - "\n".join(): Rebuilds the code into a compact, readable string.
    content = "\n".join([line.strip() for line in content.splitlines() if line.strip()])
    
    return content