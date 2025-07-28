import pdfplumber
import google.generativeai as genai
import json
import re
import os

# ====== CONFIGURE GEMINI ======
genai.configure(api_key="AIzaSyBtesPBXTGCKqV1ySFnVCx5pkIaSbdYcwg")
model = genai.GenerativeModel("models/gemini-2.5-flash")

# ====== STEP 1: Extract text from first N pages ======
def extract_sample_text(pdf_path, max_pages=5):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:max_pages]:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    return text.strip()

# ====== STEP 2: Ask Gemini to generate parser code ======
def ask_gemini_to_generate_parser(text_sample, headers):
    prompt = f"""
You are a Python developer writing a parser for a bank statement PDF with a specific table structure.

Here is some extracted text from the PDF:
{text_sample[:4000]}

The table has these exact columns in order: {headers}

CRITICAL PARSING RULES:
1. Each transaction starts with a DATE in format DD-MM-YYYY (like "01-03-2025", "02-03-2025")
2. The table structure is COLUMNAR - data is arranged in vertical columns, NOT continuous text
3. After the date, the same row contains: Branch Description, then amounts, then balance
4. Multi-line descriptions belong to the SAME transaction and should be concatenated with spaces
5. DO NOT merge data from different columns - respect column boundaries
6. Empty cells should be represented as empty strings ""

COLUMN STRUCTURE ANALYSIS:
- Date: Always starts the row (DD-MM-YYYY format)
- Branch Description: Follows date (like "980 DUITNOW", "098 RHB")  
- Sender's/Beneficiary's Name: Names like "KOGILARASI", "SANJAY KUMAR", "MOHAMMAD TAJUL"
- Reference 1: Reference codes and descriptions (like "RHBQR0196", "DuitQR Mcht")
- Reference 2: Additional references and codes (like "20250301MB", "BEMYKL030")
- RefNum: Transaction reference numbers (like "00007542", "00004964")
- Amount (DR): Debit amounts (if transaction is a debit)
- Amount (CR): Credit amounts (if transaction is a credit) 
- Balance: Running balance (like "2,326.27+", "2,421.27+")

Write a complete Python function named `parse_transactions(text: str) -> List[Dict]` that:
- Uses regex to find date patterns as transaction anchors: r'\\b\\d{{2}}-\\d{{2}}-\\d{{4}}\\b'
- For each transaction, carefully extracts data respecting column positions
- Handles multi-line descriptions by combining continuation lines
- Maps extracted data to the exact headers: {headers}
- Ignores summary lines like 'Balance B/F', 'Closing Balance', 'Deposit Account Summary'
- Returns clean, properly structured data

EXAMPLE EXPECTED OUTPUT FORMAT:
[
  {{
    "Date": "01-03-2025",
    "Branch Description": "980 DUITNOW QR POS CR",
    "Sender's / Beneficiary's Name": "KOGILARASI A/P HARIK",
    "Reference 1 / Recipient's Reference": "RHBQR0196 22/ DuitQR Mcht Transfer",
    "Reference 2 / Other Payment Details": "20250301MB BEMYKL030 OQR7608135 4",
    "RefNum": "00007542",
    "Amount (DR)": "",
    "Amount (CR)": "30.00",
    "Balance": "2,326.27+"
  }}
]

Respond ONLY with the Python code inside one ```python ... ``` code block. Do NOT add any explanation.
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


# ====== MAIN PIPELINE ======
def main():
    pdf_path = input("Enter PDF path: ").strip()
    output_json = "output_transactions.json"

    print("🔍 Extracting sample text...")
    sample_text = extract_sample_text(pdf_path)

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

    print("🧠 Asking Gemini to generate parser code...")
    parser_code = ask_gemini_to_generate_parser(sample_text, headers)

    # Optional: Save the generated parser
    with open("generated_parser.py", "w", encoding="utf-8") as f:
        f.write(parser_code)
    print("💾 Generated parser saved to generated_parser.py")

    print("⚙️ Executing the parser...")
    full_text = extract_sample_text(pdf_path, max_pages=20)
    parsed_data = run_generated_parser(parser_code, full_text)

    print(f"💾 Saving parsed data to {output_json}")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2)

    print("✅ Extraction Complete.")
    print(f"📊 Extracted {len(parsed_data)} transactions")

# ====== ENTRY POINT ======
if __name__ == "__main__":
    main()