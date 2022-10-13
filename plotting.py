import plotly.graph_objects as go
from plot_helpers import segs_xy, plot_segments
from tlayer import TLayer

def plot_steps(steps_obj, prev_layer:TLayer=None, stepnum=None, prev_layer_only_outline=True):
	#Default plotting style
	styles: dict[str, dict] = {
		'old_segs':   {'line': dict(color= 'gray', width=1)},
		'old_thread': {'line_color': 'blue'},
		'old_layer':  {'line': dict(color='gray', width=.5), 'opacity':.25},
		'to_print':   {'line': dict(color='green', width=.5), 'opacity':.25},
		'all_thread': {'line': dict(color='cyan', dash='dot', width=.5),
									 'marker': dict(symbol='circle-open', color='cyan', size=4)},
	}

	steps        = steps_obj.steps
	last_anchor  = steps[0].printer.anchor

	for stepnum,step in enumerate(steps):
		if not step.valid:
			print(f'Skip {step.number}')
			continue

		print(f'Step {stepnum}: {step.name}')
		fig = go.Figure()

		#Plot the bed
		step.printer.bed.plot(fig)

		#Plot the outline of the previous layer, if provided
		if prev_layer:
			prev_layer.plot(fig, style=styles['old_layer'],
					only_outline=prev_layer_only_outline)

		plot_segments(fig, steps_obj.layer.geometry.segments, style=styles['to_print'])

		#Plot the entire thread path that will be routed this layer
		if hasattr(steps_obj.layer, 'snapped_thread'):
			fig.add_trace(go.Scatter(**segs_xy(*steps_obj.layer.snapped_thread,
				mode='lines+markers', **styles['all_thread'])))

		#Plot the thread from the bed anchor or the layer anchor to the first
		# step's anchor
		steps[0].plot_thread(fig,
			getattr(steps_obj.layer, 'start_anchor', steps[0].printer.bed.anchor))

		#Plot any geometry that was printed in the previous step
		if stepnum > 0:
			segs = set.union(*[set(s.gcsegs) for s in steps[:stepnum]])
			steps[stepnum-1].plot_gcsegments(fig, segs,
					style={'gc_segs': styles['old_segs']})

		#Plot geometry and thread from previous steps
		for i in range(0, stepnum):

			#Plot the thread from the previous steps's anchor to the current step's
			# anchor
			if i > 0:
				steps[i].plot_thread(fig,
						steps[i-1].printer.anchor,
						style={'thread': styles['old_thread']},
				)

		#Plot geometry printed in this step
		step.plot_gcsegments(fig)

		#If there are debug intersection points, print them
		if stepnum > 0  and hasattr(steps[stepnum-1].printer, 'debug_non_isecs'):
			fig.add_trace(go.Scatter(
				x=[p.x for p in steps[stepnum-1].printer.debug_non_isecs],
				y=[p.y for p in steps[stepnum-1].printer.debug_non_isecs], mode='markers',
				marker=dict(color='magenta', symbol='circle', size=8)))

		#Plot thread trajectory from current anchor to ring
		step.printer.plot_thread_to_ring(fig)

		#Plot thread from last step's anchor to current anchor
		step.plot_thread(fig, last_anchor)
		last_anchor = step.printer.anchor

		#Plot anchor/enter/exit points if any
		step.printer.plot_anchor(fig)
		if thread_seg := getattr(step.printer, 'thread_seg', None):

			if enter := getattr(thread_seg.start_point, 'in_out', None):
				if enter.inside(step.printer.layer.geometry.outline):
					fig.add_trace(go.Scatter(x=[enter.x], y=[enter.y], mode='markers',
						marker=dict(color='yellow', symbol='x', size=8), name='enter'))

			if exit := getattr(thread_seg.end_point, 'in_out', None):
				if exit.inside(step.printer.layer.geometry.outline):
					fig.add_trace(go.Scatter(x=[exit.x], y=[exit.y], mode='markers',
						marker=dict(color='orange', symbol='x', size=8), name='exit'))

		#Plot the ring
		step.printer.ring.plot(fig)

		#Show the figure for this step
		(x1,y1),(x2,y2) = step.printer.layer.extents()
		exp_x = (x2-x1)*1.1
		exp_y = (y2-y1)*1.1
		ext_min, ext_max = step.printer.layer.extents()
		fig.update_layout(template='plotly_dark',# autosize=False,
				xaxis={'range': [x1-exp_x, x2+exp_x]},
				yaxis={'range': [y1-exp_y, y2+exp_y],
							'scaleanchor': 'x', 'scaleratio':1, 'constrain':'domain'},
				margin=dict(l=0, r=20, b=0, t=0, pad=0),
				width=450, height=450,
				showlegend=False,)
		fig.show()

	print('Finished routing this layer')
