import fitz  # PyMuPDF
import pandas as pd
import re

def extract_trademarks_line_by_line(pdf_path, output_csv):
    """
    Extract trademarks by processing the PDF line-by-line
    This handles the actual structure better than complex regex patterns
    """
    
    # Open PDF
    doc = fitz.open(pdf_path)
    
    # Collect all text lines
    all_lines = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        lines = text.split('\n')
        all_lines.extend([line.strip() for line in lines if line.strip()])
    
    doc.close()
    
    print(f"Total lines extracted: {len(all_lines)}")
    
    # Process lines to find trademark entries
    entries = []
    current_entry = []
    collecting = False
    
    for i, line in enumerate(all_lines):
        # Check if this line starts a new trademark entry
        is_new_entry = False
        
        # Pattern 1: Starts with CLASS: and has TM number
        if re.match(r'^CLASS\s*[:]?\s*\d+', line, re.IGNORECASE) and 'TM' in line:
            is_new_entry = True
        
        # Pattern 2: Has TM number and looks like start of entry
        elif re.search(r'^TM\d{8,}', line):
            # Check if previous lines suggest this is start of entry
            if i > 0 and ('CLASS' in all_lines[i-1].upper() or 'GENERAL INFORMATION' in all_lines[i-1]):
                is_new_entry = True
        
        # Pattern 3: Starts with # and has text (for entries like "# Super Value Pack")
        elif line.startswith('#') and len(line) > 2:
            is_new_entry = True
        
        # If we find a new entry, save the current one and start new
        if is_new_entry and current_entry:
            entries.append(current_entry)
            current_entry = [line]
        elif is_new_entry:
            current_entry = [line]
            collecting = True
        elif collecting:
            # Stop collecting when we hit certain markers
            if (i < len(all_lines)-1 and 
                re.match(r'^CLASS\s*[:]?\s*\d+', all_lines[i+1], re.IGNORECASE) and 
                'TM' in all_lines[i+1]):
                # Next line starts new entry
                entries.append(current_entry)
                current_entry = []
                collecting = False
            elif '=====' in line or 'Page' in line and i > 0 and 'Page' in all_lines[i-1]:
                # Page marker or separator
                if current_entry:
                    entries.append(current_entry)
                    current_entry = []
                    collecting = False
            else:
                current_entry.append(line)
    
    # Don't forget the last entry
    if current_entry:
        entries.append(current_entry)
    
    print(f"Found {len(entries)} potential trademark entries")
    
    # Parse each entry
    parsed_data = []
    
    for entry_idx, entry_lines in enumerate(entries):
        entry_text = '\n'.join(entry_lines)
        
        # Skip if too short or doesn't have TM number
        if len(entry_text) < 20 or 'TM' not in entry_text:
            continue
        
        try:
            parsed = parse_single_entry(entry_lines)
            if parsed and parsed.get('Serial Number'):
                parsed_data.append(parsed)
        except Exception as e:
            print(f"Error parsing entry {entry_idx}: {str(e)[:50]}")
            continue
    
    # Create DataFrame
    df = pd.DataFrame(parsed_data)
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['Serial Number'], keep='first')
    
    print(f"Successfully parsed {len(df)} trademark entries")
    
    # Save to CSV
    df.to_csv(output_csv, index=False, encoding='utf-8')
    
    # Show sample
    if len(df) > 0:
        print("\nSample of extracted data:")
        print(df.head(10).to_string())
    
    return df

def parse_single_entry(entry_lines):
    """Parse a single trademark entry from its lines"""
    
    entry_text = '\n'.join(entry_lines)
    
    # Initialize result
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
    
    # 1. Extract CLASS
    for line in entry_lines:
        # Look for CLASS pattern (can be "CLASS:3", "CLASS : 3", etc.)
        class_match = re.search(r'CLASS\s*[:]?\s*([\d,\s]+)', line, re.IGNORECASE)
        if class_match:
            result['Class Index'] = class_match.group(1).strip()
            break
    
    # 2. Extract Serial Number (TM number)
    for line in entry_lines:
        tm_match = re.search(r'(TM\d{8,})', line)
        if tm_match:
            result['Serial Number'] = tm_match.group(1)
            
            # Try to extract date from same line or next line
            date_match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})', line)
            if date_match:
                result['Application Date'] = date_match.group(1)
            break
    
    # If no date found with TM, search all lines
    if not result['Application Date']:
        for line in entry_lines:
            date_match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})', line)
            if date_match and 'International' not in line:
                result['Application Date'] = date_match.group(1)
                break
    
    # 3. Extract International Priority Date
    for line in entry_lines:
        if 'International priority date claimed' in line:
            # Look for date pattern after the keyword
            date_match = re.search(r'International priority date claimed\s*[:]?\s*(\d{1,2}\s+\w+\s+\d{4},.*?)(?=\s|$)', line)
            if date_match:
                result['International Priority Date'] = date_match.group(1).strip()
            break
    
    # 4. Extract By Consent Trademark Numbers
    for line in entry_lines:
        if 'By consent of the registered proprietor' in line:
            # Look for numbers after "no:"
            num_match = re.search(r'no:\s*([\d,\s]+)', line)
            if num_match:
                result['By Consent Trademark Numbers'] = num_match.group(1).strip()
            break
    
    # 5. Extract Company Name
    # Company name is usually a long line ending with ; and contains MALAYSIA or similar
    for i, line in enumerate(entry_lines):
        # Look for company indicators
        if (';' in line and 
            len(line) > 20 and 
            'AGENT' not in line.upper() and 
            'CLASS' not in line.upper() and 
            'TM' not in line):
            
            # Check if it looks like a company address
            if any(keyword in line.upper() for keyword in ['SDN', 'LTD', 'INC', 'CORP', 'CO.', 'PTE', 'MALAYSIA', 'SINGAPORE', 'JAPAN', 'USA', 'UNIVERSITI']):
                result['Company Name'] = line.strip()
                break
    
    # 6. Extract Agent Details
    for i, line in enumerate(entry_lines):
        if 'AGENT' in line.upper() and (':' in line or ' :' in line):
            # Found agent line
            agent_text = line
            
            # Check if agent info continues on next lines
            j = i + 1
            while j < len(entry_lines):
                next_line = entry_lines[j]
                # Stop if next line looks like end of agent info
                if (len(next_line) > 100 or 
                    'CLASS' in next_line.upper() or 
                    'TM' in next_line or 
                    j > i + 3):
                    break
                agent_text += ' ' + next_line
                j += 1
            
            # Clean up
            agent_text = re.sub(r'^AGENT\s*[:]?\s*', '', agent_text, flags=re.IGNORECASE)
            result['Agent Details'] = agent_text.strip()
            break
    
    # 7. Extract Description
    # Find the text between TM/date and Company/Agent
    description_lines = []
    found_tm = False
    
    for line in entry_lines:
        # Skip if it's a metadata line
        if ('CLASS' in line.upper() or 
            'TM' in line or 
            line == result['Company Name'] or 
            'AGENT' in line.upper() or
            'Registration of this trademark' in line or
            'Advertisement of a series' in line or
            'The trademark is limited' in line or
            'Mark translation:' in line or
            'Mark transliteration:' in line):
            
            if 'TM' in line:
                found_tm = True
            continue
        
        # Start collecting after TM is found
        if found_tm and line.strip():
            description_lines.append(line.strip())
        
        # Stop if we hit company or agent
        if line == result['Company Name'] or ('AGENT' in line.upper() and ':' in line):
            break
    
    result['Description'] = ' '.join(description_lines)
    
    return result

# Alternative: Even simpler approach focusing on key markers
def simple_bulk_extract(pdf_path, output_csv):
    """Super simple extraction - just find key patterns"""
    
    doc = fitz.open(pdf_path)
    all_text = ""
    
    for page in doc:
        all_text += page.get_text("text") + "\n\n"
    
    doc.close()
    
    # Find all TM numbers and their context
    data = []
    
    # Split by TM numbers
    sections = re.split(r'(TM\d{8,})', all_text)
    
    for i in range(1, len(sections), 2):
        if i < len(sections):
            tm_number = sections[i]
            context = sections[i-1][-500:] + " " + tm_number + " " + sections[i+1][:500]
            
            # Extract basic info
            entry_data = extract_basic_info(tm_number, context)
            if entry_data:
                data.append(entry_data)
    
    df = pd.DataFrame(data)
    df.to_csv(output_csv, index=False, encoding='utf-8')
    print(f"Simple extraction found {len(df)} entries")
    return df

def extract_basic_info(tm_number, context):
    """Extract basic info from context around TM number"""
    
    result = {
        'Serial Number': tm_number,
        'Class Index': '',
        'Application Date': '',
        'Company Name': '',
        'Agent Details': ''
    }
    
    # Extract class (look backward in context)
    class_match = re.search(r'CLASS\s*[:]?\s*([\d,\s]+)', context, re.IGNORECASE)
    if class_match:
        result['Class Index'] = class_match.group(1).strip()
    
    # Extract date (look near TM number)
    date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', context[context.find(tm_number):context.find(tm_number)+100])
    if date_match:
        result['Application Date'] = date_match.group(1)
    
    # Extract company (look for ; after TM)
    tm_pos = context.find(tm_number)
    if tm_pos > 0:
        # Look for company name after TM
        after_tm = context[tm_pos + len(tm_number):]
        
        # Find first ; that looks like company
        lines = after_tm.split('\n')
        for line in lines:
            if ';' in line and len(line) > 10 and 'AGENT' not in line.upper():
                result['Company Name'] = line.strip()
                break
    
    # Extract agent
    agent_match = re.search(r'AGENT\s*[:]?\s*(.*?)(?=\n\n|\n\s*\n|$)', context, re.IGNORECASE | re.DOTALL)
    if agent_match:
        result['Agent Details'] = agent_match.group(1).strip()
    
    return result

# Main function to try both methods
def main():
    pdf_file = "C:\\xampp\\htdocs\\MarkLogic\\index.cfm.pdf"
    
    print("=" * 80)
    print("IMPROVED TRADEMARK EXTRACTOR")
    print("=" * 80)
    
    # Method 1: Line-by-line (more accurate)
    print("\nMethod 1: Line-by-line extraction (recommended)...")
    try:
        df1 = extract_trademarks_line_by_line(pdf_file, 'trademarks_accurate.csv')
        print(f"✓ Extracted {len(df1)} entries")
    except Exception as e:
        print(f"✗ Error: {e}")
        df1 = pd.DataFrame()
    
    print("\n" + "=" * 80)
    
    # Method 2: Simple bulk extraction
    print("\nMethod 2: Simple bulk extraction...")
    try:
        df2 = simple_bulk_extract(pdf_file, 'trademarks_simple.csv')
        print(f"✓ Extracted {len(df2)} entries")
    except Exception as e:
        print(f"✗ Error: {e}")
        df2 = pd.DataFrame()
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Method 1 (Accurate): {len(df1) if not df1.empty else 0} entries")
    print(f"Method 2 (Simple): {len(df2) if not df2.empty else 0} entries")
    
    # If both failed, try a direct approach
    if (df1.empty or len(df1) < 10) and (df2.empty or len(df2) < 10):
        print("\nTrying direct approach...")
        df3 = direct_extraction(pdf_file)
        if not df3.empty:
            df3.to_csv('trademarks_direct.csv', index=False, encoding='utf-8')
            print(f"Direct approach found {len(df3)} entries")

def direct_extraction(pdf_path):
    """Direct extraction without complex processing"""
    doc = fitz.open(pdf_path)
    text = ""
    
    for page in doc:
        text += page.get_text("text") + "\n"
    
    doc.close()
    
    # Find all TM patterns and extract simple info
    pattern = r'(CLASS\s*[:]?\s*[\d,\s]+.*?TM\d{8,}.*?(?:\n.*?)*?AGENT\s*[:]?\s*.*?(?=\n\s*\n|CLASS\s*[:]|$))'
    
    matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
    
    data = []
    for match in matches:
        entry = extract_from_match(match)
        if entry:
            data.append(entry)
    
    return pd.DataFrame(data)

def extract_from_match(match_text):
    """Extract from a matched text block"""
    lines = match_text.split('\n')
    
    result = {
        'Class Index': '',
        'Serial Number': '',
        'Application Date': '',
        'Company Name': '',
        'Agent Details': ''
    }
    
    # Very simple extraction
    for line in lines:
        # Class
        if 'CLASS' in line.upper() and not result['Class Index']:
            class_match = re.search(r'CLASS\s*[:]?\s*([\d,\s]+)', line, re.IGNORECASE)
            if class_match:
                result['Class Index'] = class_match.group(1).strip()
        
        # TM Number
        if 'TM' in line and not result['Serial Number']:
            tm_match = re.search(r'(TM\d{8,})', line)
            if tm_match:
                result['Serial Number'] = tm_match.group(1)
        
        # Company (line with ;)
        if ';' in line and not result['Company Name'] and 'AGENT' not in line.upper():
            result['Company Name'] = line.strip()
        
        # Agent
        if 'AGENT' in line.upper() and not result['Agent Details']:
            result['Agent Details'] = line.strip()
    
    return result

if __name__ == "__main__":
    main()