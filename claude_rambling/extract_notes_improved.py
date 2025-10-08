#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import zipfile
import sys
import re
from datetime import datetime

def extract_text_from_note(note_file_path):
    """Extract readable text from a Samsung Notes .note file"""
    try:
        with open(note_file_path, 'rb') as f:
            content = f.read()

        # Try to find and extract UTF-16 encoded text
        text_content = []

        # Look for null-separated patterns (UTF-16)
        i = 0
        while i < len(content) - 1:
            # Skip binary sections (look for ASCII text patterns)
            if content[i] == 0 and i + 1 < len(content) and content[i+1] >= 32 and content[i+1] <= 126:
                # Found start of UTF-16 text
                text_chars = []
                j = i + 1
                while j < len(content) - 1:
                    if content[j] >= 32 and content[j] <= 126 and content[j+1] == 0:
                        text_chars.append(chr(content[j]))
                        j += 2
                    else:
                        break

                if len(text_chars) > 1:  # Only add if meaningful text
                    text_content.append(''.join(text_chars))
                i = j
            else:
                i += 1

        # Also try simple ASCII extraction as fallback
        ascii_text = ''.join([chr(b) for b in content if 32 <= b <= 126])

        # Combine and clean
        all_text = ' '.join(text_content) if text_content else ascii_text

        # Clean up the text
        cleaned_text = re.sub(r'\s+', ' ', all_text).strip()

        return cleaned_text if cleaned_text else None

    except Exception as e:
        print(f"Error extracting text from {note_file_path}: {e}")
        return None

def extract_filename_info(filename):
    """Extract date and title from filename"""
    # Expected format: "Title_YYMMDD_HHMMSS.note"
    basename = os.path.splitext(os.path.basename(filename))[0]

    # Try to extract date/time from filename
    date_match = re.search(r'_(\d{6})_(\d{6})$', basename)
    if date_match:
        date_str = date_match.group(1)
        time_str = date_match.group(2)
        title = basename[:date_match.start()].replace('_', ' ')

        # Format date/time
        try:
            year = "20" + date_str[0:2]
            month = date_str[2:4]
            day = date_str[4:6]
            hour = time_str[0:2]
            minute = time_str[2:4]
            second = time_str[4:6]

            formatted_datetime = f"{year}-{month}-{day} {hour}:{minute}:{second}"
            return title, formatted_datetime
        except:
            return basename, "Unknown date"
    else:
        return basename, "Unknown date"

def process_all_notes():
    """Process all note files and print them in readable format"""
    note_folder = "notePnote"

    if not os.path.exists(note_folder):
        print(f"Error: {note_folder} folder not found")
        return

    note_files = [f for f in os.listdir(note_folder) if f.endswith('.note')]

    if not note_files:
        print(f"No .note files found in {note_folder}")
        return

    print("=" * 80)
    print("SAMSUNG NOTES CONTENT")
    print("=" * 80)
    print(f"Found {len(note_files)} note(s)\n")

    for i, note_file in enumerate(sorted(note_files), 1):
        note_path = os.path.join(note_folder, note_file)
        title, date_time = extract_filename_info(note_file)

        print(f"NOTE {i}: {title}")
        print(f"Date: {date_time}")
        print("-" * 60)

        text_content = extract_text_from_note(note_path)

        if text_content:
            print(text_content)
        else:
            print("[No readable text content found]")

        print("\n" + "=" * 80 + "\n")

if __name__ == "__main__":
    process_all_notes()