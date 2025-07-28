import pdfplumber
import google.generativeai as genai
import json
import re
import os
from typing import List, Dict, Optional

# ====== CONFIGURE GEMINI ======
genai.configure(api_key="AIzaSyBtesPBXTGCKqV1ySFnVCx5pkIaSbdYcwg")
model = genai.GenerativeModel("models/gemini-2.5-flash")

# ====== STEP 1: Extract text with layout preservation ======
def extract_sample_text_with_layout(pdf_path, max_pages=3):
    """Extract text while preserving layout information"""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:max_pages]:
            extracted = page.extract_text(layout=True)
            if extracted:
                text += extracted + "\n"
    return text.strip()

# ====== STEP 2: Auto-detect table headers ======
def detect_table_headers(text_sample: str) -> List[str]:
    """Use Gemini to automatically detect table headers from the PDF"""
    prompt = f"""
Analyze this bank statement text and identify the table column headers.

TEXT SAMPLE:
{text_sample[:3000]}

Look for the table structure and identify ALL column headers in their exact order from left to right.
Common bank statement columns include variations of:
- Date/Transaction Date
- Description/Details/Particulars  
- Reference/Ref No/Transaction ID
- Debit/DR/Withdrawal
- Credit/CR/Deposit
- Balance/Running Balance
- Branch/Location
- Beneficiary/Payee
- etc.

Return ONLY a Python list of the exact header names as they appear in the PDF, in left-to-right order.
Example format: ["Date", "Description", "Reference", "Debit", "Credit", "Balance"]

Respond with just the Python list, nothing else.
"""
    
    response = model.generate_content(prompt)
    headers_text = response.text.strip()
    
    # Try to extract the list from the response
    try:
        # Remove markdown formatting if present
        if "```" in headers_text:
            headers_text = re.search(r"```(?:python)?\s*(\[.*?\])\s*```", headers_text, re.DOTALL)
            if headers_text:
                headers_text = headers_text.group(1)
        
        # Evaluate the Python list
        headers = eval(headers_text) if headers_text.startswith('[') else []
        return headers if isinstance(headers, list) else []
    except:
        print("⚠️ Could not auto-detect headers, using manual input...")
        return []

# ====== STEP 3: Manual header input fallback ======
def get_headers_manually() -> List[str]:
    """Get headers from user input if auto-detection fails"""
    print("\n📋 Please enter the column headers as they appear in your PDF:")
    print("💡 Enter each header separated by commas")
    print("📝 Example: Date, Description, Reference, Debit, Credit, Balance")
    
    headers_input = input("\nEnter headers: ").strip()
    headers = [h.strip() for h in headers_input.split(',') if h.strip()]
    return headers

# ====== STEP 4: Universal Gemini parsing prompt ======
def ask_gemini_to_generate_universal_parser(text_sample: str, headers: List[str]) -> str:
    """Generate parser with universal instructions for any bank statement format"""
    
    prompt = f"""
You are creating a universal bank statement parser for any PDF format.

TEXT SAMPLE:
{text_sample[:4000]}

DETECTED COLUMN HEADERS: {headers}

UNIVERSAL PARSING INSTRUCTIONS:

1. TRANSACTION IDENTIFICATION:
   - Find rows with DATE patterns (DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD, etc.)
   - Dates are typically the primary anchor for identifying transaction rows
   - Skip header rows, summary rows, balance forward rows

2. COLUMN STRUCTURE UNDERSTANDING:
   - This is a TABLE with FIXED COLUMNS, not free-flowing text
   - Each column has specific boundaries - respect these boundaries
   - Multi-line content within a column should be concatenated
   - DO NOT merge content from different columns

3. COMMON PATTERNS TO HANDLE:
   - Date formats: Various formats (DD-MM-YYYY, DD/MM/YYYY, etc.)
   - Amounts: Numbers with decimals (1,234.56) in debit/credit columns
   - References: Alphanumeric codes, transaction IDs
   - Descriptions: Can span multiple lines within the same column
   - Balance: Running balance, often with +/- indicators

4. UNIVERSAL FIELD MAPPING:
   - Map extracted data to the provided headers: {headers}
   - If a field cannot be determined, use empty string ""
   - Preserve original formatting for amounts and dates

5. ROBUST PARSING STRATEGY:
   - Use regex patterns for dates: r'\\b\\d{{1,4}}[-/]\\d{{1,2}}[-/]\\d{{1,4}}\\b'
   - Use positional analysis to separate columns
   - Handle word wrapping within columns
   - Ignore non-transaction rows (totals, headers, footers)

Write a complete Python function `parse_transactions(text: str) -> List[Dict]` that:

IMPLEMENTATION APPROACH:
```python
import re
from typing import List, Dict

def parse_transactions(text: str) -> List[Dict]:
    lines = [line.strip() for line in text.split('\\n') if line.strip()]
    transactions = []
    
    # Date patterns for various formats
    date_patterns = [
        r'\\b\\d{{2}}-\\d{{2}}-\\d{{4}}\\b',  # DD-MM-YYYY
        r'\\b\\d{{2}}/\\d{{2}}/\\d{{4}}\\b',  # DD/MM/YYYY  
        r'\\b\\d{{4}}-\\d{{2}}-\\d{{2}}\\b',  # YYYY-MM-DD
        r'\\b\\d{{1,2}}\s+[A-Za-z]{{3}}\s+\\d{{4}}\\b'  # DD MMM YYYY
    ]
    
    current_transaction_lines = []
    
    for line in lines:
        # Skip summary/header lines
        if any(keyword in line.upper() for keyword in [
            'BALANCE B/F', 'BALANCE C/F', 'CLOSING BALANCE', 'OPENING BALANCE',
            'TOTAL', 'SUBTOTAL', 'SUMMARY', 'ACCOUNT', 'STATEMENT',
            'PAGE', 'CONTINUED'
        ]):
            continue
        
        # Check if line starts a new transaction (contains date)
        is_transaction_start = False
        for pattern in date_patterns:
            if re.search(pattern, line):
                is_transaction_start = True
                break
        
        if is_transaction_start:
            # Process previous transaction
            if current_transaction_lines:
                transaction = parse_single_transaction(current_transaction_lines, {headers})
                if transaction:
                    transactions.append(transaction)
            # Start new transaction
            current_transaction_lines = [line]
        else:
            # Add to current transaction if we have one started
            if current_transaction_lines:
                current_transaction_lines.append(line)
    
    # Process final transaction
    if current_transaction_lines:
        transaction = parse_single_transaction(current_transaction_lines, {headers})
        if transaction:
            transactions.append(transaction)
    
    return transactions

def parse_single_transaction(lines: List[str], headers: List[str]) -> Dict:
    # Implement intelligent column extraction based on:
    # 1. Position analysis
    # 2. Pattern recognition  
    # 3. Field type detection
    # 4. Header mapping
    
    # Return dictionary with all headers as keys
    result = {{header: "" for header in headers}}
    
    # Extract date, amounts, and other fields using universal patterns
    # Map to the provided headers dynamically
    
    return result
```

Complete this implementation with robust field extraction logic that works for any bank statement format.
Map the extracted data to the exact headers: {headers}

Respond ONLY with complete Python code in ```python ``` block.
"""
    
    response = model.generate_content(prompt)
    return response.text

# ====== STEP 5: Execute parser ======
def run_generated_parser(parser_code: str, full_text: str):
    """Execute the AI-generated parser code"""
    code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", parser_code, re.DOTALL)
    if code_match:
        code = code_match.group(1)
    else:
        code = parser_code.strip()

    namespace = {}
    try:
        exec(code, namespace)
    except Exception as e:
        print("❌ Error in generated parser code:", e)
        print("💡 Generated code:")
        print(code)
        raise e

    if "parse_transactions" not in namespace:
        raise ValueError("❌ Function `parse_transactions` not found in generated code.")

    parse_func = namespace["parse_transactions"]
    return parse_func(full_text)

# ====== STEP 6: Universal fallback parser ======
def universal_fallback_parser(text: str, headers: List[str]) -> List[Dict]:
    """Universal fallback parser that works with any header structure"""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    transactions = []
    
    # Universal date patterns
    date_patterns = [
        r'\b\d{2}-\d{2}-\d{4}\b',  # DD-MM-YYYY
        r'\b\d{2}/\d{2}/\d{4}\b',  # DD/MM/YYYY  
        r'\b\d{4}-\d{2}-\d{2}\b',  # YYYY-MM-DD
        r'\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b'  # DD MMM YYYY
    ]
    
    current_transaction_lines = []
    
    for line in lines:
        # Skip summary lines
        skip_keywords = ['BALANCE B/F', 'BALANCE C/F', 'CLOSING', 'OPENING', 'TOTAL', 'SUMMARY']
        if any(keyword in line.upper() for keyword in skip_keywords):
            continue
        
        # Check for date patterns
        has_date = any(re.search(pattern, line) for pattern in date_patterns)
        
        if has_date:
            # Process previous transaction
            if current_transaction_lines:
                transaction = parse_universal_transaction(current_transaction_lines, headers)
                if transaction:
                    transactions.append(transaction)
            current_transaction_lines = [line]
        else:
            if current_transaction_lines:
                current_transaction_lines.append(line)
    
    # Process final transaction
    if current_transaction_lines:
        transaction = parse_universal_transaction(current_transaction_lines, headers)
        if transaction:
            transactions.append(transaction)
    
    return transactions

def parse_universal_transaction(lines: List[str], headers: List[str]) -> Optional[Dict]:
    """Parse a single transaction with universal logic"""
    if not lines:
        return None
    
    # Initialize result with all headers
    result = {header: "" for header in headers}
    
    # Combine all lines
    full_text = ' '.join(lines)
    
    # Extract date (first priority)
    date_patterns = [
        r'\b(\d{2}-\d{2}-\d{4})\b',
        r'\b(\d{2}/\d{2}/\d{4})\b',
        r'\b(\d{4}-\d{2}-\d{2})\b',
        r'\b(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b'
    ]
    
    date_value = ""
    for pattern in date_patterns:
        match = re.search(pattern, full_text)
        if match:
            date_value = match.group(1)
            break
    
    # Map date to appropriate header
    date_headers = ['date', 'transaction date', 'trans date', 'dt']
    for header in headers:
        if any(dh in header.lower() for dh in date_headers):
            result[header] = date_value
            break
    
    # Extract amounts
    amount_pattern = r'\b(\d{1,3}(?:,\d{3})*\.\d{2})\b'
    amounts = re.findall(amount_pattern, full_text)
    
    # Extract balance (usually last amount)
    balance_headers = ['balance', 'running balance', 'bal']
    if amounts:
        for header in headers:
            if any(bh in header.lower() for bh in balance_headers):
                result[header] = amounts[-1]  # Last amount is usually balance
                amounts = amounts[:-1]  # Remove balance from amounts
                break
    
    # Map remaining amounts to debit/credit
    if amounts:
        debit_headers = ['debit', 'dr', 'withdrawal', 'out']
        credit_headers = ['credit', 'cr', 'deposit', 'in']
        
        for header in headers:
            if any(dh in header.lower() for dh in debit_headers) and amounts:
                result[header] = amounts.pop(0)
            elif any(ch in header.lower() for ch in credit_headers) and amounts:
                result[header] = amounts.pop(0)
    
    # Basic description mapping (remaining text)
    desc_headers = ['description', 'particulars', 'details', 'narration']
    for header in headers:
        if any(dh in header.lower() for dh in desc_headers):
            # Remove amounts and dates from description
            clean_text = full_text
            for amount in re.findall(amount_pattern, full_text):
                clean_text = clean_text.replace(amount, '')
            for pattern in date_patterns:
                clean_text = re.sub(pattern, '', clean_text)
            result[header] = ' '.join(clean_text.split())
            break
    
    return result if date_value else None

# ====== MAIN PIPELINE ======
def main():
    pdf_path = input("Enter PDF path: ").strip()
    output_json = "output_transactions.json"

    print("🔍 Extracting sample text...")
    sample_text = extract_sample_text_with_layout(pdf_path)

    print("🧠 Auto-detecting table headers...")
    headers = detect_table_headers(sample_text)
    
    if not headers:
        print("❌ Auto-detection failed")
        headers = get_headers_manually()
    
    if not headers:
        print("❌ No headers provided. Exiting...")
        return
    
    print(f"✅ Using Headers: {headers}")

    print("🤖 Generating universal parser...")
    parser_code = ask_gemini_to_generate_universal_parser(sample_text, headers)

    # Save generated parser
    with open("generated_universal_parser.py", "w", encoding="utf-8") as f:
        f.write(parser_code)
    print("💾 Generated parser saved to generated_universal_parser.py")

    try:
        print("⚙️ Executing AI-generated parser...")
        full_text = extract_sample_text_with_layout(pdf_path, max_pages=20)
        parsed_data = run_generated_parser(parser_code, full_text)
    except Exception as e:
        print(f"⚠️ AI parser failed: {e}")
        print("🔄 Using universal fallback parser...")
        full_text = extract_sample_text_with_layout(pdf_path, max_pages=20)
        parsed_data = universal_fallback_parser(full_text, headers)

    print(f"💾 Saving parsed data to {output_json}")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2)

    print("✅ Extraction Complete!")
    print(f"📊 Extracted {len(parsed_data)} transactions")
    
    # Show preview
    if parsed_data:
        print(f"\n📋 Preview (using headers: {headers}):")
        print(json.dumps(parsed_data[0], indent=2))

# ====== ENTRY POINT ======
if __name__ == "__main__":
    main()