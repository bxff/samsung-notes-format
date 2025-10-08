#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import struct
import re
import json

class AdvancedStrokeDecoder:
    def __init__(self, note_file_path):
        self.note_file_path = note_file_path
        self.data = None
        self.decoded_content = {
            'metadata': {},
            'text_content': [],
            'strokes': [],
            'format_info': {}
        }

    def load_data(self):
        """Load binary data"""
        try:
            with open(self.note_file_path, 'rb') as f:
                self.data = f.read()
            return True
        except Exception as e:
            print(f"Error loading file: {e}")
            return False

    def parse_file_structure(self):
        """Parse the main file structure based on discovered patterns"""
        if not self.data or len(self.data) < 20:
            return

        # Parse header structure
        header_info = {}

        # Key offsets discovered in analysis
        offsets = {
            'magic': 0x0,
            'version': 0x4,
            'data_offset': 0x28,
            'size1': 0x2c,
            'text_offset': 0x34,
            'text_size': 0x38,
            'uuid_offset': 0x50
        }

        for name, offset in offsets.items():
            if offset + 4 <= len(self.data):
                try:
                    value = struct.unpack('<I', self.data[offset:offset+4])[0]
                    header_info[name] = {
                        'offset': hex(offset),
                        'value': value,
                        'raw': self.data[offset:offset+4].hex()
                    }
                except:
                    header_info[name] = {'offset': hex(offset), 'value': 'error', 'raw': self.data[offset:offset+4].hex()}

        self.decoded_content['format_info'] = header_info

    def extract_text_content_advanced(self):
        """Extract text content with better understanding of structure"""
        if not self.data:
            return

        text_segments = []

        # Method 1: Find UTF-16 text in known text regions
        # Based on analysis, text appears around offset 0x140-0x180
        text_regions = [
            (0x140, 0x180),  # Main text region
            (0x360, 0x460),  # Pen info region
        ]

        for start, end in text_regions:
            if start < len(self.data):
                region_data = self.data[start:min(end, len(self.data))]

                # Extract UTF-16 text
                utf16_text = self._extract_utf16_from_region(region_data, start)
                for text in utf16_text:
                    if text and len(text.strip()) > 1:
                        text_segments.append({
                            'type': 'utf16',
                            'content': text.strip(),
                            'offset': hex(start)
                        })

        # Method 2: Scan entire file for UTF-16 patterns
        i = 0
        while i < len(self.data) - 1:
            if self.data[i] >= 32 and self.data[i] <= 126 and self.data[i+1] == 0:
                chars = []
                j = i
                while j < len(self.data) - 1 and self.data[j] >= 32 and self.data[j] <= 126 and self.data[j+1] == 0:
                    chars.append(chr(self.data[j]))
                    j += 2

                if len(chars) > 1:
                    text = ''.join(chars)
                    if not self._is_metadata(text):
                        text_segments.append({
                            'type': 'utf16_scanned',
                            'content': text,
                            'offset': hex(i),
                            'end_offset': hex(j)
                        })
                i = j
            else:
                i += 1

        self.decoded_content['text_content'] = text_segments

    def _extract_utf16_from_region(self, region_data, base_offset):
        """Extract UTF-16 text from a specific region"""
        text_segments = []

        i = 0
        while i < len(region_data) - 1:
            if region_data[i] >= 32 and region_data[i] <= 126 and region_data[i+1] == 0:
                chars = []
                j = i
                while j < len(region_data) - 1 and region_data[j] >= 32 and region_data[j] <= 126 and region_data[j+1] == 0:
                    chars.append(chr(region_data[j]))
                    j += 2

                if len(chars) > 1:
                    text_segments.append(''.join(chars))
                i = j
            else:
                i += 1

        return text_segments

    def _is_metadata(self, text):
        """Check if text is metadata"""
        metadata_patterns = [
            'com.samsung.android.sdk.pen',
            'FountainPen',
            'pen.preload',
            'qi@$',
            'AK7',
            'A%%%',
            '^[0-9]+;[0-9]+;[0-9]+;$'
        ]

        for pattern in metadata_patterns:
            if pattern in text or (pattern.startswith('^') and re.match(pattern, text)):
                return True
        return False

    def extract_strokes_comprehensive(self):
        """Extract all stroke data using multiple methods"""
        if not self.data:
            return

        all_strokes = []

        # Method 1: Sequential coordinate pairs (most reliable)
        sequential_strokes = self._extract_sequential_strokes()
        all_strokes.extend(sequential_strokes)

        # Method 2: Pattern-based strokes
        pattern_strokes = self._extract_pattern_strokes()
        all_strokes.extend(pattern_strokes)

        # Method 3: Region-based strokes
        region_strokes = self._extract_region_strokes()
        all_strokes.extend(region_strokes)

        # Method 4: Advanced coordinate sequences
        advanced_strokes = self._extract_advanced_coordinates()
        all_strokes.extend(advanced_strokes)

        # Remove duplicates and organize
        unique_strokes = self._deduplicate_strokes(all_strokes)
        self.decoded_content['strokes'] = unique_strokes

    def _extract_sequential_strokes(self):
        """Extract strokes from sequential coordinate data"""
        strokes = []

        # Scan for coordinate sequences
        i = 0
        while i < len(self.data) - 8:
            try:
                # Try to read 4 uint16 values (x1,y1,x2,y2)
                vals = struct.unpack('<HHHH', self.data[i:i+8])

                # Check if these look like screen coordinates
                if all(10 < v < 2000 for v in vals):
                    # Found potential coordinate pair, expand stroke
                    stroke_coords = [(vals[0], vals[1]), (vals[2], vals[3])]
                    j = i + 8

                    # Continue reading coordinate pairs
                    while j + 4 <= len(self.data):
                        try:
                            x, y = struct.unpack('<HH', self.data[j:j+4])
                            if 10 < x < 2000 and 10 < y < 2000:
                                stroke_coords.append((x, y))
                                j += 4
                            else:
                                break
                        except:
                            break

                    if len(stroke_coords) >= 2:
                        strokes.append({
                            'type': 'sequential',
                            'coordinates': stroke_coords,
                            'point_count': len(stroke_coords),
                            'start_offset': hex(i),
                            'end_offset': hex(j),
                            'data_span': j - i,
                            'confidence': 'high'
                        })
                    i = j
                else:
                    i += 2
            except:
                i += 1

        return strokes

    def _extract_pattern_strokes(self):
        """Extract strokes based on discovered patterns"""
        strokes = []

        # Known stroke regions based on analysis
        stroke_regions = [
            (0x280, 0x290),   # Region with coordinate pairs
            (0x100, 0x120),   # Another potential stroke region
            (0x460, 0x4a0),   # Float coordinate region
        ]

        for start, end in stroke_regions:
            if start < len(self.data):
                region_data = self.data[start:min(end, len(self.data))]
                strokes.extend(self._parse_stroke_region(region_data, start, 'pattern_based'))

        return strokes

    def _extract_region_strokes(self):
        """Extract strokes from specific regions with high coordinate density"""
        strokes = []

        # Analyze data in 64-byte chunks for coordinate density
        chunk_size = 64
        for i in range(0, len(self.data), chunk_size):
            chunk = self.data[i:i+chunk_size]
            coords = self._find_coordinates_in_chunk(chunk, i)

            if len(coords) >= 4:  # Threshold for stroke region
                stroke_coords = self._organize_coordinates(coords)
                if len(stroke_coords) >= 2:
                    strokes.append({
                        'type': 'region_based',
                        'coordinates': stroke_coords,
                        'point_count': len(stroke_coords),
                        'region_start': hex(i),
                        'region_end': hex(i + chunk_size),
                        'confidence': 'medium'
                    })

        return strokes

    def _extract_advanced_coordinates(self):
        """Extract coordinates using advanced pattern recognition"""
        strokes = []

        # Look for coordinate patterns in different formats
        i = 0
        while i < len(self.data) - 16:
            # Try different coordinate formats
            formats = [
                ('<HHHH', 8),   # 4 uint16
                ('<ffffff', 24), # 6 floats
                ('<IIII', 16),   # 4 uint32
            ]

            for fmt, size in formats:
                if i + size <= len(self.data):
                    try:
                        values = struct.unpack(fmt, self.data[i:i+size])

                        # Check if values look like coordinates
                        coord_pairs = []
                        for j in range(0, len(values), 2):
                            if j + 1 < len(values):
                                x, y = values[j], values[j+1]
                                if self._is_valid_coordinate(x) and self._is_valid_coordinate(y):
                                    coord_pairs.append((x, y))

                        if len(coord_pairs) >= 2:
                            strokes.append({
                                'type': f'advanced_{fmt}',
                                'coordinates': coord_pairs,
                                'point_count': len(coord_pairs),
                                'offset': hex(i),
                                'format': fmt,
                                'confidence': 'medium'
                            })
                            i += size
                            break
                    except:
                        continue
                else:
                    i += 1
                    break
            else:
                i += 1

        return strokes

    def _find_coordinates_in_chunk(self, chunk, base_offset):
        """Find coordinate-like values in a data chunk"""
        coords = []

        for i in range(0, len(chunk) - 2, 2):
            try:
                val = struct.unpack('<H', chunk[i:i+2])[0]
                if 10 < val < 2000:
                    coords.append({
                        'value': val,
                        'offset': base_offset + i,
                        'local_offset': i
                    })
            except:
                continue

        return coords

    def _organize_coordinates(self, coords):
        """Organize scattered coordinates into (x,y) pairs"""
        if len(coords) < 2:
            return []

        # Sort by offset
        coords_sorted = sorted(coords, key=lambda x: x['offset'])

        # Create coordinate pairs
        pairs = []
        i = 0
        while i < len(coords_sorted) - 1:
            curr = coords_sorted[i]
            next_coord = coords_sorted[i + 1]

            # Check if coordinates are close (forming a pair)
            if next_coord['offset'] - curr['offset'] <= 4:
                pairs.append((curr['value'], next_coord['value']))
                i += 2
            else:
                i += 1

        return pairs

    def _parse_stroke_region(self, region_data, base_offset, stroke_type):
        """Parse a specific region for stroke data"""
        strokes = []

        # Try to extract coordinate pairs
        coords = self._find_coordinates_in_chunk(region_data, base_offset)
        if len(coords) >= 4:
            stroke_coords = self._organize_coordinates(coords)
            if len(stroke_coords) >= 2:
                strokes.append({
                    'type': stroke_type,
                    'coordinates': stroke_coords,
                    'point_count': len(stroke_coords),
                    'region_offset': hex(base_offset),
                    'confidence': 'high'
                })

        return strokes

    def _is_valid_coordinate(self, val):
        """Check if a value is a valid screen coordinate"""
        try:
            return isinstance(val, (int, float)) and 10 < val < 5000
        except:
            return False

    def _deduplicate_strokes(self, strokes):
        """Remove duplicate strokes and organize by confidence"""
        # Group by confidence level
        high_conf = [s for s in strokes if s.get('confidence') == 'high']
        medium_conf = [s for s in strokes if s.get('confidence') == 'medium']
        low_conf = [s for s in strokes if s.get('confidence') != 'high' and s.get('confidence') != 'medium']

        # Remove exact duplicates
        unique_strokes = []
        seen_coords = set()

        for stroke in high_conf + medium_conf + low_conf:
            coord_tuple = tuple(stroke['coordinates'])
            if coord_tuple not in seen_coords and len(coord_tuple) >= 2:
                seen_coords.add(coord_tuple)
                unique_strokes.append(stroke)

        return unique_strokes

    def extract_metadata(self):
        """Extract file metadata"""
        if not self.data:
            return

        metadata = {}

        # Extract filename info
        filename = os.path.basename(self.note_file_path)
        basename = os.path.splitext(filename)[0]

        # Extract date from filename
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

        self.decoded_content['metadata'] = metadata

    def decode_complete(self):
        """Run complete decoding process"""
        if not self.load_data():
            return None

        self.extract_metadata()
        self.parse_file_structure()
        self.extract_text_content_advanced()
        self.extract_strokes_comprehensive()

        return self.decoded_content

    def print_detailed_report(self):
        """Print comprehensive report"""
        content = self.decode_complete()
        if not content:
            print("❌ Failed to decode note")
            return

        print("🎯 ADVANCED SAMSUNG NOTES DECODER")
        print("=" * 80)

        # Metadata
        metadata = content['metadata']
        print(f"\n📋 METADATA:")
        print("-" * 40)
        print(f"Title: {metadata.get('title', 'Unknown')}")
        print(f"Created: {metadata.get('created_date', 'Unknown')}")
        print(f"UUIDs: {', '.join(metadata.get('uuids', []))}")

        # Format Info
        format_info = content.get('format_info', {})
        if format_info:
            print(f"\n🔧 FORMAT STRUCTURE:")
            print("-" * 40)
            for key, info in format_info.items():
                print(f"{key}: {info.get('value', 'N/A')} at {info.get('offset', 'N/A')}")

        # Text Content
        text_content = content.get('text_content', [])
        print(f"\n📝 TEXT CONTENT ({len(text_content)} segments):")
        print("-" * 40)
        for i, text in enumerate(text_content, 1):
            print(f"{i}. [{text['type']}] {text['content']} (offset: {text.get('offset', 'N/A')})")

        # Stroke Content
        strokes = content.get('strokes', [])
        print(f"\n✏️  STROKE CONTENT ({len(strokes)} strokes):")
        print("-" * 40)

        total_points = 0
        for i, stroke in enumerate(strokes, 1):
            points = stroke.get('coordinates', [])
            total_points += len(points)
            print(f"Stroke {i}: {len(points)} points")
            print(f"  Type: {stroke.get('type', 'unknown')}")
            print(f"  Confidence: {stroke.get('confidence', 'unknown')}")
            print(f"  Offset: {stroke.get('start_offset', stroke.get('region_offset', 'N/A'))}")
            print(f"  Points: {points[:6]}{'...' if len(points) > 6 else ''}")
            print()

        print(f"📊 STROKE SUMMARY:")
        print(f"Total strokes: {len(strokes)}")
        print(f"Total points: {total_points}")
        print(f"Average points per stroke: {total_points/len(strokes):.1f}" if strokes else "N/A")

        # Export data
        self.export_decoded_data()

    def export_decoded_data(self):
        """Export decoded data to JSON"""
        try:
            output_file = f"decoded_{os.path.splitext(os.path.basename(self.note_file_path))[0]}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.decoded_content, f, indent=2, ensure_ascii=False)
            print(f"💾 Decoded data exported to: {output_file}")
        except Exception as e:
            print(f"❌ Failed to export: {e}")

def main():
    note_folder = "notePnote"

    if not os.path.exists(note_folder):
        print("❌ Error: notePnote folder not found")
        return

    note_files = [f for f in os.listdir(note_folder) if f.endswith('.note')]

    if not note_files:
        print("❌ No note files found")
        return

    for note_file in note_files:
        note_path = os.path.join(note_folder, note_file)
        print(f"\n{'='*80}")
        print(f"DECODING: {note_file}")
        print(f"{'='*80}")

        decoder = AdvancedStrokeDecoder(note_path)
        decoder.print_detailed_report()

if __name__ == "__main__":
    main()