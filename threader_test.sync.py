# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.3.4
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %%
#turn off autosave since we sync from vim
# %autosave 0
import numpy as np
from Geometry3D import Point, distance, HalfLine
#from danutil import unpickle
import pickle
import plotly.graph_objects as go
from IPython.core.display import display, HTML
import plotly
from plotly.offline import init_notebook_mode
from copy import copy, deepcopy
init_notebook_mode(connected=True)
#suppress scientific notation
np.set_printoptions(suppress=True, precision=8)


from rich.console import Console
rprint = Console(style="on #272727").print

def page_wide():
	display(HTML(
	"""
	<style>
		.container { width:100% !important; }
		.output_result { max-width:100% !important; }
		.prompt { min-width:0 !important; }
		.run_this_cell { padding:0 !important; }
		.modebar { padding-right: 250px !important; }
		.jp-OutputArea-output { background-color: #272727 !important; }
	</style>
	"""))


import threader, geometry_helpers, gcode, gcline, tlayer, util
import parsers.cura4
from parsers import cura4
from threader import TLayer, Threader, GCodeException
page_wide()

#Attempt to reload modules automatically
# %load_ext autoreload
# %autoreload 2

# %%
import random
random.random()

# %%
thread_file = '/Users/dan/r/thread_printer/stl/test1/thread_from_fusion.pickle'
gcode_file  = '/Users/dan/r/thread_printer/stl/test1/main_body.gcode'
tpath = np.array(pickle.load(open(thread_file, 'rb'))) * 10
thread_transform = [131.164, 110.421, 0]

# %%
#Fusion: smaller complex shape v1
gcode_file = '/Users/dan/r/thread_printer/stl/test2/Smaller complex shape - cura.gcode'
cura_project = '/Users/dan/r/thread_printer/stl/test2/Smaller complex shape - cura.3mf'

# %%
thread_transform = cura4.parse_3mf(cura_project)
thread_transform

# %%
#From cura4.parse_3mf(cura_project) so I don't have to run that every time
thread_transform = np.array([39.26039839, 46.27034378, 23.87050056])

#See thread_from_fusion.py to get thread path
tpath = [
		([33.7300, 17.1077, 11.4653], [56.0477, 43.4545, 11.4653]),
		([56.0477, 43.4545, 11.4653], [53.2410, 59.2656, 11.4653]),
		([53.2410, 59.2656, 11.4653], [26.9901, 69.3288, 42.0560]),
		([26.9901, 69.3288, 42.0560], [26.9901, 69.3288, 47.7410]),
]
tpath = np.array(tpath)

#Do it this way so I can add transform if needed
#tpath = np.insert(tpath, 0, [[0,0,0], tpath[0,0]], axis=0)

#Temporary fix for TODO in cura4.parse3mf
thread_transform[2] = 0

g = gcode.GcodeFile(gcode_file, layer_class=TLayer)
t = Threader(g)

#start_layer = next(layer for layer in g.layers if (layer.z + layer.layer_height) >= tpath[0][1][2])
start_layer = g.layers[56]

thread_geom = tuple([geometry_helpers.GSegment(Point(*s), Point(*e)) for s,e in tpath])

# %%

fig = go.Figure()
t.printer.bed.plot(fig)
start_layer.plot(fig, only_outline=False)
fig.add_trace(go.Scatter(**geometry_helpers.segs_xy(
	#*t.steps.flat_thread,
	*thread_geom,
	**threader.Step.style['thread'])))
t.printer.ring.plot(fig)

fig.update_layout(template='plotly_dark',# autosize=False,
		yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
		margin=dict(l=0, r=20, b=0, t=0, pad=0),
		showlegend=False,)
fig.show('notebook')

# %%
stepsobj = t.route_layer(thread_geom, start_layer)

# %%
stepsobj.plot()

# %%
stepsobj.steps[1]
# 1655377366.535135
# 1655377367.125314

# %%
id(stepsobj.steps[0].printer)

# %%
ring0 = stepsobj.steps[0].printer.ring
id(stepsobj), id(stepsobj.steps[0]), stepsobj.steps[0], id(ring0), ring0

# %%
ring0 = stepsobj.steps[0].printer.ring
ring1 = copy(ring0)
ring0, ring1

# %%
ring1.set_angle(0)
ring0, ring1

# %%
id(ring0), id(ring1)

# %%
fig = go.Figure()
stepsobj49.steps[5].plot_gcsegments(fig)
fig.update_layout(template='plotly_dark',# autosize=False,
		yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
		margin=dict(l=0, r=20, b=0, t=40, pad=0),
		showlegend=False,)

fig.show('notebook')

# %%
stepsobj49.steps[5].gcsegs[-1].gc_lines[14922]

# %%
g.lines[14920:14925]

# %%
stepsobj49.steps[2].printer.ring.initial_angle, stepsobj49.steps[2].printer.ring.angle

# %%
gc = stepsobj49.gcode()
with open('/tmp/l49.gcode', 'w') as f:
	f.write(gc.construct())


# %%
g.layers[49]


# %%
list(_)

# %%
ogc = g.layers[49].lines
rprint(ogc.summary())
sorted(ogc[set(gc._index.keys()).difference(ogc._index.keys())])

# %%
stepsobj49.steps[1].gcsegs[-1].gc_lines

# %%
stepsobj50 = t.route_layer(thread_geom, g.layers[50])
stepsobj50.plot(g.layers[49])

# %%
stepsobj60 = t.route_layer(thread_geom, g.layers[60])
stepsobj60.plot()

# %%
fig = go.Figure()
layer = g.layers[49]
layer.plot(fig, ['green'], ['green'], only_outline=False)

thread = layer.flatten_thread(thread_geom)
layer.intersect_model(thread)

fig.add_trace(go.Scatter(**geometry_helpers.segs_xy(*thread,
	marker_size=8,
	line=dict(color='red', dash='dot', width=4))))

newthread = layer.anchor_snap(thread)

fig.add_trace(go.Scatter(**geometry_helpers.segs_xy(*newthread,
	marker=dict(color='lightblue', size=8),
	line=dict(color='yellow', dash='dot', width=1))))

fig.update_layout(template='plotly_dark',# autosize=False,
		yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
		margin=dict(l=0, r=20, b=0, t=40, pad=0),
		showlegend=False,
)

fig.show('notebook')

# %%
for seg, color in zip(thread_geom, plotly.colors.qualitative.Set2):
	fig.add_trace(go.Scatter3d(**geometry_helpers.segs_xyz(seg, mode='lines',
		line=dict(color=color, dash='dot', width=4))))

fig.update_layout(template='plotly_dark',# autosize=False,
		yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
		margin=dict(l=0, r=20, b=0, t=40, pad=0),
		showlegend=False,
)
fig.update_scenes(
		camera=dict(
			projection={'type': 'orthographic'},
			# eye={'x': 0, 'y': 1, 'z': 0},
		),
)

fig.show('notebook')


# %%
fig = go.Figure()
g.layers[49].plot(fig, only_outline=False)
fig.update_layout(
		yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
)
fig.update_scenes(
		camera=dict(
			projection={'type': 'orthographic'},
			# eye={'x': 0, 'y': 1, 'z': 0},
		),
)
fig.show('notebook')
fig.write_image('/tmp/slice49.svg')

# %%
import zipfile
import xml.etree.ElementTree as ET
import numpy as np

namespace = {
		"3mf": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02",
		"m"  : "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
}

filename = '/Users/dan/data/projects/research/thread_printer/stl/test2/Smaller complex shape v1 - cura.3mf'
archive = zipfile.ZipFile(filename, "r")
mfroot = ET.parse(archive.open("3D/3dmodel.model"))

# %%
mins = [float( 'inf')]*3
maxs = [float('-inf')]*3
for vertex in mfroot.findall("./3mf:resources/3mf:object/3mf:mesh/3mf:vertices/3mf:vertex", namespace):
	vals = list(map(float, [vertex.get(a) for a in 'xyz']))
	mins = [min(old, new) for old, new in zip(mins, vals)]
	maxs = [max(old, new) for old, new in zip(maxs, vals)]
mins, maxs

# %%
obj_bb = {}
for obj in mfroot.findall("./3mf:resources/3mf:object", namespace):
	mins = [float( 'inf')]*3
	maxs = [float('-inf')]*3
	for vertex in obj.findall("./3mf:mesh/3mf:vertices/3mf:vertex", namespace):
		vals = list(map(float, [vertex.get(a) for a in 'xyz']))
		mins = [min(old, new) for old, new in zip(mins, vals)]
		maxs = [max(old, new) for old, new in zip(maxs, vals)]
	if mins[0] < float('inf') or maxs[0] > float('-inf'):
		obj_bb[int(obj.get('id'))] = {'min':np.array(mins), 'max':np.array(maxs),
				'size': np.array(maxs)*2}
		print(f"Obj ID {obj.get('id')}:", mins, maxs)

#Swap Y/Z transform for individual objects, but not for grouped objects
for c in mfroot.findall('./3mf:resources/3mf:object/3mf:components/3mf:component', namespace):
	tr = np.fromstring(c.get('transform'), dtype=float, sep=' ')[-3:]
	tr[1], tr[2] = tr[2], tr[1]
	obj_bb[int(c.get('objectid'))]['tr'] = tr

for c in mfroot.findall('./3mf:build/3mf:item', namespace):
	obj_bb.setdefault(int(c.get('objectid')), {})['tr'] = np.fromstring(c.get('transform'), dtype=float, sep=' ')[-3:]

obj_bb

# %%
objects = {}
for obj in mfroot.findall("./3mf:resources/3mf:object", namespace):
	verts = []
	for vertex in obj.findall("./3mf:mesh/3mf:vertices/3mf:vertex", namespace):
		verts.append(list(map(float, [vertex.get(a) for a in 'xyz'])))
	if verts:
		objects[int(obj.get('id'))] = np.array(verts)

# %%
obj_bb[2]['tr']

# %%
#The last vertex is the start point
verts = objects[2][-66:]
f3 = go.Figure()
f3.add_trace(go.Scatter3d(x=verts[:,0], y=verts[:,1],
	z=verts[:,2], mode='markers', marker=dict(color='yellow', symbol='circle',
		size=2)))
f3.update_layout(template='plotly_dark',# autosize=False,
		yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
		margin=dict(l=0, r=20, b=0, t=0, pad=0),
		showlegend=False,)
f3.show('notebook')

# %%
# Figuring out Fusion coordinates vs 3MF vs Gcode

# %%
#These are the coordinates of each vertex of the thread in Fusion
tp = np.array([
		[28.7300,  7.1077, 11.4653],
		[51.0477, 33.4545, 11.4653],
		[48.2410, 49.2656, 11.4653],
		[21.9901, 59.3288, 42.0560],
		[21.9901, 59.3288, 47.7410],
])
tp_size = tp.max(axis=0) - tp.min(axis=0)
tp_cent = tp - tp.min(axis=0) - tp_size/2

# %%
#This is the center of the circle of vertices (from the 3mf file), which make up
# the starting end of the thread pipe object
threadstart = np.unique(verts, axis=0).mean(axis=0)

# %%
#This is the correct coordinate for the Cura 3mf file, as illustrated by importing
# it into Fusion and checking the coordinates
threadstart3mf = threadstart + obj_bb[2]['tr'] + obj_bb[3]['tr']

# %%
#This is the approximate vertex of the start point of the thread in GCode

#Gcode lines that make the face where the thread connects on layer 56
#start_layer.lines[21789:21791]
x1, x2 = 32.618, 35.543
y1, y2 = 80.587, 81.443

#Should be approx coordinate for start of thread in gcode
gthreadstart = x1 + (x2-x1)/2, y1 + (y2-y1)/2, tp[0][2]

# %%
np.vstack([threadstart, threadstart3mf, gthreadstart, tp[0]])

# %%
verts3mf = np.unique(objects[2][::500,:2], axis=0)
tp_cent_trans = tp_cent + obj_bb[2]['tr'] + obj_bb[3]['tr'] - [0, 5.75, 0]

fig_t = go.Figure()

#GCode
start_layer.plot(fig_t, only_outline=False)

#Translated object from 3MF
trans_3mf = (objects[1] + obj_bb[3]['tr'])[::10,:2]
fig_t.add_trace(go.Scatter(name='trans_3mf', x=trans_3mf[:,0], y=trans_3mf[:,1], mode='markers'))

# fig_t.add_trace(go.Scatter(name='tp', x=tp[:,0], y=tp[:,1]))
# fig_t.add_trace(go.Scatter(name='tp_cent', x=tp_cent[:,0], y=tp_cent[:,1]))
# fig_t.add_trace(go.Scatter(name='verts3mf', x=verts3mf[:,0], y=verts3mf[:,1], mode='markers'))
fig_t.add_trace(go.Scatter(name='tp_cent_trans', x=tp_cent_trans[:,0], y=tp_cent_trans[:,1]))


fig_t.update_layout(template='plotly_dark',# autosize=False,
		yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
		margin=dict(l=0, r=20, b=0, t=0, pad=0),
		showlegend=False,)
fig_t.show('notebook')
