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
import gcode
import numpy as np
from Geometry3D import Point
#from danutil import unpickle
import pickle
from importlib import reload
import plotly.graph_objects as go
from IPython.core.display import display, HTML
from plotly.offline import init_notebook_mode
init_notebook_mode(connected=True)
#suppress scientific notation
np.set_printoptions(suppress=True, precision=2)


# %%
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


# %%
import threader, geometry_helpers, gcode
from parsers import cura4
reload(geometry_helpers)
reload(threader)
reload(cura4)
reload(gcode)
from threader import TLayer, Threader, GCodeException
page_wide()

# %%
thread_file = '/Users/dan/r/thread_printer/stl/test1/thread_from_fusion.pickle'
tpath = np.array(pickle.load(open(thread_file, 'rb'))) * 10
thread_transform = [131.164, 110.421, 0]
tpath += [thread_transform, thread_transform]

thread_geom = tuple([geometry_helpers.GSegment(Point(*s), Point(*e)) for s,e in tpath])
g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode', layer_class=TLayer)
t = Threader(g)

# %%
stepsobj49 = t.route_layer(thread_geom, g.layers[49])
stepsobj49.plot()

# %%
stepsobj50 = t.route_layer(thread_geom, g.layers[50])
stepsobj50.plot(g.layers[49])

# %%
stepsobj60 = t.route_layer(thread_geom, g.layers[60])

# %%
stepsobj60.plot()

# %%
import threader, geometry_helpers, parsers.cura4
import plotly
reload(parsers.cura4)
reload(geometry_helpers)
reload(threader)
from threader import TLayer, Threader

g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode',
		layer_class=TLayer)

fig = go.Figure()
for i in range(48,51):
	g.layers[i].plot(fig, ['green'], ['green'], plot3d=True)

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
for layer in g.layers:
	layer.add_geometry()
	if layer.geometry.planes.bottom.z <= thread_geom[0].end_point.z <= layer.geometry.planes.top.z:
		print(layer)
		print(layer.geometry.planes.bottom, layer.geometry.planes.top)

# %%
g.layers[49].anchors(thread_geom[-3])

# %%
for tseg in g.layers[49]._isecs:
	print(tseg)
	print(g.layers[49]._isecs[tseg]['isec_segs'])
	print('-----')

	#81.89, 115.797 -> 84.661, 113.026

# %%
"""
For layer 49 at z = 10
Segments:
 0. ( 50.14,  74.74, -0.00), ( 83.34, 114.49,  9.97)
 1. ( 83.34, 114.49,  9.97), (147.50, 114.49,  9.97)
 2. (147.50, 114.49,  9.97), (159.14, 114.49, 16.69) -> exits layer
 3. (159.14, 114.49, 16.69), (159.05, 128.12, 61.18)

Anchor at step 2 for seg 0 is ( 83.27, 114.42)
Anchor at step 4 for seg 1 is (143.13, 114.49)
Anchor at step 6 for seg 2 is (154.48, 114.49)

TODO next: find out what's happening with segment 2 and its exit from the
layer; why is there a step 6?
"""

# %%
from rich.console import Console
blue_console = Console(style="on #272727")
blue_console.print("I'm blue. Da ba dee da ba di. 123 {stuff}")
