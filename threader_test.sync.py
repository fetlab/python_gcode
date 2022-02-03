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
reload(geometry_helpers)
reload(threader)
from threader import TLayer, Threader
page_wide()

# %%
tpath = np.array(unpickle('/Users/dan/r/thread_printer/stl/test1/thread_from_fusion.pickle')) * 10
thread_transform = [131.164, 110.421, 0]
tpath += [thread_transform, thread_transform]
thread_geom = tuple([geometry_helpers.GSegment(Point(*s), Point(*e)) for s,e in tpath])
g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode',
		layer_class=TLayer)
t = Threader(g)
steps = t.route_layer(thread_geom, g.layers[45])
#print(steps)

# %%
anchor = steps[0].state.bed.anchor
for stepnum,step in enumerate(steps):
	print(f'Step {stepnum}: {step.name}')
	fig = go.Figure()

	step.state.bed.plot(fig)

	for i in range(0, stepnum):
		steps[i].plot_gcsegments(fig, style={'gc_segs': {'line': dict(color='gray')}})
		steps[i].plot_thread(fig, steps[i-1].state.anchor,
				style={'thread': {'line':dict(color='blue')}})
	step.plot_gcsegments(fig)

	if hasattr(step.state, 'tseg'):
		step.state.plot_anchor(fig)
		tseg = step.state.tseg
		enter = step.state.layer._isecs[tseg]['enter'][0]
		exit  = step.state.layer._isecs[tseg]['exit'][0]
		isec_points = step.state.layer._isecs[tseg]['isec_points']
		isec_segs = step.state.layer._isecs[tseg]['isec_segs']
		fig.add_trace(go.Scatter(x=[enter.x], y=[enter.y], mode='markers',
			marker=dict(color='yellow', symbol='x', size=8), name='enter'))
		fig.add_trace(go.Scatter(x=[exit.x], y=[exit.y], mode='markers',
			marker=dict(color='orange', symbol='x', size=8), name='exit'))
		for i,anchor in enumerate(isec_points):
			fig.add_trace(go.Scatter(x=[exit.x], y=[exit.y], mode='markers+text',
				marker=dict(color='red', symbol='x', size=8),# name=f'isec {isec_segs[i]}',
				hovertemplate=repr(isec_segs[i])))
			fig.add_trace(go.Scatter(**geometry_helpers.segs_xy(isec_segs[i], mode='lines',
				line=dict(color='orange',  width=5))))
			#TODO: I think the problem here could be that we're intersecting part of
			# the thread that is not on the layer yet???
			print(f'intersection({isec_segs[i]}, {tseg}) = {isec_points[i]}')

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
reload(parsers.cura4)
reload(geometry_helpers)
reload(threader)
from threader import TLayer, Threader

g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode',
		layer_class=TLayer)

fig = go.Figure()
g.layers[1].plot(fig)

fig.update_layout(template='plotly_dark',# autosize=False,
		yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
		margin=dict(l=0, r=20, b=0, t=40, pad=0),
)

fig.show('notebook')

# %%
print(geometry_helpers.intersection.cache_info())
