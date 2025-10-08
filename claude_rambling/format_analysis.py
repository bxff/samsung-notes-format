#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re

def analyze_note_format(note_file_path):
    """Analyze the structure of a Samsung Notes file"""
    print(f"🔍 Analyzing {os.path.basename(note_file_path)}")
    print("=" * 50)

    try:
        with open(note_file_path, 'rb') as f:
            content = f.read()

        print(f"📊 File size: {len(content)} bytes")
        print(f"📋 First 64 bytes (hex): {content[:64].hex()}")
        print(f"📋 First 32 bytes (ASCII): {[chr(b) if 32 <= b <= 126 else '.' for b in content[:32]]}")

        # Look for UTF-16 patterns
        utf16_matches = []
        i = 0
        while i < len(content) - 1:
            if content[i] >= 32 and content[i] <= 126 and content[i+1] == 0:
                # Found potential UTF-16 start
                chars = []
                j = i
                while j < len(content) - 1:
                    if content[j] >= 32 and content[j] <= 126 and content[j+1] == 0:
                        chars.append(chr(content[j]))
                        j += 2
                    else:
                        break
                if len(chars) > 1:
                    utf16_matches.append(''.join(chars))
                i = j
            else:
                i += 1

        print(f"\n🔤 UTF-16 text segments found: {len(utf16_matches)}")
        for i, match in enumerate(utf16_matches[:5], 1):  # Show first 5
            print(f"  {i}. {match}")

        # Look for UUIDs
        uuid_pattern = re.compile(rb'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}')
        uuids = re.findall(uuid_pattern, content)
        print(f"\n🆔 UUIDs found: {len(uuids)}")
        for uid in uuids[:3]:  # Show first 3
            print(f"  - {uid.decode('ascii', errors='ignore')}")

        # Look for Samsung package names
        samsung_pattern = re.compile(rb'com\.samsung\.android\.sdk\.pen\.pen\.preload\.[A-Za-z]+')
        samsung_refs = re.findall(samsung_pattern, content)
        print(f"\n📱 Samsung pen references: {len(samsung_refs)}")
        for ref in samsung_refs:
            print(f"  - {ref.decode('ascii', errors='ignore')}")

        # Try to extract all readable text using different methods
        print(f"\n📝 Text extraction attempts:")

        # Method 1: UTF-16
        utf16_text = ' '.join(utf16_matches)
        print(f"  UTF-16 extraction: {len(utf16_text)} chars")
        if utf16_text:
            print(f"    Sample: {utf16_text[:100]}...")

        # Method 2: ASCII extraction
        ascii_text = ''.join([chr(b) for b in content if 32 <= b <= 126])
        print(f"  ASCII extraction: {len(ascii_text)} chars")
        if ascii_text:
            print(f"    Sample: {ascii_text[:100]}...")

        # Method 3: UTF-8 extraction
        try:
            utf8_text = content.decode('utf-8', errors='ignore')
            print(f"  UTF-8 extraction: {len(utf8_text)} chars")
            if utf8_text:
                print(f"    Sample: {utf8_text[:100]}...")
        except:
            print("  UTF-8 extraction: Failed")

        return True

    except Exception as e:
        print(f"❌ Error analyzing file: {e}")
        return False

def main():
    note_folder = "notePnote"

    if not os.path.exists(note_folder):
        print("❌ Error: notePnote folder not found")
        return

    note_files = [f for f in os.listdir(note_folder) if f.endswith('.note')]

    if not note_files:
        print("❌ No note files found")
        return

    print("🔬 SAMSUNG NOTES FORMAT ANALYSIS")
    print("=" * 70)

    for note_file in sorted(note_files):
        note_path = os.path.join(note_folder, note_file)
        analyze_note_format(note_path)
        print("\n" + "=" * 70 + "\n")

if __name__ == "__main__":
    main()