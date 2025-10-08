#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import struct
import matplotlib.pyplot as plt
import numpy as np

class SimpleStrokeDisplay:
    def __init__(self, note_file_path):
        self.note_file_path = note_file_path
        self.data = None
        self.strokes = []

    def load_data(self):
        """Load binary data"""
        try:
            with open(self.note_file_path, 'rb') as f:
                self.data = f.read()
            return True
        except Exception as e:
            print(f"Error loading file: {e}")
            return False

    def extract_all_coordinates(self):
        """Extract all coordinate-like data"""
        if not self.data:
            return

        coordinates = []

        # Method 1: uint16 coordinate pairs
        i = 0
        while i < len(self.data) - 4:
            try:
                x, y = struct.unpack('<HH', self.data[i:i+4])

                # Check if reasonable screen coordinates
                if 0 <= x <= 5000 and 0 <= y <= 5000:
                    # Continue collecting coordinates for a stroke
                    stroke_coords = [(x, y)]
                    j = i + 4

                    while j + 4 <= len(self.data):
                        try:
                            x2, y2 = struct.unpack('<HH', self.data[j:j+4])
                            if 0 <= x2 <= 5000 and 0 <= y2 <= 5000:
                                stroke_coords.append((x2, y2))
                                j += 4
                            else:
                                break
                        except:
                            break

                    if len(stroke_coords) >= 2:
                        # Calculate stroke dimensions to filter out noise
                        x_vals = [c[0] for c in stroke_coords]
                        y_vals = [c[1] for c in stroke_coords]
                        x_span = max(x_vals) - min(x_vals)
                        y_span = max(y_vals) - min(y_vals)

                        # Only keep strokes with reasonable dimensions
                        if (x_span > 2 or y_span > 2) and len(stroke_coords) <= 100:
                            self.strokes.append({
                                'coordinates': stroke_coords,
                                'offset': hex(i),
                                'point_count': len(stroke_coords),
                                'dimensions': (x_span, y_span)
                            })
                        i = j
                    else:
                        i += 2
                else:
                    i += 2
            except:
                i += 1

        # Method 2: Look for float coordinates
        i = 0
        while i < len(self.data) - 8:
            try:
                coords = []
                for j in range(0, min(24, len(self.data)-i), 4):
                    if i + j + 4 <= len(self.data):
                        val = struct.unpack('<f', self.data[i+j:i+j+4])[0]
                        if 10 < val < 5000:
                            coords.append(val)
                        else:
                            break

                if len(coords) >= 4 and len(coords) % 2 == 0:
                    stroke_coords = []
                    for k in range(0, len(coords), 2):
                        if k+1 < len(coords):
                            stroke_coords.append((int(coords[k]), int(coords[k+1])))

                    if len(stroke_coords) >= 2:
                        # Check if this stroke is different from existing ones
                        is_duplicate = False
                        for existing_stroke in self.strokes:
                            if existing_stroke['coordinates'] == stroke_coords:
                                is_duplicate = True
                                break

                        if not is_duplicate:
                            x_vals = [c[0] for c in stroke_coords]
                            y_vals = [c[1] for c in stroke_coords]
                            x_span = max(x_vals) - min(x_vals)
                            y_span = max(y_vals) - min(y_vals)

                            if x_span > 5 or y_span > 5:
                                self.strokes.append({
                                    'coordinates': stroke_coords,
                                    'offset': hex(i),
                                    'point_count': len(stroke_coords),
                                    'dimensions': (x_span, y_span),
                                    'type': 'float'
                                })
                i += 4
            except:
                i += 1

        print(f"Found {len(self.strokes)} total strokes")

    def create_visualization(self):
        """Create visualization of all strokes"""
        if not self.strokes:
            print("No strokes to visualize")
            return

        # Create figure
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))

        # Extract filename for title
        filename = os.path.basename(self.note_file_path)
        title = os.path.splitext(filename)[0].replace('_', ' ')

        fig.suptitle(f'Samsung Notes Stroke Analysis: {title}', fontsize=16, fontweight='bold')

        # Plot 1: All strokes together
        ax1.set_title('All Pen Strokes')
        ax1.set_xlabel('X Coordinate')
        ax1.set_ylabel('Y Coordinate')
        ax1.grid(True, alpha=0.3)

        colors = plt.cm.rainbow(np.linspace(0, 1, len(self.strokes)))

        for i, stroke in enumerate(self.strokes):
            coords = stroke['coordinates']
            x_coords = [c[0] for c in coords]
            y_coords = [c[1] for c in coords]

            ax1.plot(x_coords, y_coords, 'o-', color=colors[i],
                    linewidth=2, markersize=3, alpha=0.7,
                    label=f"Stroke {i+1} ({len(coords)} pts)")

        ax1.legend(fontsize=8, loc='upper right', ncol=2)

        # Plot 2: Natural orientation (flipped Y)
        ax2.set_title('Natural Orientation (Y-axis flipped)')
        ax2.set_xlabel('X Coordinate')
        ax2.set_ylabel('Y Coordinate (flipped)')
        ax2.grid(True, alpha=0.3)

        for i, stroke in enumerate(self.strokes):
            coords = stroke['coordinates']
            x_coords = [c[0] for c in coords]
            y_coords = [-c[1] for c in coords]  # Flip Y-axis

            ax2.plot(x_coords, y_coords, 'o-', color=colors[i],
                    linewidth=2, markersize=3, alpha=0.7)

        # Plot 3: Stroke complexity
        ax3.set_title('Stroke Complexity Analysis')
        ax3.set_xlabel('Stroke Number')
        ax3.set_ylabel('Points per Stroke')

        stroke_numbers = list(range(1, len(self.strokes) + 1))
        point_counts = [stroke['point_count'] for stroke in self.strokes]

        ax3.bar(stroke_numbers, point_counts, color=colors, alpha=0.7)
        ax3.grid(True, alpha=0.3)

        # Plot 4: Statistics and info
        ax4.set_title('Stroke Statistics')
        ax4.axis('off')

        # Calculate statistics
        total_points = sum(stroke['point_count'] for stroke in self.strokes)
        avg_points = total_points / len(self.strokes)

        all_coords = [coord for stroke in self.strokes for coord in stroke['coordinates']]
        x_coords = [c[0] for c in all_coords]
        y_coords = [c[1] for c in all_coords]

        canvas_width = max(x_coords) - min(x_coords)
        canvas_height = max(y_coords) - min(y_coords)

        # Count stroke types
        uint16_count = sum(1 for s in self.strokes if s.get('type') != 'float')
        float_count = sum(1 for s in self.strokes if s.get('type') == 'float')

        stats_text = f"""STROKE ANALYSIS SUMMARY

File: {filename}
Total Strokes: {len(self.strokes)}
Total Points: {total_points}
Average Points/Stroke: {avg_points:.1f}

Canvas Dimensions:
Width: {canvas_width:.0f} pixels
Height: {canvas_height:.0f} pixels

Coordinate Ranges:
X: {min(x_coords):.0f} - {max(x_coords):.0f}
Y: {min(y_coords):.0f} - {max(y_coords):.0f}

Stroke Types:
• uint16 coordinates: {uint16_count}
• float coordinates: {float_count}

Stroke Length Distribution:
• Short (2-5 pts): {sum(1 for s in self.strokes if s['point_count'] <= 5)}
• Medium (6-15 pts): {sum(1 for s in self.strokes if 6 <= s['point_count'] <= 15)}
• Long (16+ pts): {sum(1 for s in self.strokes if s['point_count'] > 15)}

Detection Method:
Sequential coordinate scanning with
dimensional filtering to remove noise
and duplicate detection.
"""

        ax4.text(0.05, 0.95, stats_text, transform=ax4.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace')

        plt.tight_layout()

        # Save the plot
        output_file = f"strokes_{os.path.splitext(filename)[0]}.png"
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"✅ Visualization saved: {output_file}")

        # Show the plot
        plt.show()

    def print_stroke_details(self):
        """Print detailed stroke information"""
        if not self.strokes:
            print("No strokes found")
            return

        print(f"\n📝 DETAILED STROKE INFORMATION")
        print("=" * 60)

        for i, stroke in enumerate(self.strokes, 1):
            coords = stroke['coordinates']
            x_coords = [c[0] for c in coords]
            y_coords = [c[1] for c in coords]

            print(f"\nStroke {i}:")
            print(f"  Points: {len(coords)}")
            print(f"  Offset: {stroke['offset']}")
            print(f"  Type: {stroke.get('type', 'uint16')}")
            print(f"  Dimensions: {stroke['dimensions'][0]:.0f} x {stroke['dimensions'][1]:.0f} pixels")
            print(f"  Bounding box: ({min(x_coords)}, {min(y_coords)}) to ({max(x_coords)}, {max(y_coords)})")
            print(f"  Sample coordinates: {coords[:6]}{'...' if len(coords) > 6 else ''}")

        print(f"\n📊 SUMMARY:")
        print(f"Total strokes: {len(self.strokes)}")
        print(f"Total points: {sum(len(s['coordinates']) for s in self.strokes)}")
        print(f"Average points per stroke: {sum(len(s['coordinates']) for s in self.strokes) / len(self.strokes):.1f}")

    def analyze_note(self):
        """Main analysis function"""
        print("🎯 SIMPLE STROKE ANALYZER")
        print("=" * 60)

        if not self.load_data():
            return

        filename = os.path.basename(self.note_file_path)
        print(f"Analyzing: {filename}")

        self.extract_all_coordinates()
        self.print_stroke_details()

        if self.strokes:
            self.create_visualization()
        else:
            print("No strokes found to visualize")

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
        print(f"ANALYZING: {note_file}")
        print(f"{'='*80}")

        analyzer = SimpleStrokeDisplay(note_path)
        analyzer.analyze_note()

if __name__ == "__main__":
    main()