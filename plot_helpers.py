from typing import Collection, Dict, Any
from functools import partial
import plotly.graph_objects as go
from fastcore.basics import listify
from fastcore.meta import use_kwargs
from util import deep_update
from geometry.utils import min_max_xyz_segs
from geometry.gsegment import GSegment
from geometry.gpoint import GPoint
from plot_styles import styles

def str2style(spec, linewidth=1, markersize=4):
	"""Return a style based on spec, where spec is like Matplotlib's:

		'[marker][color][line][color]'

		markersize applies unless a size is specified in the code below.
	"""
	markers: dict[str, str|dict] = {
			'.': {'symbol': 'circle', 'size': 1},
			'o': 'circle',
			'v': 'triangle-down',
			'^': 'triangle-up',
			'<': 'triangle-left',
			'>': 'triangle-right',
			'1': 'y-down',
			'2': 'y-up',
			'3': 'y-left',
			'4': 'y-right',
			'8': 'octagon',
			's': 'square',
			'p': 'pentagon',
			'P': 'cross',
			'*': 'star',
			'h': 'hexagon',
			'H': 'hexagon2',
			'+': 'cross',
			'x': 'x',
			'X': 'x',
			'D': 'diamond',
	}

	lines = {
			'-': 'solid',
			';': 'dash',
			'-.': 'dashdot',
			':':  'dot',
	}

	colors = {
			'b': 'blue',
			'g': 'green',
			'r': 'red',
			'c': 'cyan',
			'm': 'magenta',
			'y': 'yellow',
			'k': 'black',
			'w': 'white',
			'G': 'gray',
	}

	#Adapted from matplotlib's code
	# https://github.com/matplotlib/matplotlib/blob/a302267d7f0ec4ab05973b984f7b56db21bf524c/lib/matplotlib/axes/_base.py#L169
	markerstyle: str|dict|None = None
	markercolor, linestyle, linecolor, color = None, None, None, None

	i = 0
	while i < len(spec):
		c = spec[i]
		if c in markers:
			markerstyle = markers[c]
			i += 1
		elif c in colors:
			if linestyle is not None:
				linecolor = colors[c]
			elif markerstyle is not None:
				markercolor = colors[c]
			else:
				color = colors[c]
			i += 1
		elif c in lines:
			linestyle = lines[c]
			i += 1

	style: dict[str, dict|Any] = {}

	if markercolor or markerstyle:
		style['marker'] = {'size':  markersize}
	if linecolor or linestyle:
		style['line'] = {'width': linewidth}

	if markercolor is None and linecolor is None and color is not None:
		markercolor = linecolor = color

	if linestyle:
		style['mode'] = 'lines+markers' if markerstyle else 'lines'
		style['line']['dash'] = linestyle
	if markerstyle:
		style.setdefault('mode', 'markers')
		if isinstance(markerstyle, str): markerstyle = {'symbol': markerstyle}
		style['marker'].update(markerstyle)
	if markercolor:
		style['marker']['color'] = markercolor
	if linecolor:
		style['line']['color'] = linecolor

	return style


@use_kwargs(styles.keys())
def quickplot(plot3d=False, show=True, **kwargs):
	fig = go.Figure()
	for style in styles:
		if style in kwargs:
			if not (data := listify(kwargs[style])): continue
			if isinstance(data[0], GSegment):
				plot_segments(fig, data, style=styles[style], plot3d=plot3d)
			elif isinstance(data[0], GPoint):
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


def plot_points(fig, points: Collection[GPoint], name='points',
									style:str|Dict|None=None, plot3d=False, **kwargs):

	if isinstance(style, str):
		style = str2style(style)
	style = deep_update(styles['points'], style or {}, kwargs)

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



def plot_segments(fig, segs_to_plot: Collection[GSegment], name='segments',
									style:str|Dict|None=None, plot3d=False, **kwargs):

	if isinstance(style, str):
		style = str2style(style)
	style = deep_update(styles['segments'], style or {}, kwargs)

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


def add_circles(fig, centers, radius=1, name='circles', style=None):
	if isinstance(style, str): style = str2style(style)
	style = deep_update(styles['circles'], style or {})
	if 'mode' in style: del(style['mode'])
	for c in centers:
		fig.add_shape(type='circle',
				xref='x', yref='y',
				x0=c.x-radius, x1=c.x+radius,
				y0=c.y-radius, y1=c.y+radius,
				**style)


def show_dark(fig, zoom_box:None|Collection[Collection[float]]=None, zoom_factor:float=1.1):
	xaxis = {}
	yaxis = {'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'}
	if zoom_box is not None:
		(x1,y1),(x2,y2)	= zoom_box
		exp_x = (x2-x1)*zoom_factor
		exp_y = (y2-y1)*zoom_factor
		xaxis.update({'range': [x1-exp_x, x2+exp_x]})
		yaxis.update({'range': [y1-exp_y, y2+exp_y]})
	fig.update_layout(template='plotly_dark',
			xaxis=xaxis, yaxis=yaxis,
			margin=dict(l=0, r=20, b=0, t=0, pad=0),
			width=450, height=450,
			showlegend=False,)
	fig.show()
