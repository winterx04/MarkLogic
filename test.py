import fitz  # PyMuPDF
import pandas as pd
import re
from datetime import datetime

def extract_trademarks_structured(pdf_path, output_csv):
    """
    Structured extraction with proper column assignment
    """
    
    # Open PDF
    doc = fitz.open(pdf_path)
    
    # Collect all text with page info
    all_entries = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        
        # Process each page
        page_entries = extract_from_page(text, page_num)
        all_entries.extend(page_entries)
    
    doc.close()
    
    print(f"Total entries found: {len(all_entries)}")
    
    # Parse each entry
    parsed_data = []
    
    for entry in all_entries:
        parsed = parse_trademark_entry(entry)
        if parsed and parsed.get('Serial Number'):
            parsed_data.append(parsed)
    
    # Create DataFrame
    df = pd.DataFrame(parsed_data)
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['Serial Number'], keep='first')
    
    print(f"Successfully parsed {len(df)} trademark entries")
    
    # Save to CSV
    df.to_csv(output_csv, index=False, encoding='utf-8')
    
    # Show sample
    if len(df) > 0:
        print("\nSample of extracted data (first 5 entries):")
        print(df[['Class Index', 'Serial Number', 'Application Date', 
                  'International Priority Date', 'Company Name']].head().to_string())
    
    return df

def extract_from_page(page_text, page_num):
    """Extract trademark entries from a single page"""
    
    entries = []
    lines = page_text.split('\n')
    
    current_entry = []
    collecting = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        if not line:
            continue
            
        # Check if this line starts a new trademark entry
        is_start = False
        
        # Pattern 1: Line contains CLASS and TM (e.g., "CLASS:3 TM2025012263")
        if re.search(r'CLASS\s*[:]?\s*\d+.*TM\d', line, re.IGNORECASE):
            is_start = True
            
        # Pattern 2: Line starts with TM number (e.g., "TM2025012263 18 April 2025")
        elif re.match(r'^TM\d{8,}\s+\d', line):
            is_start = True
            
        # Pattern 3: Line has # followed by trademark name (e.g., "# Super Value Pack")
        elif line.startswith('#') and len(line) > 2:
            is_start = True
            
        # If starting new entry and we have a current entry, save it
        if is_start and current_entry:
            entries.append('\n'.join(current_entry))
            current_entry = [line]
        elif is_start:
            current_entry = [line]
            collecting = True
        elif collecting:
            # Check if next line starts a new entry
            if i < len(lines) - 1:
                next_line = lines[i + 1].strip()
                next_is_start = (
                    re.search(r'CLASS\s*[:]?\s*\d+.*TM\d', next_line, re.IGNORECASE) or
                    re.match(r'^TM\d{8,}\s+\d', next_line) or
                    (next_line.startswith('#') and len(next_line) > 2)
                )
                
                if next_is_start:
                    entries.append('\n'.join(current_entry))
                    current_entry = []
                    collecting = False
                else:
                    current_entry.append(line)
            else:
                current_entry.append(line)
    
    # Don't forget the last entry
    if current_entry:
        entries.append('\n'.join(current_entry))
    
    return entries

def parse_trademark_entry(entry_text):
    """Parse a single trademark entry with correct column assignment"""
    
    lines = [line.strip() for line in entry_text.split('\n') if line.strip()]
    
    result = {
        'Class Index': '',
        'Serial Number': '',
        'Application Date': '',
        'International Priority Date': '',
        'By Consent Trademark Numbers': '',
        'Description': '',
        'Company Name': '',
        'Agent Details': ''
    }
    
    # 1. Extract CLASS INDEX (always at the beginning)
    for line in lines:
        class_match = re.search(r'CLASS\s*[:]?\s*([\d,\s]+)', line, re.IGNORECASE)
        if class_match:
            result['Class Index'] = class_match.group(1).strip().replace(' ', '')
            break
    
    # 2. Extract SERIAL NUMBER (TM...) and APPLICATION DATE
    for i, line in enumerate(lines):
        tm_match = re.search(r'(TM\d{8,})', line)
        if tm_match:
            result['Serial Number'] = tm_match.group(1)
            
            # Look for application date (usually on same line after TM)
            # Pattern: TM2025012263 18 April 2025
            date_pattern = r'TM\d{8,}\s+(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|[A-Za-z]{3,})\.?\s+\d{4})'
            date_match = re.search(date_pattern, line)
            
            if date_match:
                result['Application Date'] = date_match.group(1)
            else:
                # Check next line for date
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', next_line)
                    if date_match:
                        result['Application Date'] = date_match.group(1)
            break
    
    # 3. Extract INTERNATIONAL PRIORITY DATE (only if present)
    # This appears as: "International priority date claimed: 11 September 2018, Japan"
    for line in lines:
        if 'International priority date claimed' in line:
            # Extract the entire date and country
            match = re.search(r'International priority date claimed\s*[:]?\s*(.*?)(?=\s*\n|\.|$)', line, re.IGNORECASE)
            if match:
                result['International Priority Date'] = match.group(1).strip()
            break
    
    # 4. Extract BY CONSENT TRADEMARK NUMBERS
    for line in lines:
        if 'By consent of the registered proprietor' in line:
            # Find numbers after "no:"
            match = re.search(r'no:\s*([\d,\s]+)', line)
            if match:
                result['By Consent Trademark Numbers'] = match.group(1).strip()
            break
    
    # 5. Extract COMPANY NAME
    # Look for the line that ends with ; and contains address info
    for i, line in enumerate(lines):
        # Skip if it's agent line or contains TM/CLASS
        if ('AGENT' in line.upper() or 
            'CLASS' in line.upper() or 
            'TM' in line or
            line.startswith('#')):
            continue
        
        # Company name ends with ; and has reasonable length
        if line.endswith(';') and len(line) > 10:
            # Additional check: should contain location indicators
            location_indicators = ['MALAYSIA', 'SINGAPORE', 'JAPAN', 'USA', 'CHINA', 'KOREA', 'TAIWAN', 
                                  'SDN', 'LTD', 'INC', 'CORP', 'CO.', 'PTE', 'UNIVERSITI', 'JALAN', 'ROAD']
            
            if any(indicator in line.upper() for indicator in location_indicators):
                result['Company Name'] = line
                break
    
    # 6. Extract AGENT DETAILS
    for i, line in enumerate(lines):
        if 'AGENT' in line.upper() and (':' in line or ' :' in line):
            # Get the agent line and possibly following lines
            agent_text = line
            
            # Look for continuation
            j = i + 1
            while j < len(lines) and j < i + 4:  # Max 3 continuation lines
                next_line = lines[j]
                # Stop if next line looks like new data
                if (len(next_line.split()) < 3 or  # Very short line
                    'CLASS' in next_line.upper() or
                    'TM' in next_line or
                    next_line.endswith(';')):
                    break
                agent_text += ' ' + next_line
                j += 1
            
            # Clean up
            agent_text = re.sub(r'^AGENT\s*[:]?\s*', '', agent_text, flags=re.IGNORECASE)
            result['Agent Details'] = agent_text.strip()
            break
    
    # 7. Extract DESCRIPTION (goods/services)
    # This is text between trademark info and company/agent
    description_lines = []
    collecting = False
    passed_serial = False
    
    for line in lines:
        # Skip metadata lines
        if ('CLASS' in line.upper() or
            'TM' in line or
            line == result['Company Name'] or
            'AGENT' in line.upper() or
            'International priority date claimed' in line or
            'By consent of the registered proprietor' in line or
            'Registration of this trademark' in line or
            'Advertisement of a series' in line or
            'The trademark is limited' in line or
            'Mark translation:' in line or
            'Mark transliteration:' in line):
            
            if 'TM' in line:
                passed_serial = True
            continue
        
        # Start collecting after we've passed the TM line
        if passed_serial and not collecting and line.strip():
            collecting = True
        
        if collecting and line.strip():
            # Stop if we hit company name
            if line == result['Company Name'] or ('AGENT' in line.upper() and ':' in line):
                break
            description_lines.append(line.strip())
    
    result['Description'] = ' '.join(description_lines)
    
    # Clean up description
    if result['Description']:
        # Remove common prefixes and clean up
        result['Description'] = re.sub(r'^\d+\s+\w+\s+\d{4}\s+', '', result['Description'])
        result['Description'] = re.sub(r'\s+', ' ', result['Description'])
    
    return result

# Alternative: Direct field-by-field extraction
def extract_fields_directly(pdf_path, output_csv):
    """Extract fields directly without complex line processing"""
    
    doc = fitz.open(pdf_path)
    text = ""
    
    for page in doc:
        text += page.get_text("text") + "\n"
    
    doc.close()
    
    # Clean up text
    text = re.sub(r'\n\s*\n+', '\n', text)
    
    # Find all TM entries using a simpler approach
    entries = []
    
    # Look for TM patterns with their context
    tm_pattern = r'(TM\d{8,})\s+(\d{1,2}\s+\w+\s+\d{4})'
    tm_matches = list(re.finditer(tm_pattern, text))
    
    for i, match in enumerate(tm_matches):
        tm_num = match.group(1)
        app_date = match.group(2)
        
        # Get context around this TM
        start_pos = max(0, match.start() - 500)
        end_pos = match.end() + 500 if i < len(tm_matches) - 1 else match.end() + 1000
        
        context = text[start_pos:end_pos]
        
        # Extract fields from context
        entry_data = extract_from_context(tm_num, app_date, context)
        if entry_data:
            entries.append(entry_data)
    
    # Create DataFrame
    df = pd.DataFrame(entries)
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['Serial Number'], keep='first')
    
    print(f"Direct extraction found {len(df)} entries")
    
    # Save to CSV
    df.to_csv(output_csv, index=False, encoding='utf-8')
    
    return df

def extract_from_context(tm_num, app_date, context):
    """Extract all fields from context around TM number"""
    
    result = {
        'Serial Number': tm_num,
        'Application Date': app_date,
        'Class Index': '',
        'International Priority Date': '',
        'By Consent Trademark Numbers': '',
        'Description': '',
        'Company Name': '',
        'Agent Details': ''
    }
    
    # Extract CLASS (look backward)
    class_match = re.search(r'CLASS\s*[:]?\s*([\d,\s]+)', context[:200], re.IGNORECASE)
    if class_match:
        result['Class Index'] = class_match.group(1).strip().replace(' ', '')
    
    # Extract International Priority Date
    intl_match = re.search(r'International priority date claimed\s*[:]?\s*(.*?)(?=\s*\n|\.|;)', context, re.IGNORECASE)
    if intl_match:
        result['International Priority Date'] = intl_match.group(1).strip()
    
    # Extract By Consent Numbers
    consent_match = re.search(r'By consent of the registered proprietor.*?no:\s*([\d,\s]+)', context, re.IGNORECASE | re.DOTALL)
    if consent_match:
        result['By Consent Trademark Numbers'] = consent_match.group(1).strip()
    
    # Extract Company Name (look for ; after TM)
    tm_pos = context.find(tm_num)
    if tm_pos > 0:
        after_tm = context[tm_pos + len(tm_num):]
        
        # Find company name pattern
        company_match = re.search(r'([A-Z][^;\n]{20,};)', after_tm[:500])
        if company_match:
            result['Company Name'] = company_match.group(1).strip()
    
    # Extract Agent Details
    agent_match = re.search(r'AGENT\s*[:]?\s*(.*?)(?=\n\s*\n|\nCLASS\s*[:]|\nTM\d|$)', context, re.IGNORECASE | re.DOTALL)
    if agent_match:
        result['Agent Details'] = agent_match.group(1).strip()
    
    # Extract Description (text between date and company/agent)
    # This is simplified - actual implementation would be more complex
    date_pos = context.find(app_date)
    if date_pos > 0 and result['Company Name']:
        company_pos = context.find(result['Company Name'])
        if company_pos > date_pos:
            description = context[date_pos + len(app_date):company_pos]
            # Clean up
            description = re.sub(r'Registration of this trademark.*?\.', '', description, flags=re.DOTALL)
            description = re.sub(r'\s+', ' ', description).strip()
            result['Description'] = description[:500]  # Limit length
    
    return result

def main():
    pdf_file = "C:\\xampp\\htdocs\\MarkLogic\\index.cfm.pdf"
    
    print("=" * 80)
    print("CORRECTED TRADEMARK EXTRACTOR")
    print("=" * 80)
    
    # Method 1: Structured extraction (recommended)
    print("\nMethod 1: Structured extraction with correct column assignment...")
    try:
        df1 = extract_trademarks_structured(pdf_file, 'trademarks_corrected.csv')
        
        # Show specific columns to verify correctness
        print("\nVerifying column assignment:")
        print("-" * 80)
        
        # Find entries with international priority dates to verify
        intl_entries = df1[df1['International Priority Date'] != '']
        
        if not intl_entries.empty:
            print("\nEntries with International Priority Dates (showing correct column assignment):")
            for idx, row in intl_entries.head(3).iterrows():
                print(f"\nEntry {idx}:")
                print(f"  Serial: {row['Serial Number']}")
                print(f"  App Date: {row['Application Date']}")
                print(f"  Intl Priority: {row['International Priority Date']}")
                print(f"  Company: {row['Company Name'][:50]}...")
        else:
            print("No entries with international priority dates found")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        df1 = pd.DataFrame()
    
    print("\n" + "=" * 80)
    
    # Method 2: Direct extraction
    print("\nMethod 2: Direct field extraction...")
    try:
        df2 = extract_fields_directly(pdf_file, 'trademarks_direct.csv')
    except Exception as e:
        print(f"Error: {e}")
        df2 = pd.DataFrame()
    
    # Summary
    print("\n" + "=" * 80)
    print("EXTRACTION SUMMARY")
    print("=" * 80)
    print(f"Structured extraction: {len(df1) if not df1.empty else 0} entries")
    print(f"Direct extraction: {len(df2) if not df2.empty else 0} entries")
    
    # Show sample data
    if not df1.empty:
        print("\nSample from structured extraction (with all columns):")
        sample_cols = ['Class Index', 'Serial Number', 'Application Date', 
                      'International Priority Date', 'Company Name', 'Agent Details']
        print(df1[sample_cols].head(5).to_string())

if __name__ == "__main__":
    main()