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
# Imports
import pickle
import numpy as np
import thread, gcode, gclayer
from Geometry3D import Segment, Point, intersection, Renderer
from parsers import cura4
from importlib import reload
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from plotly.offline import plot, iplot, init_notebook_mode
from IPython.core.display import display, HTML
init_notebook_mode(connected=True)

#suppress scientific notation
np.set_printoptions(suppress=True, precision=2)


# %%
#turn off autosave since we sync from vim
# %autosave 0

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


def xy(*segs, **kwargs):
	d = xyz(*segs, **kwargs)
	del(d['z'])
	return d


def seg_xyz(*segs, **kwargs):
	#Plot gcode segments. The 'None' makes a break in a line so we can use
	# just one add_trace() call.
	x, y, z = [], [], []
	for s in segs:
		x.extend([s.start_point.x, s.end_point.x, None])
		y.extend([s.start_point.y, s.end_point.y, None])
		z.extend([s.start_point.z, s.end_point.z, None])
	return dict(x=x, y=y, z=z, **kwargs)


def seg_xy(*segs, **kwargs):
	d = seg_xyz(*segs, **kwargs)
	del(d['z'])
	return d


def fig_del_by_names(fig, *names):
	"""Remove the trace with the name from the fig."""
	fignames = set([d.name for d in fig.data])
	fignames.difference_update(names)
	fig.data = [d for d in fig.data if d.name in fignames]

# %%
def plot_layer(layer, thread_geom=[]):
	fig = go.FigureWidget()

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

		intersections = thread.intersect_thread(thread_geom, layer)
		for seg,enter,exit,gclines in intersections:
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

	fig.update_layout(template='plotly_dark',# autosize=False,
			scene_aspectmode='data',
		width=750, height=750, margin=dict(l=0, r=20, b=0, t=0, pad=0),
		)
	#fig.show('notebook')

	return fig, intersections

# %%
page_wide()
fig, ii = plot_layer(g.layers[49], thread_geom)
fig

# %%
# seg,enter,exit,gclines 
fig.add_trace(go.Scatter3d(**seg_xyz(ii[0][0], *ii[0][3], mode='lines', line={'color':'red'})));

# %%
from copy import deepcopy

# %%
styles = {
	'gc_segs':      {'mode': 'lines', 'line': dict(color='green', width=1)},
	'th_traj':      {'mode': 'lines', 'line': dict(color='cyan', dash='dot', width=1)},
	'thread_seg':   {'mode': 'lines', 'line': dict(color='red', dash='dot', width=1)},
	'isec_gcode':   {'mode': 'lines', 'line': dict(color='yellow', width=1)},
	'layer_thread': {
		'marker': dict(color='orange', size=4),
		'line':   dict(color='red', dash='dot', width=3),
	},
}

def plot_steps(layer, thread_geom):
	#Separate the layer lines that do (intersected_gc) and don't (gc_segs)
	# intersect the thread in this layer
	gc_segs = set(layer.geometry.segments)
	intersections = thread.intersect_thread(thread_geom, layer)
	intersected_gc = set(sum([i[3] for i in intersections], []))
	gc_segs.difference_update(intersected_gc)
	gc_segs = list(gc_segs)

	frames = []
	titles = []

	#List of traces to show in all frames
	always_show = []

	# gcode segments that no thread intersects should always be shown
	gc_segs = go.Scatter(**seg_xy(*gc_segs, name='gc_segs', **styles['gc_segs']))
	always_show.append(gc_segs)

	#First frame is gcode + thread; assume the start_point of the first thread
	# segment is the thread anchor point on the bed. Put the thread away from the
	# model to begin with.
	anchor = thread_geom[0].start_point
	titles.append('Start')
	frames.append(always_show + [
		go.Scatter(**seg_xy(Segment(anchor, Point(anchor.x, layer.extents()[1][1], 0)),
		name='th_traj', **styles['th_traj']))])

	#Now generate the frames of the animation:
	# 1. Rotate the thread from its current anchor point to overlap the gcode segment that
	#    should capture it.
	# 2. Draw the gcode segment that will capture it.
	# 3. Store the new anchor point for the thread.
	# Each frame should show updates of the previous.
	for seg,enter,exit,gclines,gcinter in intersections:
		print(f'enter: {bool(enter)}, exit: {bool(exit)}, gclines: {len(gclines)}, gcinter: {len(gcinter)}')

		#The thread segment, whether or not it intersects anything in the layer
		thread_seg = go.Scatter(**seg_xy(seg, name='thread_seg', **styles['thread_seg']))

		#If there's no intersection with layer geometry, just show the thread
		# segment
		if not (enter or exit or gclines):
			thread_seg.line.color = 'gray'
			frames.append(always_show + [thread_seg])
			continue

		#The gcode segments that this thread segment intersects in this layer
		isec_gcode = go.Scatter(**seg_xy(*gclines, name='isec_gcode', **styles['isec_gcode']))

		#The thread segment where it intersects the layer (either a line if
		# captured or points if entering/exiting)
		if enter and exit:
			point = enter
			kwargs = xy(enter, exit, mode='lines')
		elif enter or exit:
			point = enter or exit
			kwargs = xy(point, mode='markers')
		else:
			point = seg.start_point
			kwargs = seg_xy(seg, mode='lines')

		kwargs.update(styles['layer_thread'])
		layer_thread = go.Scatter(name='layer_thread', **kwargs)

		#The representation of the actual thread trajectory, from anchor to thread
		# carrier
		th_traj = go.Scatter(xy(anchor,
			deepcopy(point).move(seg.line.dv.unit() * 100), #extend line
			**styles['th_traj']))

		#Set the anchor to the last place the thread gets captured
		#anchor = min(gcinter, key=lambda p:pz(seg.end_point).distance(pz(p)))

		frames.append(always_show + [
			isec_gcode,
			th_traj,
			layer_thread,
		])
			
		#Going forward, always show the placed gcode
		isec_gcode_new = go.Scatter(**seg_xy(*gclines, **styles['gc_segs']))
		always_show.append(isec_gcode_new)

	return frames

# %%
def show_each_frame(frames):
	for i,frame in enumerate(frames):
		fig = go.Figure()
		for trace in frame:
			fig.add_trace(trace)
		fig.update_layout(template='plotly_dark',# autosize=False,
				yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
				#height=750,
				margin=dict(l=0, r=20, b=0, t=0, pad=0),
				showlegend=False,)
		fig.show('notebook')

# %%
def show_frames_as_subplots(frames):
	#fig = frames2subplots(frames)
	fig.update_layout(template='plotly_dark',# autosize=False,
			yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
			height=750*len(frames),
			margin=dict(l=0, r=20, b=0, t=0, pad=0),
			showlegend=False,
		)
	return fig

# %%
def animate_frames(frames):
	#Set up the figure
	(xm, ym), (xM, yM) = layer.extents()
	page_wide()
	frames = [go.Frame(data=f) for f in frames]
	fig = go.Figure(
		data = always_show,
		 layout = go.Layout(
			scene_aspectmode='data',
			xaxis={'range': [xm, xM], 'autorange': False},
			yaxis={'range': [ym, yM], 'autorange': False},
		 	updatemenus=[{
		 		'type':'buttons',
		 		'buttons':[{'label':'Play', 'method':'animate',
					'args':[None, {'transition':{'duration':0}}]}]}],
		 	template='plotly_dark', autosize=False,
		 	width=750, margin=dict(l=0, r=20, b=0, t=0, pad=0),
		 ),
		frames = frames
	)

	return fig


# %%
def frames2subplots(frames, titles=[]):
	fig = make_subplots(rows=len(frames), subplot_titles=titles,
			shared_xaxes=True, shared_yaxes=True,
			vertical_spacing=.001
	)
	for i,frame in enumerate(frames):
		for trace in frame:
			fig.add_trace(trace, row=i+1, col=1)
	return fig

# %%
frames = plot_steps(g.layers[49], thread_geom)
show_each_frame(frames)
