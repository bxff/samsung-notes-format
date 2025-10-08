#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import matplotlib.pyplot as plt
import numpy as np

class FinalStrokeVisualizer:
    def __init__(self, analysis_file_path):
        self.analysis_file_path = analysis_file_path
        self.analysis_data = None

    def load_analysis(self):
        """Load the analysis data"""
        try:
            with open(self.analysis_file_path, 'r', encoding='utf-8') as f:
                # Handle bytes objects in JSON
                content = f.read()
                # Replace bytes representations
                content = content.replace('"__bytes__": ', '"raw_bytes": ')
                self.analysis_data = json.loads(content)
            return True
        except Exception as e:
            print(f"Error loading analysis: {e}")
            return False

    def extract_clean_strokes(self):
        """Extract and clean stroke data"""
        if not self.analysis_data:
            return []

        strokes = self.analysis_data.get('pen_strokes', [])
        clean_strokes = []

        for stroke in strokes:
            coords = stroke.get('coordinates', [])
            if coords and len(coords) >= 2:
                # Filter out invalid coordinates
                valid_coords = []
                for x, y in coords:
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                        if 0 <= x <= 5000 and 0 <= y <= 5000:
                            valid_coords.append((x, y))

                if len(valid_coords) >= 2:
                    clean_strokes.append({
                        'coordinates': valid_coords,
                        'method': stroke.get('method', 'unknown'),
                        'point_count': len(valid_coords)
                    })

        return clean_strokes

    def create_comprehensive_visualization(self):
        """Create comprehensive visualization of all strokes"""
        strokes = self.extract_clean_strokes()

        if not strokes:
            print("No valid strokes to visualize")
            return

        print(f"🎨 Creating visualization for {len(strokes)} strokes")
        print(f"Total points: {sum(s['point_count'] for s in strokes)}")

        # Create figure with multiple views
        fig = plt.figure(figsize=(20, 15))

        # Main plot - All strokes
        ax1 = plt.subplot(2, 3, 1)
        ax1.set_title('All Pen Strokes', fontsize=14, fontweight='bold')
        ax1.set_xlabel('X Coordinate')
        ax1.set_ylabel('Y Coordinate')
        ax1.grid(True, alpha=0.3)
        ax1.set_aspect('equal')

        colors = plt.cm.rainbow(np.linspace(0, 1, len(strokes)))

        for i, stroke in enumerate(strokes):
            coords = stroke['coordinates']
            x_coords = [c[0] for c in coords]
            y_coords = [c[1] for c in coords]

            ax1.plot(x_coords, y_coords, 'o-', color=colors[i],
                    linewidth=2, markersize=3, alpha=0.8)

        # Flipped view (natural orientation)
        ax2 = plt.subplot(2, 3, 2)
        ax2.set_title('Strokes (Natural Orientation)', fontsize=14, fontweight='bold')
        ax2.set_xlabel('X Coordinate')
        ax2.set_ylabel('Y Coordinate (flipped)')
        ax2.grid(True, alpha=0.3)
        ax2.set_aspect('equal')

        for i, stroke in enumerate(strokes):
            coords = stroke['coordinates']
            x_coords = [c[0] for c in coords]
            y_coords = [-c[1] for c in coords]  # Flip Y

            ax2.plot(x_coords, y_coords, 'o-', color=colors[i],
                    linewidth=2, markersize=3, alpha=0.8)

        # Coordinate distribution
        ax3 = plt.subplot(2, 3, 3)
        ax3.set_title('Coordinate Distribution', fontsize=14, fontweight='bold')

        all_x = [c[0] for stroke in strokes for c in stroke['coordinates']]
        all_y = [c[1] for stroke in strokes for c in stroke['coordinates']]

        ax3.scatter(all_x, all_y, alpha=0.6, s=1)
        ax3.set_xlabel('X Coordinate')
        ax3.set_ylabel('Y Coordinate')
        ax3.grid(True, alpha=0.3)

        # Stroke complexity analysis
        ax4 = plt.subplot(2, 3, 4)
        ax4.set_title('Stroke Complexity', fontsize=14, fontweight='bold')

        stroke_lengths = [len(stroke['coordinates']) for stroke in strokes]
        ax4.hist(stroke_lengths, bins=20, alpha=0.7, color='skyblue', edgecolor='black')
        ax4.set_xlabel('Points per Stroke')
        ax4.set_ylabel('Number of Strokes')
        ax4.grid(True, alpha=0.3)

        # Bounding boxes
        ax5 = plt.subplot(2, 3, 5)
        ax5.set_title('Stroke Bounding Boxes', fontsize=14, fontweight='bold')
        ax5.set_xlabel('X Coordinate')
        ax5.set_ylabel('Y Coordinate')
        ax5.grid(True, alpha=0.3)
        ax5.set_aspect('equal')

        for i, stroke in enumerate(strokes):
            coords = stroke['coordinates']
            x_coords = [c[0] for c in coords]
            y_coords = [c[1] for c in coords]

            min_x, max_x = min(x_coords), max(x_coords)
            min_y, max_y = min(y_coords), max(y_coords)

            width = max_x - min_x
            height = max_y - min_y

            rect = plt.Rectangle((min_x, min_y), width, height,
                               fill=False, edgecolor=colors[i], linewidth=1, alpha=0.7)
            ax5.add_patch(rect)

        # Statistics text
        ax6 = plt.subplot(2, 3, 6)
        ax6.set_title('Stroke Statistics', fontsize=14, fontweight='bold')
        ax6.axis('off')

        # Calculate statistics
        total_points = sum(len(stroke['coordinates']) for stroke in strokes)
        avg_points = total_points / len(strokes)

        x_range = [min(all_x), max(all_x)] if all_x else [0, 0]
        y_range = [min(all_y), max(all_y)] if all_y else [0, 0]

        canvas_width = x_range[1] - x_range[0]
        canvas_height = y_range[1] - y_range[0]

        methods = list(set(stroke.get('method', 'unknown') for stroke in strokes))
        method_counts = {}
        for method in methods:
            method_counts[method] = sum(1 for s in strokes if s.get('method') == method)

        stats_text = f"""STROKE ANALYSIS SUMMARY

Total Strokes: {len(strokes)}
Total Points: {total_points}
Average Points/Stroke: {avg_points:.1f}

Canvas Dimensions:
Width: {canvas_width:.0f} pixels
Height: {canvas_height:.0f} pixels

Coordinate Ranges:
X: {x_range[0]:.0f} - {x_range[1]:.0f}
Y: {y_range[0]:.0f} - {y_range[1]:.0f}

Detection Methods:
{chr(10).join(f'  • {method}: {count} strokes' for method, count in method_counts.items())}

Stroke Length Distribution:
Short (2-5 pts): {sum(1 for s in strokes if len(s['coordinates']) <= 5)}
Medium (6-15 pts): {sum(1 for s in strokes if 6 <= len(s['coordinates']) <= 15)}
Long (16+ pts): {sum(1 for s in strokes if len(s['coordinates']) > 15)}
"""

        ax6.text(0.05, 0.95, stats_text, transform=ax6.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace')

        plt.suptitle(f'Samsung Notes - Complete Stroke Analysis\n{os.path.basename(self.analysis_file_path)}',
                    fontsize=16, fontweight='bold')

        plt.tight_layout()

        # Save the visualization
        output_file = f"stroke_visualization_{os.path.splitext(os.path.basename(self.analysis_file_path))[0]}.png"
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"✅ Visualization saved: {output_file}")

        # Show the plot
        plt.show()

        return strokes

    def print_detailed_analysis(self):
        """Print detailed stroke analysis"""
        if not self.load_analysis():
            return

        strokes = self.extract_clean_strokes()
        metadata = self.analysis_data.get('metadata', {})

        print("📊 DETAILED STROKE ANALYSIS")
        print("=" * 70)

        # Metadata
        print(f"\n📋 NOTE INFORMATION:")
        print("-" * 40)
        print(f"Title: {metadata.get('title', 'Unknown')}")
        print(f"Created: {metadata.get('created_date', 'Unknown')}")

        # Stroke summary
        print(f"\n✏️ STROKE SUMMARY:")
        print("-" * 40)
        print(f"Total strokes: {len(strokes)}")
        print(f"Total points: {sum(len(s['coordinates']) for s in strokes)}")

        if strokes:
            avg_points = sum(len(s['coordinates']) for s in strokes) / len(strokes)
            print(f"Average points per stroke: {avg_points:.1f}")

            # Coordinate ranges
            all_coords = [coord for stroke in strokes for coord in stroke['coordinates']]
            x_coords = [c[0] for c in all_coords]
            y_coords = [c[1] for c in all_coords]

            print(f"X range: {min(x_coords):.0f} - {max(x_coords):.0f}")
            print(f"Y range: {min(y_coords):.0f} - {max(y_coords):.0f}")
            print(f"Canvas size: {max(x_coords)-min(x_coords):.0f} x {max(y_coords)-min(y_coords):.0f} pixels")

        # Individual strokes
        print(f"\n📝 INDIVIDUAL STROKES:")
        print("-" * 40)

        for i, stroke in enumerate(strokes, 1):
            coords = stroke['coordinates']
            x_coords = [c[0] for c in coords]
            y_coords = [c[1] for c in coords]

            print(f"\nStroke {i}:")
            print(f"  Points: {len(coords)}")
            print(f"  Method: {stroke.get('method', 'unknown')}")
            print(f"  Bounding box: ({min(x_coords)}, {min(y_coords)}) to ({max(x_coords)}, {max(y_coords)})")
            print(f"  Dimensions: {max(x_coords)-min(x_coords):.0f} x {max(y_coords)-min(y_coords):.0f} pixels")
            print(f"  Sample coords: {coords[:4]}{'...' if len(coords) > 4 else ''}")

        return strokes

def main():
    # Find the latest analysis file
    analysis_files = [f for f in os.listdir('.') if f.startswith('ultimate_analysis_') and f.endswith('.json')]

    if not analysis_files:
        print("❌ No analysis files found. Run ultimate_stroke_analyzer.py first.")
        return

    # Use the most recent analysis file
    analysis_file = sorted(analysis_files)[-1]
    print(f"📁 Using analysis file: {analysis_file}")

    visualizer = FinalStrokeVisualizer(analysis_file)
    strokes = visualizer.print_detailed_analysis()
    visualizer.create_comprehensive_visualization()

if __name__ == "__main__":
    main()