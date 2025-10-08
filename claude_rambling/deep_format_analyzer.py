#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import struct
import re
from collections import defaultdict

class DeepFormatAnalyzer:
    def __init__(self, note_file_path):
        self.note_file_path = note_file_path
        self.data = None
        self.format_structure = {}

    def load_data(self):
        """Load the binary data"""
        try:
            with open(self.note_file_path, 'rb') as f:
                self.data = f.read()
            print(f"📁 Loaded {len(self.data)} bytes from {os.path.basename(self.note_file_path)}")
            return True
        except Exception as e:
            print(f"Error loading file: {e}")
            return False

    def analyze_header_structure(self):
        """Analyze the file header to understand the format structure"""
        print("\n🔍 ANALYZING HEADER STRUCTURE")
        print("-" * 50)

        if not self.data or len(self.data) < 100:
            print("Insufficient data for header analysis")
            return

        # Parse first 100 bytes in detail
        header_data = self.data[:100]

        print("First 100 bytes (hex):")
        print(header_data.hex())

        print("\nDetailed breakdown:")
        for i in range(0, min(100, len(header_data)), 4):
            chunk = header_data[i:i+4]
            if len(chunk) == 4:
                # Try different interpretations
                as_le_uint32 = struct.unpack('<I', chunk)[0]
                as_be_uint32 = struct.unpack('>I', chunk)[0]
                as_le_float = struct.unpack('<f', chunk)[0]
                as_be_float = struct.unpack('>f', chunk)[0]

                print(f"0x{i:04x}: {chunk.hex()} | u32:{as_le_uint32} | be_u32:{as_be_uint32} | f32:{as_le_float:.6f} | be_f32:{as_be_float:.6f}")

                # Look for significant values
                if as_le_uint32 > 0 and as_le_uint32 < 10000:
                    print(f"       ^ Potential size/length: {as_le_uint32}")
                if as_le_float > 0.1 and as_le_float < 5000:
                    print(f"       ^ Potential coordinate: {as_le_float}")

    def find_repeating_patterns(self):
        """Find repeating patterns that might indicate data structures"""
        print("\n🔍 SEARCHING FOR REPEATING PATTERNS")
        print("-" * 50)

        if not self.data:
            return

        # Look for common patterns
        patterns = defaultdict(list)

        # Search for 2-byte patterns
        for i in range(len(self.data) - 2):
            pattern = self.data[i:i+2]
            patterns[pattern].append(i)

        print("Most common 2-byte patterns:")
        common_patterns = sorted(patterns.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        for pattern, positions in common_patterns:
            if len(positions) > 3:
                print(f"  {pattern.hex()}: appears {len(positions)} times at positions {[hex(p) for p in positions[:5]]}")

                # Try to interpret these patterns
                try:
                    if len(pattern) == 2:
                        val = struct.unpack('<H', pattern)[0]
                        if 10 < val < 2000:
                            print(f"    ^ As uint16: {val} (possible coordinate)")
                except:
                    pass

    def analyze_coordinate_like_data(self):
        """Find all data that looks like coordinates"""
        print("\n🔍 ANALYZING COORDINATE-LIKE DATA")
        print("-" * 50)

        if not self.data:
            return

        coordinates = []

        # Method 1: 16-bit integers
        print("Searching 16-bit integers:")
        for i in range(0, len(self.data) - 2, 2):
            try:
                val = struct.unpack('<H', self.data[i:i+2])[0]
                if 10 < val < 2000:  # Reasonable coordinate range
                    coordinates.append({
                        'offset': hex(i),
                        'value': val,
                        'type': 'uint16',
                        'raw_bytes': self.data[i:i+2].hex()
                    })
            except:
                continue

        print(f"Found {len(coordinates)} potential uint16 coordinates")

        # Method 2: 32-bit floats
        print("\nSearching 32-bit floats:")
        float_coords = []
        for i in range(0, len(self.data) - 4, 4):
            try:
                val = struct.unpack('<f', self.data[i:i+4])[0]
                if 0.1 < val < 5000:  # Reasonable coordinate range
                    float_coords.append({
                        'offset': hex(i),
                        'value': val,
                        'type': 'float32',
                        'raw_bytes': self.data[i:i+4].hex()
                    })
            except:
                continue

        print(f"Found {len(float_coords)} potential float coordinates")

        # Method 3: 32-bit integers
        print("\nSearching 32-bit integers:")
        int32_coords = []
        for i in range(0, len(self.data) - 4, 4):
            try:
                val = struct.unpack('<I', self.data[i:i+4])[0]
                if 10 < val < 5000:  # Reasonable coordinate range
                    int32_coords.append({
                        'offset': hex(i),
                        'value': val,
                        'type': 'uint32',
                        'raw_bytes': self.data[i:i+4].hex()
                    })
            except:
                continue

        print(f"Found {len(int32_coords)} potential uint32 coordinates")

        # Show samples of each type
        print("\nSample coordinates by type:")
        for coord_type, coord_list in [
            ('uint16', coordinates[:10]),
            ('float32', float_coords[:10]),
            ('uint32', int32_coords[:10])
        ]:
            if coord_list:
                print(f"\n{coord_type.upper()} samples:")
                for coord in coord_list:
                    print(f"  {coord['offset']}: {coord['value']} ({coord['raw_bytes']})")

        return coordinates, float_coords, int32_coords

    def find_stroke_sequences(self, coords_list):
        """Find sequences that might be pen strokes"""
        print("\n🔍 FINDING STROKE SEQUENCES")
        print("-" * 50)

        strokes = []

        # Group coordinates by proximity and type
        for coord_type, coords in [('uint16', coords_list)]:
            if not coords:
                continue

            print(f"\nAnalyzing {coord_type} coordinates:")

            # Sort by offset
            coords_sorted = sorted(coords, key=lambda x: int(x['offset'], 16))

            # Look for sequential patterns
            i = 0
            while i < len(coords_sorted) - 1:
                current = coords_sorted[i]
                next_coord = coords_sorted[i + 1]

                # Check if coordinates are close in memory (possible stroke)
                current_offset = int(current['offset'], 16)
                next_offset = int(next_coord['offset'], 16)

                # Look for sequences within a reasonable distance
                if next_offset - current_offset <= 16:  # Within 16 bytes
                    # Start a potential stroke
                    stroke_coords = [current['value']]
                    j = i + 1

                    # Continue collecting coordinates
                    while j < len(coords_sorted) - 1:
                        cur = coords_sorted[j]
                        nxt = coords_sorted[j + 1] if j + 1 < len(coords_sorted) else None

                        stroke_coords.append(cur['value'])

                        if nxt and int(nxt['offset'], 16) - int(cur['offset'], 16) <= 16:
                            j += 1
                        else:
                            break

                    if len(stroke_coords) >= 4:  # Minimum points for a stroke
                        strokes.append({
                            'type': coord_type,
                            'start_offset': current['offset'],
                            'coordinates': stroke_coords,
                            'point_count': len(stroke_coords),
                            'span': hex(int(coords_sorted[j]['offset'], 16) - current_offset)
                        })

                    i = j + 1
                else:
                    i += 1

        print(f"\nFound {len(strokes)} potential stroke sequences:")
        for i, stroke in enumerate(strokes, 1):
            print(f"  Stroke {i}: {stroke['point_count']} points, type {stroke['type']}")
            print(f"    Start: {stroke['start_offset']}, span: {stroke['span']}")
            print(f"    Coords: {stroke['coordinates'][:8]}{'...' if len(stroke['coordinates']) > 8 else ''}")

        return strokes

    def analyze_data_chunks(self):
        """Analyze the data in chunks to find structure"""
        print("\n🔍 ANALYZING DATA CHUNKS")
        print("-" * 50)

        if not self.data:
            return

        chunk_size = 32
        chunks = []

        for i in range(0, len(self.data), chunk_size):
            chunk = self.data[i:i+chunk_size]
            if len(chunk) == chunk_size:
                # Analyze chunk
                null_count = chunk.count(0)
                printable_count = sum(1 for b in chunk if 32 <= b <= 126)

                chunks.append({
                    'offset': hex(i),
                    'size': chunk_size,
                    'null_ratio': null_count / chunk_size,
                    'printable_ratio': printable_count / chunk_size,
                    'data': chunk.hex()
                })

        # Find interesting chunks
        print("Interesting chunks (not mostly null):")
        for chunk in chunks:
            if chunk['null_ratio'] < 0.8:  # Less than 80% null
                print(f"  {chunk['offset']}: null={chunk['null_ratio']:.2f}, printable={chunk['printable_ratio']:.2f}")
                print(f"    Data: {chunk['data'][:64]}{'...' if len(chunk['data']) > 64 else ''}")

                # Try to find patterns in this chunk
                data = bytes.fromhex(chunk['data'])
                for j in range(0, len(data), 2):
                    if j + 2 <= len(data):
                        try:
                            val = struct.unpack('<H', data[j:j+2])[0]
                            if 10 < val < 2000:
                                print(f"      Possible coord at offset {j}: {val}")
                        except:
                            pass

    def decode_samsung_format(self):
        """Try to decode Samsung's specific format"""
        print("\n🔍 DECODING SAMSUNG FORMAT SPECIFICS")
        print("-" * 50)

        if not self.data:
            return

        # Look for known Samsung markers
        samsung_markers = [
            b'com.samsung.android.sdk.pen',
            b'FountainPen',
            b'pen.preload'
        ]

        for marker in samsung_markers:
            positions = []
            start = 0
            while True:
                pos = self.data.find(marker, start)
                if pos == -1:
                    break
                positions.append(pos)
                start = pos + 1

            if positions:
                print(f"Found '{marker.decode()}' at positions: {[hex(p) for p in positions]}")

                # Analyze data around these markers
                for pos in positions:
                    print(f"\n  Analysis around {hex(pos)}:")
                    start_pos = max(0, pos - 32)
                    end_pos = min(len(self.data), pos + len(marker) + 64)
                    context = self.data[start_pos:end_pos]

                    print(f"    Context: {context[:64].hex()}...")
                    print(f"    ASCII: {[chr(b) if 32 <= b <= 126 else '.' for b in context[:64]]}")

        # Look for coordinate sequences in a different way
        print("\nSearching for coordinate pairs (x,y sequences):")
        i = 0
        coord_pairs = []

        while i < len(self.data) - 8:
            try:
                # Try to interpret as 4 uint16 values (x1,y1,x2,y2)
                if i + 8 <= len(self.data):
                    vals = struct.unpack('<HHHH', self.data[i:i+8])

                    # Check if these look like screen coordinates
                    if all(10 < v < 2000 for v in vals):
                        coord_pairs.append({
                            'offset': hex(i),
                            'coords': [(vals[0], vals[1]), (vals[2], vals[3])],
                            'raw': self.data[i:i+8].hex()
                        })
                        i += 8
                    else:
                        i += 2
                else:
                    i += 1
            except:
                i += 1

        print(f"Found {len(coord_pairs)} potential coordinate pairs:")
        for pair in coord_pairs[:10]:
            print(f"  {pair['offset']}: {pair['coords']} ({pair['raw']})")

        return coord_pairs

    def run_complete_analysis(self):
        """Run all analysis methods"""
        print("🔬 DEEP SAMSUNG NOTES FORMAT ANALYSIS")
        print("=" * 80)

        if not self.load_data():
            return

        self.analyze_header_structure()
        self.find_repeating_patterns()
        coords, float_coords, int32_coords = self.analyze_coordinate_like_data()
        strokes = self.find_stroke_sequences(coords)
        self.analyze_data_chunks()
        coord_pairs = self.decode_samsung_format()

        # Summary
        print(f"\n📊 ANALYSIS SUMMARY")
        print("-" * 50)
        print(f"File size: {len(self.data)} bytes")
        print(f"Potential coordinates found: {len(coords)} (uint16), {len(float_coords)} (float), {len(int32_coords)} (uint32)")
        print(f"Potential strokes: {len(strokes)}")
        print(f"Coordinate pairs: {len(coord_pairs)}")

        return {
            'coordinates': coords,
            'float_coords': float_coords,
            'int32_coords': int32_coords,
            'strokes': strokes,
            'coord_pairs': coord_pairs
        }

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
        print(f"DEEP ANALYSIS: {note_file}")
        print(f"{'='*80}")

        analyzer = DeepFormatAnalyzer(note_path)
        results = analyzer.run_complete_analysis()

if __name__ == "__main__":
    main()