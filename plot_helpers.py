import plotly.graph_objects as go
from fastcore.basics import listify
from fastcore.meta import use_kwargs
from util import deep_update
from functools import partial
from geometry_helpers import min_max_xyz_segs, Segment, Point

styles = {
	#'bed':        {'line': dict(color='rgba(0,0,0,0)'), 'fillcolor': 'LightSkyBlue', 'opacity':.25},
	'old_segs':   {'line': dict(color= 'gray', width=1)},
	'all_thread': {'line': dict(color='cyan', dash='dot', width=.5)},
	'old_thread': {'line_color': 'blue'},
	'gc_segs':    {'mode':'lines', 'line': dict(color='green',  width=1)},
	'thread':     {'mode':'lines', 'line': dict(color='white', width=1, dash='dot')},
	'anchor':     {'mode':'markers', 'marker': dict(color='red', symbol='x', size=4)},
	'points':     {'mode':'markers', 'marker': dict(color='violet', symbol='circle', size=4)},
	# 'ring':       {'line': dict(color='white', width=10), 'opacity':.25},
	# 'indicator':  {'line': dict(color='blue',  width= 4)},
}


@use_kwargs(styles.keys())
def quickplot(plot3d=False, show=True, **kwargs):
	fig = go.Figure()
	for style in styles:
		if style in kwargs:
			data = listify(kwargs[style])
			if isinstance(data[0], Segment):
				plot_segments(fig, data, style=styles[style], plot3d=plot3d)
			elif isinstance(data[0], Point):
				plot_points(fig, data, style=styles[style], plot3d=plot3d)
	if show: show_dark(fig)
	return fig


def segs_xyz(*segs, **kwargs):
	#Plot gcode segments. The 'None' makes a break in a line so we can use
	# just one add_trace() call.
	x, y, z = [], [], []
	for s in segs:
		x.extend([s.start_point.x, s.end_point.x, None])
		y.extend([s.start_point.y, s.end_point.y, None])
		z.extend([s.start_point.z, s.end_point.z, None])
	return dict(x=x, y=y, z=z, **kwargs)


def segs_xy(*segs, **kwargs):
	d = segs_xyz(*segs, **kwargs)
	del(d['z'])
	return d


def update_figure(fig, name, style, what='traces'):
	"""Update traces, shapes, etc for the passed figure object for figure members with
	the given name.  style should be a dict like {name: {'line': {'color': 'red'}}} .
	"""
	if style and name in style:
		getattr(fig, f'update_{what}')(selector={'name':name}, **style[name])


def plot_points(fig, points, name='points', style=None, plot3d=False):
	style = deep_update(styles['anchor'], style or {})
	x,y,z = xyz = zip(*[p[:] for p in points])
	if plot3d:
		scatter_func = partial(go.Scatter3d, x=x, y=y, z=z)
		minx, miny, minz = map(min, xyz)
		maxx, maxy, maxz = map(max, xyz)
		fig.add_trace(go.Scatter3d(x=[minx, maxx], y=[miny, maxy], z=[minz, maxz],
			mode='markers', marker=dict(color='black')))
		fig.update_layout(scene=dict(aspectmode='cube'))
	else:
		scatter_func = partial(go.Scatter, x=x, y=y)

	fig.add_trace(scatter_func(name=name, **style))



def plot_segments(fig, segs_to_plot, name='gc_segs', style=None, plot3d=False):
	style = deep_update(styles['gc_segs'], style or {})
	if plot3d:
		scatter_func = go.Scatter3d
		segs_func = segs_xyz
		style = deep_update(style, {'line': dict(width=2)})
		(minx, miny, minz), (maxx, maxy, maxz) = min_max_xyz_segs(segs_to_plot)
		fig.add_trace(go.Scatter3d(x=[minx, maxx], y=[miny, maxy], z=[minz, maxz],
			mode='markers', marker=dict(color='black')))
		fig.update_layout(scene=dict(aspectmode='cube'))
	else:
		scatter_func = go.Scatter
		segs_func = segs_xy

	fig.add_trace(scatter_func(**segs_func(*segs_to_plot, name=name, **style)))


def show_dark(fig):
	fig.update_layout(template='plotly_dark',# autosize=False,
			yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
			margin=dict(l=0, r=20, b=0, t=0, pad=0),
			width=450, height=450,
			showlegend=False,)
	fig.show()
