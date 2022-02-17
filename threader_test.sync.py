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
from danutil import unpickle
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
	</style>
	"""))


# %%
import threader, geometry_helpers
from parsers import cura4
reload(geometry_helpers)
reload(threader)
reload(cura4)
from threader import TLayer, Threader
page_wide()

# %%
tpath = np.array(unpickle('/Users/dan/r/thread_printer/stl/test1/thread_from_fusion.pickle')) * 10
thread_transform = [131.164, 110.421, 0]
tpath += [thread_transform, thread_transform]

thread_geom = tuple([geometry_helpers.GSegment(Point(*s), Point(*e)) for s,e in tpath])
g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode', layer_class=TLayer)
t = Threader(g)
stepsobj = t.route_layer(thread_geom, g.layers[49])
steps = stepsobj.steps
#print(steps)

# %%
stepsobj.flat_thread
pickle(stepsobj.flat_thread, '/tmp/t.pickle')

# %%
anchor = steps[0].state.bed.anchor
for stepnum,step in enumerate(steps):
	print(f'Step {stepnum}: {step.name}')
	fig = go.Figure()

	step.state.bed.plot(fig)

	for i in range(0, stepnum):
		steps[i].plot_gcsegments(fig, style={'gc_segs': {'line': dict(color='gray')}})
		if i > 0:
			steps[i].plot_thread(fig, steps[i-1].state.anchor,
					style={'thread': {'line':dict(color='blue')}})
	step.plot_gcsegments(fig)

	if hasattr(step.state, 'tseg'):
		step.state.plot_anchor(fig)
		tseg = step.state.tseg
		isec_points = step.state.layer.model_isecs[tseg]['isec_points']
		isec_segs = step.state.layer.model_isecs[tseg]['isec_segs']

		if enter := getattr(tseg.start_point, 'in_out', None):
			if enter.inside(step.state.layer.geometry.outline):
				fig.add_trace(go.Scatter(x=[enter.x], y=[enter.y], mode='markers',
					marker=dict(color='yellow', symbol='x', size=8), name='enter'))

		if exit := getattr(tseg.end_point, 'in_out', None):
			if exit.inside(step.state.layer.geometry.outline):
				fig.add_trace(go.Scatter(x=[exit.x], y=[exit.y], mode='markers',
					marker=dict(color='orange', symbol='x', size=8), name='exit'))

		# for i,anchor in enumerate(isec_points):
		# 	fig.add_trace(go.Scatter(x=[anchor.x], y=[anchor.y], mode='markers+text',
		# 		marker=dict(color='red', symbol='x', size=8),
		# 		hovertemplate=repr(isec_segs[i])))
			# fig.add_trace(go.Scatter(**geometry_helpers.segs_xy(isec_segs[i], mode='lines',
			# 	line=dict(color='orange',  width=5))))
			#TODO: I think the problem here could be that we're intersecting part of
			# the thread that is not on the layer yet???
			# print(f'intersection({isec_segs[i]}, {tseg}) = {isec_points[i]}')

	# if hasattr(step.state, 'hl_parts'):

	# 	a, b = step.state.hl_parts
	# 	fig.add_trace(go.Scatter(x=[a.x, b.x], y=[a.y, b.y], line=dict(color='red',
	# 		width=4, dash='dot')))
	# 	fig.add_trace(go.Scatter(x=[step.state.ring_point.x],
	# 		y=[step.state.ring_point.y], mode='markers',
	# 		marker=dict(color='limegreen', symbol='circle', size=8)))

	step.state.plot_thread_to_ring(fig)
	step.plot_thread(fig, anchor)
	anchor = step.state.anchor

	step.state.ring.plot(fig)

	fig.update_layout(template='plotly_dark',# autosize=False,
			yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
			#height=750,
			margin=dict(l=0, r=20, b=0, t=0, pad=0),
			showlegend=False,)
	fig.show('notebook')

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
l = g.layers[49]
l.intersect(thread_geom)
#enter, exit = l._isecs[thread_geom[0]]['enter'], l._isecs[thread_geom[0]]['exit']
print(l._isecs[thread_geom[0]])

fig = go.Figure()
l.plot(fig)
fig.add_trace(go.Scatter(**geometry_helpers.segs_xy(thread_geom[0],
	mode='lines', line=dict(color='green',  width=2))))
fig.add_trace(go.Scatter(x=[enter.x], y=[enter.y], marker=dict(color='red',
	symbol='x', size=8)))
# fig.add_trace(go.Scatter(x=[enter.x, exit.x], y=[enter.y, exit.y],
# 	line=dict(color='red', width=2)))
print(thread_geom[0])
print(enter, exit)
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
