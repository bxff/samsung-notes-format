#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import struct
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path
import numpy as np
import re

class SamsungNotesVisualizer:
    def __init__(self, note_file_path):
        self.note_file_path = note_file_path
        self.data = None
        self.strokes = []
        self.metadata = {}

    def load_data(self):
        """Load the binary data"""
        try:
            with open(self.note_file_path, 'rb') as f:
                self.data = f.read()
            return True
        except Exception as e:
            print(f"Error loading file: {e}")
            return False

    def extract_strokes_advanced(self):
        """Advanced stroke extraction looking for coordinate patterns"""
        if not self.data:
            return

        # Look for actual coordinate patterns in the data
        # Pen strokes are typically sequences of (x,y) coordinates

        strokes = []

        # Method 1: Look for patterns of float values that could be coordinates
        i = 0
        while i < len(self.data) - 16:
            try:
                # Try to extract a sequence of 4+ floats
                coords = []
                for j in range(0, 16, 4):
                    if i + j + 4 <= len(self.data):
                        val = struct.unpack('<f', self.data[i+j:i+j+4])[0]
                        # Check if it's a reasonable screen coordinate (pixels)
                        if 10 < val < 2000:  # Typical screen coordinate range
                            coords.append(val)
                        else:
                            break

                # If we found at least 4 coordinate values, it might be a stroke
                if len(coords) >= 4:
                    # Interpret as x,y pairs
                    stroke_coords = []
                    for k in range(0, len(coords)-1, 2):
                        if k+1 < len(coords):
                            stroke_coords.append([coords[k], coords[k+1]])

                    if len(stroke_coords) >= 2:
                        strokes.append({
                            'offset': hex(i),
                            'coordinates': stroke_coords,
                            'raw_values': coords
                        })
                        i += 16
                    else:
                        i += 4
                else:
                    i += 4

            except:
                i += 1

        # Method 2: Look for integer coordinate patterns
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
                            'raw_values': coords,
                            'type': 'uint16'
                        })
                        i += 8
                    else:
                        i += 2
                else:
                    i += 2

            except:
                i += 1

        # Filter and normalize strokes
        normalized_strokes = []
        for stroke in strokes:
            coords = stroke['coordinates']
            if coords and len(coords) > 1:
                # Normalize coordinates to make them more visible
                x_coords = [c[0] for c in coords]
                y_coords = [c[1] for c in coords]

                # Basic filtering to remove noise
                if (max(x_coords) - min(x_coords) > 5 and
                    max(y_coords) - min(y_coords) > 5):
                    normalized_strokes.append(stroke)

        self.strokes = normalized_strokes

    def extract_metadata(self):
        """Extract basic metadata"""
        if not self.data:
            return

        filename = os.path.basename(self.note_file_path)
        basename = os.path.splitext(filename)[0]

        # Extract title and date from filename
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
                self.metadata['date'] = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                self.metadata['title'] = basename[:date_match.start()].replace('_', ' ')
            except:
                self.metadata['date'] = "Unknown"
                self.metadata['title'] = basename
        else:
            self.metadata['date'] = "Unknown"
            self.metadata['title'] = basename

        # Extract UUIDs
        uuid_pattern = rb'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'
        uuids = re.findall(uuid_pattern, self.data)
        self.metadata['uuids'] = [uid.decode('ascii') for uid in uuids]

    def create_visualization(self):
        """Create visualization of the strokes"""
        if not self.strokes:
            print("No strokes to visualize")
            return

        # Create figure with subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle(f'Samsung Notes Analysis: {self.metadata.get("title", "Unknown")}', fontsize=16)

        # Plot 1: Raw strokes
        ax1.set_title('Pen Strokes - Raw Coordinates')
        ax1.set_xlabel('X Coordinate')
        ax1.set_ylabel('Y Coordinate')
        ax1.grid(True, alpha=0.3)

        colors = plt.cm.rainbow(np.linspace(0, 1, len(self.strokes)))
        for i, stroke in enumerate(self.strokes):
            coords = stroke['coordinates']
            if coords:
                x_coords = [c[0] for c in coords]
                y_coords = [c[1] for c in coords]
                ax1.plot(x_coords, y_coords, 'o-', color=colors[i],
                        linewidth=2, markersize=4, label=f'Stroke {i+1} (offset {stroke["offset"]})')

        ax1.legend(fontsize=8, loc='upper right')

        # Plot 2: Normalized strokes (flipped Y-axis for natural orientation)
        ax2.set_title('Pen Strokes - Normalized View')
        ax2.set_xlabel('X Coordinate')
        ax2.set_ylabel('Y Coordinate (flipped)')
        ax2.grid(True, alpha=0.3)

        for i, stroke in enumerate(self.strokes):
            coords = stroke['coordinates']
            if coords:
                x_coords = [c[0] for c in coords]
                y_coords = [-c[1] for c in coords]  # Flip Y-axis
                ax2.plot(x_coords, y_coords, 'o-', color=colors[i], linewidth=2, markersize=4)

        # Plot 3: Coordinate distribution
        ax3.set_title('Coordinate Distribution')
        ax3.set_xlabel('Stroke Index')
        ax3.set_ylabel('Coordinate Values')

        all_x = []
        all_y = []
        for stroke in self.strokes:
            coords = stroke['coordinates']
            all_x.extend([c[0] for c in coords])
            all_y.extend([c[1] for c in coords])

        if all_x and all_y:
            stroke_indices = range(len(all_x))
            ax3.scatter(stroke_indices, all_x, alpha=0.6, label='X coords', color='blue')
            ax3.scatter(stroke_indices, all_y, alpha=0.6, label='Y coords', color='red')
            ax3.legend()
            ax3.grid(True, alpha=0.3)

        # Plot 4: Stroke statistics
        ax4.set_title('Stroke Statistics')
        ax4.axis('off')

        stats_text = f"""File Information:
Title: {self.metadata.get('title', 'Unknown')}
Date: {self.metadata.get('date', 'Unknown')}
File Size: {len(self.data) if self.data else 0} bytes

Stroke Analysis:
Total Strokes: {len(self.strokes)}
Total Points: {sum(len(s['coordinates']) for s in self.strokes)}
Avg Points/Stroke: {np.mean([len(s['coordinates']) for s in self.strokes]) if self.strokes else 0:.1f}

Coordinate Ranges:
X: {min(all_x):.1f} - {max(all_x):.1f} (if all_x else 'N/A')
Y: {min(all_y):.1f} - {max(all_y):.1f} (if all_y else 'N/A')

UUIDs: {', '.join(self.metadata.get('uuids', [])[:2])}
"""

        ax4.text(0.1, 0.9, stats_text, transform=ax4.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace')

        plt.tight_layout()

        # Save the plot
        output_file = f"note_visualization_{os.path.splitext(os.path.basename(self.note_file_path))[0]}.png"
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Visualization saved as: {output_file}")

        # Show the plot
        plt.show()

    def print_stroke_details(self):
        """Print detailed information about extracted strokes"""
        print(f"\n📝 STROKE DETAILS FOR: {self.metadata.get('title', 'Unknown')}")
        print("=" * 70)

        if not self.strokes:
            print("No pen strokes found in this note")
            return

        for i, stroke in enumerate(self.strokes, 1):
            print(f"\n✏️  Stroke {i}:")
            print(f"   Offset: {stroke['offset']}")
            print(f"   Points: {len(stroke['coordinates'])}")
            print(f"   Coordinates: {stroke['coordinates']}")

            if stroke.get('type'):
                print(f"   Data Type: {stroke['type']}")

        print(f"\n📊 SUMMARY:")
        print(f"Total strokes: {len(self.strokes)}")
        print(f"Total coordinate points: {sum(len(s['coordinates']) for s in self.strokes)}")

    def visualize_note(self):
        """Main method to visualize the note"""
        if not self.load_data():
            return

        self.extract_metadata()
        self.extract_strokes_advanced()
        self.print_stroke_details()

        if self.strokes:
            self.create_visualization()
        else:
            print("No strokes found to visualize")

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
        print(f"VISUALIZING: {note_file}")
        print(f"{'='*80}")

        visualizer = SamsungNotesVisualizer(note_path)
        visualizer.visualize_note()

if __name__ == "__main__":
    main()