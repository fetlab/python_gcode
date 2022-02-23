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
"""
