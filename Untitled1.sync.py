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

from IPython.core.display import display, HTML
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

#suppress scientific notation
numpy.set_printoptions(suppress=True, precision=2)
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
fig = go.Figure()
x, y, z = [], [], []
for s in g.layers[53].geometry['segments']:
		x.extend([s.start_point.x, s.end_point.x, None])
		y.extend([s.start_point.y, s.end_point.y, None])
		z.extend([s.start_point.z, s.end_point.z, None])
fig.add_trace(go.Scatter3d(x=x, y=y, z=z, mode='lines', line={'color': 'green'}))

threadnp = np.vstack([tpath[:,0], tpath[:,1][-1]])
fig.add_trace(go.Scatter3d(x=threadnp[:,0], y=threadnp[:,1], z=threadnp[:,2], mode='lines',
													line={'color':'red', 'dash':'dot', 'width':3}))

for tg in thread_geom:
	intr = intersection(g.layers[53].geometry['planes'][0], tg)
	if intr:
		print(f'{i}: {intr}')
		fig.add_trace(go.Scatter3d(
			x=[intr.x],
			y=[intr.y],
			z=[intr.z],
			mode='markers',
			marker_size=4,
			marker_color='yellow',
			#mode='lines',
			#line={'color':'yellow', 'width':8}))
			))


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

fig.update_layout(
	template='plotly_dark',
	autosize=False,
	width=750,
	height=750,
	margin=dict(
			l=0,
			r=20,
			b=0,
			t=0,
			pad=0
	))
fig.show()
