#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re

def extract_clean_text(note_file_path):
    """Extract only clean readable text from Samsung Notes file"""
    try:
        with open(note_file_path, 'rb') as f:
            content = f.read()

        # Convert to string and extract only printable ASCII/UTF-8 text
        try:
            # Try UTF-8 first
            text = content.decode('utf-8', errors='ignore')
        except:
            # Fallback to latin-1
            text = content.decode('latin-1', errors='ignore')

        # Find all readable sentences/phrases
        # Look for patterns that look like normal sentences
        sentences = re.findall(r'[A-Z][a-zA-Z0-9\s,.!?\'"-]+[.!?]', text)

        # Also look for other readable text chunks
        text_chunks = re.findall(r'[a-zA-Z][a-zA-Z0-9\s,.!?\'"-]{10,}', text)

        # Combine unique text pieces
        all_text = set(sentences + text_chunks)

        # Filter out Samsung metadata
        clean_text = []
        for piece in all_text:
            # Skip if it contains Samsung metadata
            if any(skip in piece for skip in [
                'com.samsung.android.sdk.pen',
                'FountainPen',
                'pen.preload',
                '@$',
                'qi@$',
                'A%%%',
                'AA A',
                'AK7B',
                'atK7B'
            ]):
                continue

            # Skip if it's too short or just metadata
            if len(piece.strip()) < 5:
                continue

            clean_text.append(piece.strip())

        return ' '.join(clean_text) if clean_text else None

    except Exception as e:
        print(f"Error processing {note_file_path}: {e}")
        return None

def extract_title_from_filename(filename):
    """Extract a clean title from the filename"""
    basename = os.path.splitext(os.path.basename(filename))[0]

    # Remove date/time pattern
    basename = re.sub(r'_\d{6}_\d{6}$', '', basename)

    # Replace underscores with spaces and clean up
    title = basename.replace('_', ' ').strip()

    return title

def extract_date_from_filename(filename):
    """Extract date from filename"""
    basename = os.path.splitext(os.path.basename(filename))[0]

    date_match = re.search(r'_(\d{6})_(\d{6})$', basename)
    if date_match:
        date_str = date_match.group(1)
        time_str = date_match.group(2)

        try:
            year = "20" + date_str[0:2]
            month = date_str[2:4]
            day = date_str[4:6]
            hour = time_str[0:2]
            minute = time_str[2:4]
            second = time_str[4:6]

            return f"{year}-{month}-{day} {hour}:{minute}:{second}"
        except:
            pass

    return "Unknown date"

def display_notes():
    """Display all notes in a clean format"""
    note_folder = "notePnote"

    if not os.path.exists(note_folder):
        print("Error: notePnote folder not found")
        print("Please run sdocxToTxt.py first to extract notes from sdocx files.")
        return

    note_files = [f for f in os.listdir(note_folder) if f.endswith('.note')]

    if not note_files:
        print("No note files found.")
        return

    print("📱 SAMSUNG NOTES - CLEAN TEXT EXTRACTED")
    print("=" * 70)
    print(f"Found {len(note_files)} note(s)\n")

    for i, note_file in enumerate(sorted(note_files), 1):
        note_path = os.path.join(note_folder, note_file)

        title = extract_title_from_filename(note_file)
        date = extract_date_from_filename(note_file)
        content = extract_clean_text(note_path)

        print(f"📝 Note {i}: {title}")
        print(f"📅 Date: {date}")
        print("-" * 50)

        if content and len(content.strip()) > 0:
            print(content)
        else:
            print("⚠️  No readable text content found")
            print("   (This might be a handwritten note, drawing, or contain only images)")

        print("\n" + "=" * 70 + "\n")

if __name__ == "__main__":
    display_notes()