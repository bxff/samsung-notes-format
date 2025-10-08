#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re

def extract_manual_text(note_file_path):
    """Manually extract text by analyzing the binary structure"""
    try:
        with open(note_file_path, 'rb') as f:
            content = f.read()

        # Look for UTF-16 text patterns (character followed by null byte)
        text_segments = []
        i = 0
        current_text = ""

        while i < len(content) - 1:
            # Check if this looks like UTF-16 text
            if content[i] >= 32 and content[i] <= 126 and content[i+1] == 0:
                # This could be UTF-16 text
                chars = []
                j = i
                while j < len(content) - 1:
                    if content[j] >= 32 and content[j] <= 126 and content[j+1] == 0:
                        chars.append(chr(content[j]))
                        j += 2
                    elif content[j] == 0 and j < len(content) - 1 and content[j+1] >= 32 and content[j+1] <= 126:
                        # Skip null byte and continue
                        j += 1
                    else:
                        break

                if len(chars) > 1:
                    segment = ''.join(chars)
                    # Only add if it looks like real text
                    if any(c.isalpha() for c in segment):
                        text_segments.append(segment)
                i = j
            else:
                i += 1

        # Join segments and clean up
        full_text = ' '.join(text_segments)

        # Remove Samsung metadata patterns
        patterns = [
            r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',  # UUIDs
            r'com\.samsung\.android\.sdk\.pen\.pen\.preload\.[A-Za-z]+',
            r'@\$\w+',
            r'AK7\w*',
            r'A%%%',
            r'\d+;\d+;\d+;',
            r'AA A',
            r'\d+#A_\d+cC',
            r'L\?\?\|',
            r'@\|',
            r'fudA\w*',
        ]

        for pattern in patterns:
            full_text = re.sub(pattern, '', full_text, flags=re.IGNORECASE)

        # Clean up whitespace
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        # Try to extract meaningful sentences
        sentences = re.findall(r'[A-Z][a-zA-Z0-9\s,.!?\'"-]+[.!?]', full_text)
        if sentences:
            return ' '.join(sentences)

        # If no sentences found, return cleaned text if it has content
        if len(full_text) > 10:
            return full_text

        return None

    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    note_folder = "notePnote"

    if not os.path.exists(note_folder):
        print("❌ Error: notePnote folder not found")
        print("Please run 'python3 sdocxToTxt.py' first to extract notes.")
        return

    note_files = [f for f in os.listdir(note_folder) if f.endswith('.note')]

    if not note_files:
        print("❌ No note files found in notePnote folder")
        return

    print("📱 Samsung Notes - Clean Text Extraction")
    print("=" * 60)
    print(f"📊 Found {len(note_files)} note(s)\n")

    for i, note_file in enumerate(sorted(note_files), 1):
        note_path = os.path.join(note_folder, note_file)

        # Extract title and date from filename
        basename = os.path.splitext(note_file)[0]
        title = re.sub(r'_\d{6}_\d{6}$', '', basename).replace('_', ' ')

        date_match = re.search(r'_(\d{6})_(\d{6})$', basename)
        if date_match:
            date_str = date_match.group(1)
            time_str = date_match.group(2)
            try:
                date = f"20{date_str[0:2]}-{date_str[2:4]}-{date_str[4:6]} {time_str[0:2]}:{time_str[2:4]}:{time_str[4:6]}"
            except:
                date = "Unknown date"
        else:
            date = "Unknown date"

        print(f"📝 Note {i}: {title}")
        print(f"📅 Created: {date}")
        print("-" * 40)

        content = extract_manual_text(note_path)

        if content and len(content.strip()) > 0:
            print(content)
        else:
            print("⚠️  No readable text found")
            print("   This note might contain:")
            print("   • Handwritten content")
            print("   • Drawings or sketches")
            print("   • Images or attachments")

        print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    main()