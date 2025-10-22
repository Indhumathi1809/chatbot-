import pdfplumber
import google.generativeai as genai
import json
import re
import os

# ====== CONFIGURE GEMINI ======
genai.configure(api_key="AIzaSyBtesPBXTGCKqV1ySFnVCx5pkIaSbdYcwg")
model = genai.GenerativeModel("models/gemini-2.5-flash")

# ====== STEP 1: Extract text with better formatting ======
def extract_sample_text_with_layout(pdf_path, max_pages=5):
    """Extract text while preserving some layout information"""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:max_pages]:
            # Try to extract with layout
            extracted = page.extract_text(layout=True)
            if extracted:
                text += extracted + "\n"
    return text.strip()

# ====== STEP 2: Enhanced Gemini prompt for better parsing ======
def ask_gemini_to_generate_parser(text_sample, headers):
    prompt = f"""
You are a Python expert writing a bank statement parser. The PDF contains a transaction table with FIXED COLUMN POSITIONS.

TEXT SAMPLE:
{text_sample[:4000]}

COLUMN HEADERS (in exact order): {headers}

PARSING STRATEGY - COLUMN-BASED APPROACH:
1. Find transaction rows by DATE pattern: \\b\\d{{2}}-\\d{{2}}-\\d{{4}}\\b
2. Each transaction may span multiple lines due to word wrapping
3. Use POSITIONAL LOGIC - don't just concatenate everything

DETAILED COLUMN ANALYSIS:
Looking at the sample text, I can see the structure:
- Column 1: Date (01-03-2025, 02-03-2025, etc.)
- Column 2: Branch Description (980, 098, etc. followed by description)
- Column 3: Sender's/Beneficiary's Name (KOGILARASI, SANJAY KUMAR, etc.)
- Column 4: Reference 1 (RHBQR0196, reference codes)
- Column 5: Reference 2 (20250301MB, additional codes)
- Column 6: RefNum (00007542, 00004964, etc.)
- Column 7: Amount (DR) (debit amounts or empty)
- Column 8: Amount (CR) (credit amounts or empty)  
- Column 9: Balance (2,326.27+, 2,421.27+, etc.)

CRITICAL RULES:
1. DO NOT merge content from different columns into one field
2. Multi-line content should only be merged if it belongs to the SAME column
3. Use whitespace and positioning to determine column boundaries
4. Each amount should go to either DR or CR column, never both
5. Balance is always the rightmost value ending with + or -

Write a Python function `parse_transactions(text: str) -> List[Dict]` that:

STEP 1: Split text into lines and identify transaction start lines (those with dates)
STEP 2: For each transaction, collect all its lines (until next date or end)
STEP 3: Parse each transaction's lines using column positions and regex patterns
STEP 4: Handle multi-line fields by intelligent concatenation within same column
STEP 5: Return structured data matching: {headers}

EXAMPLE PARSING LOGIC:
```python
import re
from typing import List, Dict

def parse_transactions(text: str) -> List[Dict]:
    lines = text.strip().split('\\n')
    transactions = []
    
    # Find transaction boundaries
    date_pattern = r'\\b(\\d{{2}}-\\d{{2}}-\\d{{4}})\\b'
    current_transaction_lines = []
    
    for line in lines:
        if re.search(date_pattern, line):
            # Process previous transaction if exists
            if current_transaction_lines:
                transaction = parse_single_transaction(current_transaction_lines)
                if transaction:
                    transactions.append(transaction)
            # Start new transaction
            current_transaction_lines = [line]
        else:
            # Add to current transaction
            if current_transaction_lines:
                current_transaction_lines.append(line)
    
    # Process last transaction
    if current_transaction_lines:
        transaction = parse_single_transaction(current_transaction_lines)
        if transaction:
            transactions.append(transaction)
    
    return transactions

def parse_single_transaction(lines: List[str]) -> Dict:
    # Implement column-based parsing here
    # Use regex and positioning to extract each field
    # Return properly structured dictionary
    pass
```

Complete this implementation with proper column extraction logic.
Respond ONLY with complete Python code in ```python ``` block.
"""
    response = model.generate_content(prompt)
    return response.text


# ====== STEP 3: Execute AI-generated parser ======
def run_generated_parser(parser_code: str, full_text: str):
    # Extract only the code block between triple backticks
    code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", parser_code, re.DOTALL)
    if code_match:
        code = code_match.group(1)
    else:
        # Fallback: use the whole string if no code block found
        code = parser_code.strip()

    namespace = {}
    try:
        exec(code, namespace)
    except Exception as e:
        print("❌ Error in generated parser code:", e)
        print("💡 Here is the generated code for debugging:")
        print(code)
        raise e

    if "parse_transactions" not in namespace:
        raise ValueError("❌ Function `parse_transactions` not found in generated code.")

    parse_func = namespace["parse_transactions"]
    return parse_func(full_text)


# ====== MANUAL FALLBACK PARSER ======
def manual_parser_fallback(text: str) -> list:
    """Fallback manual parser as backup"""
    lines = text.strip().split('\n')
    transactions = []
    
    date_pattern = r'\b(\d{2}-\d{2}-\d{4})\b'
    current_transaction_lines = []
    
    for line in lines:
        # Skip summary lines
        if any(keyword in line.upper() for keyword in ['BALANCE B/F', 'CLOSING BALANCE', 'DEPOSIT ACCOUNT SUMMARY', 'BEGINNING BALANCE', 'ENDING BALANCE']):
            continue
            
        if re.search(date_pattern, line):
            # Process previous transaction
            if current_transaction_lines:
                transaction = parse_single_transaction_manual(current_transaction_lines)
                if transaction:
                    transactions.append(transaction)
            # Start new transaction
            current_transaction_lines = [line]
        else:
            if current_transaction_lines and line.strip():
                current_transaction_lines.append(line)
    
    # Process last transaction
    if current_transaction_lines:
        transaction = parse_single_transaction_manual(current_transaction_lines)
        if transaction:
            transactions.append(transaction)
    
    return transactions

def parse_single_transaction_manual(lines: list) -> dict:
    """Manual parsing of a single transaction"""
    if not lines:
        return None
    
    # Combine all lines
    full_text = ' '.join(line.strip() for line in lines)
    
    # Extract date
    date_match = re.search(r'\b(\d{2}-\d{2}-\d{4})\b', full_text)
    if not date_match:
        return None
    
    date = date_match.group(1)
    
    # Extract balance (rightmost number with + or -)
    balance_match = re.search(r'(\d{1,3}(?:,\d{3})*\.\d{2}[+-]?)\s*$', full_text)
    balance = balance_match.group(1) if balance_match else ""
    
    # Extract amounts (look for standalone numbers)
    amount_pattern = r'\b(\d{1,3}(?:,\d{3})*\.\d{2})\b'
    amounts = re.findall(amount_pattern, full_text)
    
    # Remove balance from amounts
    if balance:
        balance_num = balance.replace('+', '').replace('-', '')
        amounts = [amt for amt in amounts if amt != balance_num]
    
    # Determine DR/CR
    amount_dr = ""
    amount_cr = ""
    if amounts:
        # Simple heuristic: if balance increases, it's credit
        if '+' in balance or not balance:
            amount_cr = amounts[0] if amounts else ""
        else:
            amount_dr = amounts[0] if amounts else ""
    
    return {
        "Date": date,
        "Branch Description": "",  # Would need more complex parsing
        "Sender's / Beneficiary's Name": "",
        "Reference 1 / Recipient's Reference": "",
        "Reference 2 / Other Payment Details": "",
        "RefNum": "",
        "Amount (DR)": amount_dr,
        "Amount (CR)": amount_cr,
        "Balance": balance
    }


# ====== MAIN PIPELINE ======
def main():
    pdf_path = input("Enter PDF path: ").strip()
    output_json = "output_transactions.json"

    print("🔍 Extracting sample text with layout...")
    sample_text = extract_sample_text_with_layout(pdf_path)

    # ✅ Use predefined headers
    headers = [
        "Date",
        "Branch Description", 
        "Sender's / Beneficiary's Name",
        "Reference 1 / Recipient's Reference",
        "Reference 2 / Other Payment Details",
        "RefNum",
        "Amount (DR)",
        "Amount (CR)",
        "Balance"
    ]
    print(f"✅ Using Fixed Headers: {headers}")

    print("🧠 Asking Gemini to generate enhanced parser code...")
    parser_code = ask_gemini_to_generate_parser(sample_text, headers)

    # Save the generated parser
    with open("generated_parser_v2.py", "w", encoding="utf-8") as f:
        f.write(parser_code)
    print("💾 Generated parser saved to generated_parser_v2.py")

    try:
        print("⚙️ Executing the AI-generated parser...")
        full_text = extract_sample_text_with_layout(pdf_path, max_pages=20)
        parsed_data = run_generated_parser(parser_code, full_text)
    except Exception as e:
        print(f"⚠️ AI parser failed: {e}")
        print("🔄 Falling back to manual parser...")
        parsed_data = manual_parser_fallback(full_text)

    print(f"💾 Saving parsed data to {output_json}")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2)

    print("✅ Extraction Complete.")
    print(f"📊 Extracted {len(parsed_data)} transactions")
    
    # Show preview
    if parsed_data:
        print("\n📋 Preview of first transaction:")
        print(json.dumps(parsed_data[0], indent=2))

# ====== ENTRY POINT ======
if __name__ == "__main__":
    main()