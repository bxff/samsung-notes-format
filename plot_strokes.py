#!/usr/bin/env python3
"""
Quick plot of extracted stroke bounding boxes from Samsung Notes .sdocx file
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Stroke data extracted from sdocx_extractor.py
strokes = [
    {
        "uuid": "4367476a-a480-11f0-a066-bfbb6cd89211",
        "left": 602, "top": 309, "right": 639, "bottom": 993,
        "binary_size": 2827
    },
    {
        "uuid": "845599fe-a497-11f0-9d98-9f0adfe9fa71",
        "left": 766, "top": 291, "right": 804, "bottom": 944,
        "binary_size": 4699
    },
    {
        "uuid": "87af17b8-a499-11f0-819d-931efd286e76",
        "left": 991, "top": 317, "right": 1059, "bottom": 891,
        "binary_size": 2551
    }
]

# Page dimensions (from test file)
PAGE_WIDTH = 1440
PAGE_HEIGHT = 4072

# Create figure
fig, ax = plt.subplots(1, 1, figsize=(10, 12))

# Plot each stroke bounding box
colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
for i, stroke in enumerate(strokes):
    color = colors[i % len(colors)]

    # Calculate width and height
    width = stroke['right'] - stroke['left']
    height = stroke['bottom'] - stroke['top']

    # Create rectangle
    rect = patches.Rectangle(
        (stroke['left'], stroke['top']),
        width, height,
        linewidth=2,
        edgecolor=color,
        facecolor=color,
        alpha=0.3
    )
    ax.add_patch(rect)

    # Add label
    label = f"Stroke {i+1}\n{stroke['binary_size']} bytes"
    ax.text(
        stroke['left'] + width/2,
        stroke['top'] + height/2,
        label,
        ha='center',
        va='center',
        fontsize=9,
        color='black',
        weight='bold'
    )

# Set limits and labels
ax.set_xlim(0, PAGE_WIDTH)
ax.set_ylim(PAGE_HEIGHT, 0)  # Flip y-axis (top to bottom)
ax.set_xlabel('X Position (pixels)', fontsize=12)
ax.set_ylabel('Y Position (pixels)', fontsize=12)
ax.set_title('Samsung Notes - Extracted Stroke Bounding Boxes\n"ThisIsTheTitle_251009_042302.sdocx"', fontsize=14, weight='bold')

# Add grid
ax.grid(True, alpha=0.3, linestyle='--')

# Add page boundary
ax.plot([0, PAGE_WIDTH, PAGE_WIDTH, 0, 0],
        [0, 0, PAGE_HEIGHT, PAGE_HEIGHT, 0],
        'k-', linewidth=1, alpha=0.5)

plt.tight_layout()
plt.savefig('stroke_bounding_boxes.png', dpi=150, bbox_inches='tight')
print("Plot saved as: stroke_bounding_boxes.png")
