#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import struct
import re
import json
from collections import defaultdict

class UltimateStrokeAnalyzer:
    def __init__(self, note_file_path):
        self.note_file_path = note_file_path
        self.data = None
        self.analysis = {
            'format_structure': {},
            'text_content': [],
            'pen_strokes': [],
            'metadata': {},
            'stroke_statistics': {}
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

    def analyze_samsung_format_structure(self):
        """Deep analysis of Samsung's proprietary format"""
        print("🔍 ANALYZING SAMSUNG FORMAT STRUCTURE")
        print("-" * 60)

        if not self.data:
            return

        # Samsung Notes appears to use a chunk-based format
        # Let's identify the main chunks

        chunks = []
        i = 0

        while i < len(self.data) - 8:
            try:
                # Look for chunk headers (typically 4-byte size + 4-byte type)
                chunk_size = struct.unpack('<I', self.data[i:i+4])[0]
                chunk_type = struct.unpack('<I', self.data[i+4:i+8])[0]

                # Validate chunk
                if 0 < chunk_size < len(self.data) and i + chunk_size <= len(self.data):
                    chunk_data = self.data[i+8:i+8+chunk_size]

                    chunks.append({
                        'offset': hex(i),
                        'size': chunk_size,
                        'type': hex(chunk_type),
                        'type_int': chunk_type,
                        'data': chunk_data,
                        'end_offset': hex(i + 8 + chunk_size)
                    })

                    print(f"Chunk at {hex(i)}: size={chunk_size}, type={hex(chunk_type)}")

                    # Try to identify chunk type
                    if chunk_type == 0x414f5450:  # 'POTA' - Potential text area
                        print("  ^ Text chunk identified")
                        self._extract_text_from_chunk(chunk_data, i)
                    elif chunk_type == 0x50414e53:  # 'SNAP' - Potential stroke data
                        print("  ^ Stroke chunk identified")
                        self._extract_strokes_from_chunk(chunk_data, i)
                    elif chunk_size > 1000:  # Large chunk - likely main data
                        print("  ^ Large data chunk")

                    i += 8 + chunk_size
                else:
                    i += 4
            except:
                i += 1

        self.analysis['format_structure'] = {
            'chunks': chunks,
            'total_chunks': len(chunks)
        }

    def _extract_text_from_chunk(self, chunk_data, base_offset):
        """Extract text from a text chunk"""
        # Look for UTF-16 strings in the chunk
        text_segments = []

        i = 0
        while i < len(chunk_data) - 1:
            if chunk_data[i] >= 32 and chunk_data[i] <= 126 and chunk_data[i+1] == 0:
                chars = []
                j = i
                while j < len(chunk_data) - 1 and chunk_data[j] >= 32 and chunk_data[j] <= 126 and chunk_data[j+1] == 0:
                    chars.append(chr(chunk_data[j]))
                    j += 2

                if len(chars) > 1:
                    text = ''.join(chars)
                    if not self._is_pen_metadata(text):
                        text_segments.append({
                            'text': text,
                            'offset': hex(base_offset + 8 + i),
                            'method': 'utf16_chunk'
                        })
                i = j
            else:
                i += 1

        self.analysis['text_content'].extend(text_segments)

    def _extract_strokes_from_chunk(self, chunk_data, base_offset):
        """Extract strokes from a stroke chunk"""
        strokes = []

        # Stroke data typically contains coordinate sequences
        # Look for patterns of coordinate values

        i = 0
        while i < len(chunk_data) - 8:
            try:
                # Try to read stroke header (point count + data size)
                point_count = struct.unpack('<H', chunk_data[i:i+2])[0]
                data_size = struct.unpack('<H', chunk_data[i+2:i+4])[0]

                # Validate stroke
                if 2 <= point_count <= 1000 and data_size > 0 and i + 4 + data_size <= len(chunk_data):
                    stroke_data = chunk_data[i+4:i+4+data_size]

                    # Extract coordinates from stroke data
                    coords = self._parse_stroke_coordinates(stroke_data, point_count)

                    if len(coords) >= 2:
                        strokes.append({
                            'point_count': point_count,
                            'coordinates': coords,
                            'data_size': data_size,
                            'offset': hex(base_offset + 8 + i),
                            'raw_data': stroke_data[:16].hex() + '...' if len(stroke_data) > 16 else stroke_data.hex()
                        })

                    i += 4 + data_size
                else:
                    i += 2
            except:
                i += 1

        self.analysis['pen_strokes'].extend(strokes)

    def _parse_stroke_coordinates(self, stroke_data, expected_points):
        """Parse coordinates from stroke data"""
        coords = []

        # Try different coordinate formats
        formats = [
            ('<HH', 4),    # uint16 x,y pairs
            ('<ff', 8),    # float32 x,y pairs
            ('<HHHH', 8),  # uint16 with pressure data
        ]

        for fmt, point_size in formats:
            if len(stroke_data) >= expected_points * point_size:
                try:
                    parsed_coords = []
                    for i in range(0, min(expected_points * point_size, len(stroke_data)), point_size):
                        if i + point_size <= len(stroke_data):
                            if fmt == '<HH':
                                x, y = struct.unpack(fmt, stroke_data[i:i+point_size])
                            elif fmt == '<ff':
                                x, y = struct.unpack(fmt, stroke_data[i:i+point_size])
                                x, y = int(x), int(y)  # Convert floats to ints
                            elif fmt == '<HHHH':
                                x, y, pressure, _ = struct.unpack(fmt, stroke_data[i:i+point_size])

                            # Validate coordinates
                            if self._is_valid_screen_coordinate(x) and self._is_valid_screen_coordinate(y):
                                parsed_coords.append((x, y))

                    if len(parsed_coords) >= expected_points * 0.8:  # 80% match threshold
                        return parsed_coords[:expected_points]

                except:
                    continue

        return coords

    def _is_valid_screen_coordinate(self, coord):
        """Check if coordinate is valid for screen coordinates"""
        return isinstance(coord, (int, float)) and 0 <= coord <= 5000

    def _is_pen_metadata(self, text):
        """Check if text is pen metadata"""
        metadata_patterns = [
            r'com\.samsung\.android\.sdk\.pen',
            r'FountainPen',
            r'pen\.preload',
            r'^\d+;\d+;\d+;$',
            r'qi@\$',
            r'AK7',
            r'A%%%'
        ]

        for pattern in metadata_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def extract_comprehensive_strokes(self):
        """Extract strokes using comprehensive methods"""
        print("\n✏️ COMPREHENSIVE STROKE EXTRACTION")
        print("-" * 60)

        if not self.data:
            return

        all_strokes = []

        # Method 1: Scan for coordinate sequences
        sequential_strokes = self._find_sequential_coordinates()
        all_strokes.extend(sequential_strokes)

        # Method 2: Look for stroke patterns
        pattern_strokes = self._find_stroke_patterns()
        all_strokes.extend(pattern_strokes)

        # Method 3: Region-based detection
        region_strokes = self._find_stroke_regions()
        all_strokes.extend(region_strokes)

        # Filter and validate strokes
        valid_strokes = self._validate_strokes(all_strokes)

        # Analyze stroke statistics
        self._analyze_stroke_statistics(valid_strokes)

        self.analysis['pen_strokes'] = valid_strokes

        print(f"Found {len(valid_strokes)} valid strokes")

        for i, stroke in enumerate(valid_strokes[:5], 1):
            print(f"  Stroke {i}: {len(stroke['coordinates'])} points")
            print(f"    Method: {stroke.get('method', 'unknown')}")
            print(f"    Sample coords: {stroke['coordinates'][:4]}{'...' if len(stroke['coordinates']) > 4 else ''}")

        if len(valid_strokes) > 5:
            print(f"  ... and {len(valid_strokes) - 5} more strokes")

    def _find_sequential_coordinates(self):
        """Find sequential coordinate pairs"""
        strokes = []

        i = 0
        while i < len(self.data) - 8:
            try:
                # Read 4 uint16 values (x1,y1,x2,y2)
                x1, y1, x2, y2 = struct.unpack('<HHHH', self.data[i:i+8])

                # Validate as screen coordinates
                if all(self._is_valid_screen_coordinate(c) for c in [x1, y1, x2, y2]):
                    # Check if it's part of a longer sequence
                    coords = [(x1, y1), (x2, y2)]
                    j = i + 8

                    while j + 4 <= len(self.data):
                        try:
                            x, y = struct.unpack('<HH', self.data[j:j+4])
                            if self._is_valid_screen_coordinate(x) and self._is_valid_screen_coordinate(y):
                                coords.append((x, y))
                                j += 4
                            else:
                                break
                        except:
                            break

                    if len(coords) >= 2:
                        strokes.append({
                            'coordinates': coords,
                            'method': 'sequential',
                            'offset': hex(i),
                            'point_count': len(coords)
                        })
                    i = j
                else:
                    i += 2
            except:
                i += 1

        return strokes

    def _find_stroke_patterns(self):
        """Find strokes using pattern recognition"""
        strokes = []

        # Known stroke patterns in Samsung format
        stroke_markers = [
            b'\x01\x04\x04\x01',  # Common stroke header
            b'\x00\x00\x01\x00',  # Another pattern
        ]

        for marker in stroke_markers:
            pos = 0
            while True:
                pos = self.data.find(marker, pos)
                if pos == -1:
                    break

                # Try to extract stroke after marker
                if pos + 20 <= len(self.data):
                    stroke_data = self.data[pos + len(marker):pos + 20]
                    coords = self._parse_stroke_coordinates(stroke_data, 5)  # Try for 5 points

                    if len(coords) >= 2:
                        strokes.append({
                            'coordinates': coords,
                            'method': 'pattern_based',
                            'offset': hex(pos),
                            'point_count': len(coords),
                            'marker': marker.hex()
                        })

                pos += 1

        return strokes

    def _find_stroke_regions(self):
        """Find strokes in high-density coordinate regions"""
        strokes = []

        # Scan file in 64-byte chunks
        chunk_size = 64
        for i in range(0, len(self.data), chunk_size):
            chunk = self.data[i:i+chunk_size]
            coords = []

            # Find coordinates in chunk
            for j in range(0, len(chunk) - 2, 2):
                try:
                    val = struct.unpack('<H', chunk[j:j+2])[0]
                    if self._is_valid_screen_coordinate(val):
                        coords.append({
                            'value': val,
                            'offset': i + j
                        })
                except:
                    continue

            # If enough coordinates, try to organize into strokes
            if len(coords) >= 6:
                organized_coords = self._organize_coordinates(coords)
                if len(organized_coords) >= 2:
                    strokes.append({
                        'coordinates': organized_coords,
                        'method': 'region_based',
                        'region_start': hex(i),
                        'region_end': hex(i + chunk_size),
                        'point_count': len(organized_coords)
                    })

        return strokes

    def _organize_coordinates(self, coords):
        """Organize scattered coordinates into (x,y) pairs"""
        if len(coords) < 2:
            return []

        coords_sorted = sorted(coords, key=lambda x: x['offset'])
        pairs = []

        i = 0
        while i < len(coords_sorted) - 1:
            curr = coords_sorted[i]
            next_coord = coords_sorted[i + 1]

            # Check if coordinates form a pair (close in memory)
            if next_coord['offset'] - curr['offset'] <= 6:
                pairs.append((curr['value'], next_coord['value']))
                i += 2
            else:
                i += 1

        return pairs

    def _validate_strokes(self, strokes):
        """Validate and filter strokes"""
        valid_strokes = []

        for stroke in strokes:
            coords = stroke['coordinates']

            # Validation criteria
            if len(coords) < 2:
                continue

            # Check coordinate ranges
            x_coords = [c[0] for c in coords]
            y_coords = [c[1] for c in coords]

            if not all(self._is_valid_screen_coordinate(x) for x in x_coords):
                continue
            if not all(self._is_valid_screen_coordinate(y) for y in y_coords):
                continue

            # Check if stroke has reasonable dimensions
            x_range = max(x_coords) - min(x_coords)
            y_range = max(y_coords) - min(y_coords)

            if x_range < 1 or y_range < 1:
                continue

            # Avoid single-point strokes or lines that are too short
            if x_range < 5 and y_range < 5 and len(coords) == 2:
                continue

            valid_strokes.append(stroke)

        # Remove duplicates
        unique_strokes = []
        seen_coords = set()

        for stroke in valid_strokes:
            coord_key = tuple(stroke['coordinates'])
            if coord_key not in seen_coords:
                seen_coords.add(coord_key)
                unique_strokes.append(stroke)

        return unique_strokes

    def _analyze_stroke_statistics(self, strokes):
        """Analyze stroke statistics"""
        if not strokes:
            self.analysis['stroke_statistics'] = {}
            return

        total_points = sum(len(s['coordinates']) for s in strokes)
        avg_points = total_points / len(strokes)

        all_x = [c[0] for stroke in strokes for c in stroke['coordinates']]
        all_y = [c[1] for stroke in strokes for c in stroke['coordinates']]

        stats = {
            'total_strokes': len(strokes),
            'total_points': total_points,
            'average_points_per_stroke': avg_points,
            'x_range': [min(all_x), max(all_x)],
            'y_range': [min(all_y), max(all_y)],
            'methods': list(set(s.get('method', 'unknown') for s in strokes))
        }

        self.analysis['stroke_statistics'] = stats

    def extract_metadata(self):
        """Extract file metadata"""
        if not self.data:
            return

        metadata = {}

        # Extract from filename
        filename = os.path.basename(self.note_file_path)
        basename = os.path.splitext(filename)[0]

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

        self.analysis['metadata'] = metadata

    def run_ultimate_analysis(self):
        """Run the complete ultimate analysis"""
        print("🎯 ULTIMATE SAMSUNG NOTES ANALYZER")
        print("=" * 80)

        if not self.load_data():
            return None

        self.extract_metadata()
        self.analyze_samsung_format_structure()
        self.extract_comprehensive_strokes()

        return self.analysis

    def print_ultimate_report(self):
        """Print the ultimate analysis report"""
        analysis = self.run_ultimate_analysis()
        if not analysis:
            print("❌ Analysis failed")
            return

        # Metadata
        metadata = analysis.get('metadata', {})
        print(f"\n📋 NOTE METADATA:")
        print("-" * 40)
        print(f"Title: {metadata.get('title', 'Unknown')}")
        print(f"Created: {metadata.get('created_date', 'Unknown')}")
        print(f"UUIDs: {', '.join(metadata.get('uuids', []))}")

        # Format structure
        format_info = analysis.get('format_structure', {})
        print(f"\n🏗️ FORMAT STRUCTURE:")
        print("-" * 40)
        print(f"Total chunks: {format_info.get('total_chunks', 0)}")

        # Text content
        text_content = analysis.get('text_content', [])
        print(f"\n📝 TEXT CONTENT ({len(text_content)} segments):")
        print("-" * 40)
        for i, text in enumerate(text_content, 1):
            print(f"{i}. {text['text']} (offset: {text['offset']})")

        # Stroke analysis
        strokes = analysis.get('pen_strokes', [])
        stats = analysis.get('stroke_statistics', {})

        print(f"\n✏️ STROKE ANALYSIS:")
        print("-" * 40)
        print(f"Total strokes: {stats.get('total_strokes', 0)}")
        print(f"Total points: {stats.get('total_points', 0)}")
        print(f"Average points/stroke: {stats.get('average_points_per_stroke', 0):.1f}")
        print(f"X coordinate range: {stats.get('x_range', [0, 0])}")
        print(f"Y coordinate range: {stats.get('y_range', [0, 0])}")
        print(f"Detection methods: {', '.join(stats.get('methods', []))}")

        print(f"\n📊 STROKE DETAILS:")
        print("-" * 40)
        for i, stroke in enumerate(strokes[:10], 1):  # Show first 10
            coords = stroke['coordinates']
            print(f"Stroke {i}: {len(coords)} points ({stroke.get('method', 'unknown')})")
            print(f"  Sample: {coords[:3]}{'...' if len(coords) > 3 else ''}")

        if len(strokes) > 10:
            print(f"... and {len(strokes) - 10} more strokes")

        # Export
        self.export_analysis()

    def export_analysis(self):
        """Export complete analysis"""
        try:
            output_file = f"ultimate_analysis_{os.path.splitext(os.path.basename(self.note_file_path))[0]}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.analysis, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Ultimate analysis exported to: {output_file}")
        except Exception as e:
            print(f"\n❌ Export failed: {e}")

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
        print(f"ULTIMATE ANALYSIS: {note_file}")
        print(f"{'='*80}")

        analyzer = UltimateStrokeAnalyzer(note_path)
        analyzer.print_ultimate_report()

if __name__ == "__main__":
    main()