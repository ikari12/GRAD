"""Generate Supplementary Table S1 as a PNG image for Figshare upload."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Data from sport_variance.txt
data = {
    'Metric': [
        'GACD (cardiac drift)', 'Gradient sensitivity', 'Speed sensitivity',
        'GACD (cardiac drift)', 'Gradient sensitivity', 'Speed sensitivity',
    ],
    'Sport': ['Cycling', 'Cycling', 'Cycling', 'Mountain bike', 'Mountain bike', 'Mountain bike'],
    'K': [94, 94, 94, 10, 10, 10],
    'N': [1647, 1647, 1647, 172, 172, 172],
    'ICC(1,1)': [0.215, 0.377, 0.470, 0.076, 0.017, 0.215],
    'SB(k=5)': [0.703, 0.907, 0.874, -0.003, 0.253, 0.426],
    '%Person': [21.5, 37.7, 47.0, 7.6, 1.7, 21.5],
    '%Route': [0.0, 0.0, 3.1, 0.0, 0.0, 0.0],
    '%Occasion': [78.5, 62.3, 49.8, 92.4, 98.3, 78.5],
}

fig, ax = plt.subplots(figsize=(14, 5))
ax.axis('off')
ax.set_title('Supplementary Table S1. Sport-specific variance decomposition\nfor the high-engagement subset',
             fontsize=13, fontweight='bold', pad=20, loc='left')

columns = ['Sport', 'Metric', 'K', 'N', 'ICC(1,1)', 'SB(k=5)', '%Person', '%Route', '%Occasion']
cell_data = []
for i in range(len(data['Metric'])):
    row = [data[col][i] for col in columns]
    cell_data.append(row)

# Add running row
cell_data.append(['Running', '—', 3, 47, '—', '—', '—', '—', '—'])

table = ax.table(cellText=cell_data, colLabels=columns, loc='center', cellLoc='center')
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1.0, 1.8)

# Style header
for j in range(len(columns)):
    table[0, j].set_facecolor('#2c3e50')
    table[0, j].set_text_props(color='white', fontweight='bold')

# Alternate row colors
for i in range(1, len(cell_data) + 1):
    color = '#f0f4f8' if i % 2 == 0 else 'white'
    for j in range(len(columns)):
        table[i, j].set_facecolor(color)

# Add footnote
fig.text(0.05, 0.02,
         'Note: Running subsample (N = 47 workouts, 3 users with ≥5 sessions) was insufficient for stable ICC estimation.\n'
         'Negative SB(k=5) for MTB GACD reflects near-zero split-half correlation in a small sample (K = 10).',
         fontsize=8, style='italic', va='bottom')

plt.tight_layout()
plt.savefig('/Users/hisashi/Desktop/Workspace/GRAD/paper/tableS1_sport_variance.png', dpi=300, bbox_inches='tight',
            facecolor='white', edgecolor='none')
print("Saved: tableS1_sport_variance.png")
