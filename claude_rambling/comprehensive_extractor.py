#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import struct
import json
import re
from datetime import datetime

class SamsungNotesExtractor:
    def __init__(self, note_file_path):
        self.note_file_path = note_file_path
        self.data = None
        self.note_content = {
            'metadata': {},
            'text_content': [],
            'pen_strokes': [],
            'pen_info': [],
            'coordinates': [],
            'raw_data_analysis': {}
        }

    def load_data(self):
        """Load the binary data from the note file"""
        try:
            with open(self.note_file_path, 'rb') as f:
                self.data = f.read()
            return True
        except Exception as e:
            print(f"Error loading file: {e}")
            return False

    def extract_metadata(self):
        """Extract metadata from the binary header"""
        if not self.data:
            return

        metadata = {}

        # Extract UUIDs
        uuid_pattern = rb'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'
        uuids = re.findall(uuid_pattern, self.data)
        metadata['uuids'] = [uid.decode('ascii') for uid in uuids]

        # Extract file info from filename
        filename = os.path.basename(self.note_file_path)
        basename = os.path.splitext(filename)[0]

        # Try to extract date from filename
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
                metadata['created_date'] = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                metadata['title'] = basename[:date_match.start()].replace('_', ' ')
            except:
                metadata['created_date'] = "Unknown"
                metadata['title'] = basename
        else:
            metadata['created_date'] = "Unknown"
            metadata['title'] = basename

        metadata['file_size'] = len(self.data)

        # Extract header information
        if len(self.data) >= 12:
            header_info = struct.unpack('<I', self.data[:4])[0]
            metadata['header_magic'] = hex(header_info)

        self.note_content['metadata'] = metadata

    def extract_text_content(self):
        """Extract UTF-16 text content"""
        if not self.data:
            return

        text_segments = []
        i = 0
        while i < len(self.data) - 1:
            # Look for UTF-16 patterns (character + null byte)
            if self.data[i] >= 32 and self.data[i] <= 126 and self.data[i+1] == 0:
                chars = []
                j = i
                while j < len(self.data) - 1 and self.data[j] >= 32 and self.data[j] <= 126 and self.data[j+1] == 0:
                    chars.append(chr(self.data[j]))
                    j += 2
                    if j >= len(self.data) - 1 or self.data[j] != 0:
                        break

                if len(chars) > 1:
                    text_segments.append(''.join(chars))
                i = j
            else:
                i += 1

        # Filter out Samsung metadata
        clean_text = []
        for segment in text_segments:
            if not any(skip in segment for skip in [
                'com.samsung.android.sdk.pen',
                'FountainPen',
                'pen.preload'
            ]):
                clean_text.append(segment)

        self.note_content['text_content'] = clean_text

    def extract_pen_info(self):
        """Extract pen information and metadata"""
        if not self.data:
            return

        # Look for pen package names
        pen_pattern = rb'com\.samsung\.android\.sdk\.pen\.pen\.preload\.([A-Za-z]+)'
        pen_matches = re.findall(pen_pattern, self.data)

        pen_types = []
        for match in pen_matches:
            pen_types.append(match.decode('ascii'))

        # Look for pen color/stroke info
        color_pattern = rb'\d+;\d+;\d+;'
        color_matches = re.findall(color_pattern, self.data)

        stroke_patterns = []
        for match in color_matches:
            stroke_patterns.append(match.decode('ascii'))

        self.note_content['pen_info'] = {
            'pen_types': list(set(pen_types)),
            'stroke_patterns': stroke_patterns
        }

    def extract_coordinates(self):
        """Extract potential coordinate data"""
        if not self.data:
            return

        coordinates = []

        # Look for float values that could be coordinates
        for i in range(0, len(self.data) - 4, 4):
            try:
                # Try to interpret as little-endian float
                val = struct.unpack('<f', self.data[i:i+4])[0]

                # Check if it's a reasonable coordinate value
                if 0.1 < val < 10000:  # Reasonable range for coordinates
                    coordinates.append({
                        'offset': hex(i),
                        'value': val,
                        'type': 'float'
                    })
            except:
                continue

        # Also look for coordinate-like integer values
        for i in range(0, len(self.data) - 4, 2):
            try:
                val = struct.unpack('<H', self.data[i:i+2])[0]
                if 0 < val < 5000:  # Reasonable range
                    coordinates.append({
                        'offset': hex(i),
                        'value': val,
                        'type': 'uint16'
                    })
            except:
                continue

        self.note_content['coordinates'] = coordinates[:50]  # Limit to first 50

    def extract_pen_strokes(self):
        """Extract pen stroke data patterns"""
        if not self.data:
            return

        strokes = []

        # Look for stroke data patterns
        # Pen strokes often come in sequences of coordinates
        i = 0
        while i < len(self.data) - 8:
            # Look for patterns that might be stroke data
            try:
                # Try to read as a sequence of coordinates
                if i + 16 < len(self.data):
                    coords = []
                    for j in range(0, 16, 4):
                        val = struct.unpack('<f', self.data[i+j:i+j+4])[0]
                        if 0 < val < 5000:
                            coords.append(val)

                    if len(coords) >= 4:  # Found a potential stroke sequence
                        strokes.append({
                            'offset': hex(i),
                            'coordinates': coords,
                            'length': len(coords)
                        })
                        i += 16
                    else:
                        i += 4
                else:
                    i += 1
            except:
                i += 1

        self.note_content['pen_strokes'] = strokes

    def analyze_structure(self):
        """Analyze the overall structure"""
        if not self.data:
            return

        analysis = {}

        # Find all null bytes (often separators)
        null_positions = [i for i, b in enumerate(self.data) if b == 0]
        analysis['null_byte_count'] = len(null_positions)
        analysis['null_byte_positions'] = [hex(pos) for pos in null_positions[:20]]

        # Find UTF-16 text regions
        utf16_regions = []
        i = 0
        while i < len(self.data) - 1:
            if self.data[i] >= 32 and self.data[i] <= 126 and self.data[i+1] == 0:
                start = i
                while i < len(self.data) - 1 and self.data[i] >= 32 and self.data[i] <= 126 and self.data[i+1] == 0:
                    i += 2
                utf16_regions.append((hex(start), hex(i), i-start))
            else:
                i += 1

        analysis['utf16_regions'] = utf16_regions

        # Analyze byte distribution
        byte_counts = {}
        for b in self.data:
            byte_counts[b] = byte_counts.get(b, 0) + 1
        analysis['most_common_bytes'] = sorted(byte_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        self.note_content['raw_data_analysis'] = analysis

    def extract_all(self):
        """Extract all content types"""
        if not self.load_data():
            return None

        self.extract_metadata()
        self.extract_text_content()
        self.extract_pen_info()
        self.extract_coordinates()
        self.extract_pen_strokes()
        self.analyze_structure()

        return self.note_content

    def print_comprehensive_report(self):
        """Print a detailed report of all extracted content"""
        content = self.extract_all()
        if not content:
            print("Failed to extract content")
            return

        print("📱 SAMSUNG NOTES - COMPREHENSIVE CONTENT ANALYSIS")
        print("=" * 80)

        # Metadata
        print("\n📋 METADATA:")
        print("-" * 40)
        meta = content['metadata']
        print(f"Title: {meta.get('title', 'Unknown')}")
        print(f"Created: {meta.get('created_date', 'Unknown')}")
        print(f"File Size: {meta.get('file_size', 0)} bytes")
        if meta.get('uuids'):
            print(f"UUIDs: {', '.join(meta['uuids'])}")

        # Text Content
        print(f"\n📝 TEXT CONTENT:")
        print("-" * 40)
        text = content['text_content']
        if text:
            for i, segment in enumerate(text, 1):
                print(f"{i}. {segment}")
        else:
            print("No readable text content found")

        # Pen Information
        print(f"\n🖊️  PEN INFORMATION:")
        print("-" * 40)
        pen_info = content['pen_info']
        if pen_info.get('pen_types'):
            print(f"Pen Types: {', '.join(pen_info['pen_types'])}")
        if pen_info.get('stroke_patterns'):
            print(f"Stroke Patterns: {', '.join(pen_info['stroke_patterns'])}")

        # Coordinates
        print(f"\n📍 COORDINATE DATA:")
        print("-" * 40)
        coords = content['coordinates']
        if coords:
            print(f"Found {len(coords)} potential coordinate values")
            print("Sample coordinates:")
            for i, coord in enumerate(coords[:10], 1):
                print(f"  {i}. Offset {coord['offset']}: {coord['value']} ({coord['type']})")
            if len(coords) > 10:
                print(f"  ... and {len(coords) - 10} more")
        else:
            print("No coordinate data found")

        # Pen Strokes
        print(f"\n✏️  PEN STROKES:")
        print("-" * 40)
        strokes = content['pen_strokes']
        if strokes:
            print(f"Found {len(strokes)} potential stroke sequences")
            for i, stroke in enumerate(strokes[:5], 1):
                print(f"  Stroke {i}: Offset {stroke['offset']}, {stroke['length']} points")
                print(f"    Coords: {stroke['coordinates'][:6]}{'...' if len(stroke['coordinates']) > 6 else ''}")
            if len(strokes) > 5:
                print(f"  ... and {len(strokes) - 5} more strokes")
        else:
            print("No pen stroke data found")

        # Structure Analysis
        print(f"\n🔍 STRUCTURE ANALYSIS:")
        print("-" * 40)
        analysis = content['raw_data_analysis']
        print(f"Null bytes: {analysis.get('null_byte_count', 0)}")
        print(f"UTF-16 text regions: {len(analysis.get('utf16_regions', []))}")
        if analysis.get('most_common_bytes'):
            print("Most common bytes:")
            for byte_val, count in analysis['most_common_bytes'][:5]:
                print(f"  0x{byte_val:02x}: {count} occurrences")

def main():
    note_folder = "notePnote"

    if not os.path.exists(note_folder):
        print("❌ Error: notePnote folder not found")
        print("Please run 'python3 sdocxToTxt.py' first to extract notes.")
        return

    note_files = [f for f in os.listdir(note_folder) if f.endswith('.note')]

    if not note_files:
        print("❌ No note files found")
        return

    for note_file in sorted(note_files):
        note_path = os.path.join(note_folder, note_file)
        print(f"\n{'='*80}")
        print(f"ANALYZING: {note_file}")
        print(f"{'='*80}")

        extractor = SamsungNotesExtractor(note_path)
        extractor.print_comprehensive_report()

if __name__ == "__main__":
    main()