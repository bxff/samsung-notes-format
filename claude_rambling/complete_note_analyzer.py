#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import struct
import re
import json
from datetime import datetime

class CompleteNoteAnalyzer:
    def __init__(self, note_file_path):
        self.note_file_path = note_file_path
        self.data = None
        self.analysis = {
            'file_info': {},
            'metadata': {},
            'content_types': {},
            'text_content': [],
            'pen_strokes': [],
            'coordinates': [],
            'structure_analysis': {},
            'pen_metadata': {}
        }

    def load_data(self):
        """Load binary data from note file"""
        try:
            with open(self.note_file_path, 'rb') as f:
                self.data = f.read()
            self.analysis['file_info'] = {
                'filename': os.path.basename(self.note_file_path),
                'file_size': len(self.data),
                'file_path': self.note_file_path
            }
            return True
        except Exception as e:
            print(f"Error loading file: {e}")
            return False

    def extract_metadata(self):
        """Extract all metadata from the note"""
        if not self.data:
            return

        metadata = {}
        filename = os.path.basename(self.note_file_path)
        basename = os.path.splitext(filename)[0]

        # Extract date and title from filename
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

        # Extract UUIDs
        uuid_pattern = rb'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'
        uuids = re.findall(uuid_pattern, self.data)
        metadata['uuids'] = [uid.decode('ascii') for uid in uuids]

        # Extract header information
        if len(self.data) >= 20:
            metadata['header_magic'] = hex(struct.unpack('<I', self.data[:4])[0])
            metadata['format_version'] = hex(struct.unpack('<I', self.data[4:8])[0])

        self.analysis['metadata'] = metadata

    def extract_text_content(self):
        """Extract all text content using multiple methods"""
        if not self.data:
            return

        text_content = []

        # Method 1: UTF-16 extraction
        utf16_text = []
        i = 0
        while i < len(self.data) - 1:
            if self.data[i] >= 32 and self.data[i] <= 126 and self.data[i+1] == 0:
                chars = []
                j = i
                while j < len(self.data) - 1 and self.data[j] >= 32 and self.data[j] <= 126 and self.data[j+1] == 0:
                    chars.append(chr(self.data[j]))
                    j += 2
                if len(chars) > 1:
                    utf16_text.append(''.join(chars))
                i = j
            else:
                i += 1

        # Method 2: ASCII extraction
        ascii_text = ''.join([chr(b) for b in self.data if 32 <= b <= 126])

        # Method 3: UTF-8 extraction
        try:
            utf8_text = self.data.decode('utf-8', errors='ignore')
        except:
            utf8_text = ""

        # Clean and combine text
        for method_name, text_list in [
            ("UTF-16", utf16_text),
            ("ASCII", [ascii_text]),
            ("UTF-8", [utf8_text])
        ]:
            for text in text_list:
                if text and len(text.strip()) > 1:
                    # Filter out Samsung metadata
                    if not any(skip in text for skip in [
                        'com.samsung.android.sdk.pen',
                        'FountainPen', 'pen.preload',
                        'qi@$', 'AK7', 'A%%%'
                    ]):
                        text_content.append({
                            'method': method_name,
                            'content': text.strip(),
                            'length': len(text.strip())
                        })

        self.analysis['text_content'] = text_content

    def extract_pen_metadata(self):
        """Extract pen-related metadata"""
        if not self.data:
            return

        pen_metadata = {}

        # Extract pen package names
        pen_pattern = rb'com\.samsung\.android\.sdk\.pen\.pen\.preload\.([A-Za-z]+)'
        pen_matches = re.findall(pen_pattern, self.data)
        pen_metadata['pen_types'] = list(set([match.decode('ascii') for match in pen_matches]))

        # Extract color/stroke patterns
        color_pattern = rb'(\d+;\d+;\d+;)'
        color_matches = re.findall(color_pattern, self.data)
        pen_metadata['color_patterns'] = [match.decode('ascii') for match in color_matches]

        # Extract stroke metadata
        stroke_pattern = rb'(\d+#\w+)'
        stroke_matches = re.findall(stroke_pattern, self.data)
        pen_metadata['stroke_metadata'] = [match.decode('ascii') for match in stroke_matches]

        self.analysis['pen_metadata'] = pen_metadata

    def extract_pen_strokes(self):
        """Extract pen stroke coordinate data"""
        if not self.data:
            return

        strokes = []

        # Method 1: Float coordinate sequences
        i = 0
        while i < len(self.data) - 16:
            try:
                coords = []
                for j in range(0, 16, 4):
                    if i + j + 4 <= len(self.data):
                        val = struct.unpack('<f', self.data[i+j:i+j+4])[0]
                        if 10 < val < 2000:  # Reasonable screen coordinate range
                            coords.append(val)
                        else:
                            break

                if len(coords) >= 4:
                    stroke_coords = []
                    for k in range(0, len(coords)-1, 2):
                        if k+1 < len(coords):
                            stroke_coords.append([coords[k], coords[k+1]])

                    if len(stroke_coords) >= 2:
                        strokes.append({
                            'offset': hex(i),
                            'coordinates': stroke_coords,
                            'data_type': 'float32',
                            'point_count': len(stroke_coords),
                            'raw_values': coords
                        })
                        i += 16
                    else:
                        i += 4
                else:
                    i += 4

            except:
                i += 1

        # Method 2: Integer coordinate sequences
        i = 0
        while i < len(self.data) - 8:
            try:
                coords = []
                for j in range(0, 8, 2):
                    if i + j + 2 <= len(self.data):
                        val = struct.unpack('<H', self.data[i+j:i+j+2])[0]
                        if 10 < val < 2000:
                            coords.append(val)
                        else:
                            break

                if len(coords) >= 4:
                    stroke_coords = []
                    for k in range(0, len(coords)-1, 2):
                        if k+1 < len(coords):
                            stroke_coords.append([coords[k], coords[k+1]])

                    if len(stroke_coords) >= 2:
                        strokes.append({
                            'offset': hex(i),
                            'coordinates': stroke_coords,
                            'data_type': 'uint16',
                            'point_count': len(stroke_coords),
                            'raw_values': coords
                        })
                        i += 8
                    else:
                        i += 2
                else:
                    i += 2

            except:
                i += 1

        # Filter strokes to remove noise
        filtered_strokes = []
        for stroke in strokes:
            coords = stroke['coordinates']
            if coords:
                x_coords = [c[0] for c in coords]
                y_coords = [c[1] for c in coords]

                # Only keep strokes with reasonable dimensions
                if (max(x_coords) - min(x_coords) > 5 and
                    max(y_coords) - min(y_coords) > 5):
                    filtered_strokes.append(stroke)

        self.analysis['pen_strokes'] = filtered_strokes

    def analyze_structure(self):
        """Analyze the binary structure"""
        if not self.data:
            return

        structure = {}

        # Null byte analysis
        null_positions = [i for i, b in enumerate(self.data) if b == 0]
        structure['null_byte_count'] = len(null_positions)
        structure['null_byte_density'] = len(null_positions) / len(self.data)

        # UTF-16 text regions
        utf16_regions = []
        i = 0
        while i < len(self.data) - 1:
            if self.data[i] >= 32 and self.data[i] <= 126 and self.data[i+1] == 0:
                start = i
                while i < len(self.data) - 1 and self.data[i] >= 32 and self.data[i] <= 126 and self.data[i+1] == 0:
                    i += 2
                utf16_regions.append({
                    'start': hex(start),
                    'end': hex(i),
                    'length': i - start,
                    'char_count': (i - start) // 2
                })
            else:
                i += 1

        structure['utf16_regions'] = utf16_regions

        # Byte frequency analysis
        byte_counts = {}
        for b in self.data:
            byte_counts[b] = byte_counts.get(b, 0) + 1

        structure['byte_frequency'] = dict(sorted(byte_counts.items(), key=lambda x: x[1], reverse=True)[:10])

        # Pattern analysis
        structure['repeating_patterns'] = []
        for pattern_length in [2, 4, 8]:
            patterns = {}
            for i in range(len(self.data) - pattern_length):
                pattern = self.data[i:i+pattern_length]
                patterns[pattern] = patterns.get(pattern, 0) + 1

            common_patterns = [(p, c) for p, c in patterns.items() if c > 3]
            if common_patterns:
                structure['repeating_patterns'].extend([
                    {
                        'pattern': p.hex(),
                        'length': pattern_length,
                        'count': c
                    } for p, c in sorted(common_patterns, key=lambda x: x[1], reverse=True)[:3]
                ])

        self.analysis['structure_analysis'] = structure

    def analyze_content_types(self):
        """Analyze what types of content are present"""
        content_types = {}

        # Check for text content
        if self.analysis['text_content']:
            content_types['text'] = {
                'present': True,
                'segments': len(self.analysis['text_content']),
                'total_chars': sum(t['length'] for t in self.analysis['text_content'])
            }
        else:
            content_types['text'] = {'present': False}

        # Check for pen strokes
        if self.analysis['pen_strokes']:
            content_types['handwritten'] = {
                'present': True,
                'strokes': len(self.analysis['pen_strokes']),
                'total_points': sum(s['point_count'] for s in self.analysis['pen_strokes'])
            }
        else:
            content_types['handwritten'] = {'present': False}

        # Check for pen metadata
        if self.analysis['pen_metadata'].get('pen_types'):
            content_types['pen_metadata'] = {
                'present': True,
                'pen_types': self.analysis['pen_metadata']['pen_types']
            }
        else:
            content_types['pen_metadata'] = {'present': False}

        # Determine dominant content type
        if content_types['text']['present'] and content_types['handwritten']['present']:
            content_types['dominant_type'] = 'mixed'
        elif content_types['text']['present']:
            content_types['dominant_type'] = 'text_only'
        elif content_types['handwritten']['present']:
            content_types['dominant_type'] = 'handwritten_only'
        else:
            content_types['dominant_type'] = 'empty_or_binary'

        self.analysis['content_types'] = content_types

    def run_complete_analysis(self):
        """Run all analysis methods"""
        if not self.load_data():
            return None

        self.extract_metadata()
        self.extract_text_content()
        self.extract_pen_metadata()
        self.extract_pen_strokes()
        self.analyze_structure()
        self.analyze_content_types()

        return self.analysis

    def print_detailed_report(self):
        """Print a comprehensive analysis report"""
        analysis = self.run_complete_analysis()
        if not analysis:
            print("❌ Failed to analyze note")
            return

        print("📱 SAMSUNG NOTES - COMPLETE ANALYSIS REPORT")
        print("=" * 80)

        # File Information
        print(f"\n📁 FILE INFORMATION:")
        print("-" * 40)
        file_info = analysis['file_info']
        print(f"Filename: {file_info['filename']}")
        print(f"Size: {file_info['file_size']} bytes")

        # Metadata
        print(f"\n📋 METADATA:")
        print("-" * 40)
        metadata = analysis['metadata']
        print(f"Title: {metadata.get('title', 'Unknown')}")
        print(f"Created: {metadata.get('created_date', 'Unknown')}")
        if metadata.get('uuids'):
            print(f"UUIDs: {', '.join(metadata['uuids'][:2])}")

        # Content Types Analysis
        print(f"\n📊 CONTENT TYPES:")
        print("-" * 40)
        content = analysis['content_types']
        print(f"Dominant Type: {content['dominant_type'].upper()}")
        print(f"Text Content: {'✓ Present' if content['text']['present'] else '✗ Absent'}")
        print(f"Handwritten Content: {'✓ Present' if content['handwritten']['present'] else '✗ Absent'}")
        print(f"Pen Metadata: {'✓ Present' if content['pen_metadata']['present'] else '✗ Absent'}")

        # Text Content Details
        if content['text']['present']:
            print(f"\n📝 TEXT CONTENT:")
            print("-" * 40)
            for i, text in enumerate(analysis['text_content'][:3], 1):
                print(f"{i}. [{text['method']}] {text['content'][:80]}{'...' if len(text['content']) > 80 else ''}")

        # Handwritten Content Details
        if content['handwritten']['present']:
            print(f"\n✏️  HANDWRITTEN CONTENT:")
            print("-" * 40)
            strokes = analysis['pen_strokes']
            print(f"Strokes: {len(strokes)}")
            print(f"Total Points: {content['handwritten']['total_points']}")

            for i, stroke in enumerate(strokes[:3], 1):
                print(f"  Stroke {i}: {stroke['point_count']} points at offset {stroke['offset']}")
                coords = stroke['coordinates'][:3]
                print(f"    Sample coords: {coords}{'...' if len(stroke['coordinates']) > 3 else ''}")

        # Pen Metadata
        if content['pen_metadata']['present']:
            print(f"\n🖊️  PEN METADATA:")
            print("-" * 40)
            pen_meta = analysis['pen_metadata']
            if pen_meta.get('pen_types'):
                print(f"Pen Types: {', '.join(pen_meta['pen_types'])}")
            if pen_meta.get('color_patterns'):
                print(f"Color Patterns: {', '.join(pen_meta['color_patterns'][:2])}")

        # Structure Analysis
        print(f"\n🔍 STRUCTURE ANALYSIS:")
        print("-" * 40)
        structure = analysis['structure_analysis']
        print(f"Null bytes: {structure['null_byte_count']} ({structure['null_byte_density']:.1%} of file)")
        print(f"UTF-16 regions: {len(structure['utf16_regions'])}")
        print(f"Most common byte: 0x{list(structure['byte_frequency'].keys())[0]:02x}")

        # Export data
        self.export_analysis()

    def export_analysis(self):
        """Export analysis to JSON file"""
        try:
            # Convert bytes to strings for JSON serialization
            analysis_copy = {}
            for key, value in self.analysis.items():
                if isinstance(value, dict):
                    analysis_copy[key] = {}
                    for subkey, subvalue in value.items():
                        if isinstance(subvalue, bytes):
                            analysis_copy[key][subkey] = subvalue.hex()
                        elif isinstance(subvalue, list) and subvalue and isinstance(subvalue[0], bytes):
                            analysis_copy[key][subkey] = [item.hex() if isinstance(item, bytes) else item for item in subvalue]
                        else:
                            analysis_copy[key][subkey] = subvalue
                else:
                    analysis_copy[key] = value

            output_file = f"analysis_{os.path.splitext(os.path.basename(self.note_file_path))[0]}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_copy, f, indent=2, ensure_ascii=False)

            print(f"\n💾 Analysis exported to: {output_file}")
        except Exception as e:
            print(f"\n❌ Failed to export analysis: {e}")

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

    print("🔬 SAMSUNG NOTES - COMPREHENSIVE ANALYZER")
    print("=" * 80)
    print(f"Found {len(note_files)} note file(s) to analyze\n")

    for note_file in sorted(note_files):
        note_path = os.path.join(note_folder, note_file)
        analyzer = CompleteNoteAnalyzer(note_path)
        analyzer.print_detailed_report()
        print("\n" + "=" * 80)

if __name__ == "__main__":
    main()