# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.13.3
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %%
# #%pylab
import pickle
import numpy as np
import thread, gcode, gclayer
from Geometry3D import Segment, Point, intersection, Renderer
from parsers import cura4
from importlib import reload
import plotly.graph_objects as go
from plotly.offline import plot, iplot, init_notebook_mode
from IPython.core.display import display, HTML
init_notebook_mode(connected=True)

#suppress scientific notation
np.set_printoptions(suppress=True, precision=2)

# %%
#turn off autosave since we sync from vim
%autosave 0

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
	</style>
	"""))

# %%
reload(thread); reload(gcode); reload(cura4); reload(gclayer)

# %%
g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode')
thread.layers_to_geom(g)

# %%
#units from fusion are always in cm, so we need to convert to mm
tpath = np.array(pickle.load(open('/Users/dan/r/thread_printer/stl/test1/thread_from_fusion.pickle', 'rb'))) * 10
thread_transform = [131.164, 110.421, 0]
tpath += [thread_transform, thread_transform]
thread_geom = [Segment(Point(*s), Point(*e)) for s,e in tpath]

# %%
def xyz(*args, **kwargs):
	"""Separate the x, y, and z attributes of the arguments into separate lists.
	Return a dict with those as well as any kwargs."""
	x, y, z = [], [], []
	for a in args:
		x.append(a.x if a is not None else None)
		y.append(a.y if a is not None else None)
		z.append(a.z if a is not None else None)
	return dict(x=x, y=y, z=z, **kwargs)


def seg_xyz(*segs, **kwargs):
	#Plot gcode segments. The 'None' makes a break in a line so we can use
	# just one add_trace() call.
	x, y, z = [], [], []
	for s in segs:
		x.extend([s.start_point.x, s.end_point.x, None])
		y.extend([s.start_point.y, s.end_point.y, None])
		z.extend([s.start_point.z, s.end_point.z, None])
	return dict(x=x, y=y, z=z, **kwargs)

# %%
def plot_layer(layer, thread_geom=[]):
	fig = go.Figure()

	fig.add_trace(go.Scatter3d(**seg_xyz(
			*layer.geometry.segments,
			mode='lines',
			line={'color': 'green'})))

	if thread_geom:
		#Plot the thread
		fig.add_trace(go.Scatter3d(**seg_xyz(
			*thread_geom,
			mode='lines',
			line={'color':'white', 'dash':'dot', 'width':3})))

		for seg,enter,exit,gclines in thread.intersect_thread(thread_geom, layer):
			if enter and exit:
				kwargs = xyz(enter, exit, mode='lines')
			elif enter or exit:
				point = enter or exit
				kwargs = xyz(point, mode='markers')
			else:
				kwargs = xyz(seg.start_point, seg.end_point, mode='lines')

			fig.add_trace(go.Scatter3d(
				marker={'color':'yellow', 'size':4},
				line={'color':'yellow', 'width':8},
				**kwargs,
			))

			if gclines:
				fig.add_trace(go.Scatter3d(**seg_xyz(
					*gclines,
					mode='lines',
					line={'color':'yellow', 'width': 2},
				)))

	fig.update_layout(template='plotly_dark', autosize=False,
			scene_aspectmode='data',
		width=750, height=750, margin=dict(l=0, r=20, b=0, t=0, pad=0),
		)
	fig.show('notebook')

# %%
page_wide()
plot_layer(g.layers[49], thread_geom)

# %%

	"""
	#Plot top/bottom planes for the layer
	xx = list(filter(None, x)); yy = list(filter(None, y))
	zz = g.layers[53].z - 0.2
	fig.add_trace(go.Mesh3d(
			x=[min(xx), min(xx), max(xx), max(xx)],
			y=[min(yy), max(yy), max(yy), min(yy)],
			z=[zz,		 zz,		 zz,		 zz],
			opacity=.5))
	zz = g.layers[53].z + 0.2
	fig.add_trace(go.Mesh3d(
			x=[min(xx), min(xx), max(xx), max(xx)],
			y=[min(yy), max(yy), max(yy), min(yy)],
			z=[zz,		 zz,		 zz,		 zz],
			opacity=.5))
"""
