import plotly.graph_objects as go

styles = {
	'gc_segs': {'mode':'lines', 'line': dict(color='green',  width=1)},
	'thread':  {'mode':'lines', 'line': dict(color='yellow', width=1, dash='dot')},
}

def update_figure(fig, name, style, what='traces'):
	"""Update traces, shapes, etc for the passed figure object for figure members with
	the given name.  style should be a dict like {name: {'line': {'color': 'red'}}} .
	"""
	if style and name in style:
		getattr(fig, f'update_{what}')(selector={'name':name}, **style[name])


def plot_gcsegments(fig, segs_to_plot, style=None):
	#Plot gcode segments. The 'None' makes a break in a line so we can use
	# just one add_trace() call.
	segs = {'x': [], 'y': []}
	for seg in segs_to_plot:
		segs['x'].extend([seg.start_point.x, seg.end_point.x, None])
		segs['y'].extend([seg.start_point.y, seg.end_point.y, None])
	fig.add_trace(go.Scatter(**segs, name='gc_segs', **styles['gc_segs']))
	update_figure(fig, 'gc_segs', style)


def show_dark(fig):
	fig.update_layout(template='plotly_dark',# autosize=False,
			yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
			margin=dict(l=0, r=20, b=0, t=0, pad=0),
			showlegend=False,)
	fig.show()
