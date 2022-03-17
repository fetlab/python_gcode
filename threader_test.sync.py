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
init_notebook_mode(connected=True)
#suppress scientific notation
np.set_printoptions(suppress=True, precision=2)


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
from parsers import cura4
from threader import TLayer, Threader, GCodeException
page_wide()

#Attempt to reload modules automatically
# %load_ext autoreload
# %autoreload 2
# %aimport -rich
# %aimport -Geometry3D

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
gc = stepsobj49.gcode()

# %%
stepsobj49.printer.gcode(gc)

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
