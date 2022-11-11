import plotly.graph_objects as go
from plot_helpers import segs_xy, plot_segments, plot_points, show_dark, styles
from tlayer import TLayer
from util import deep_update
from geometry import GSegment
from Geometry3D import Vector
import ender3


def plot_steps(steps_obj, prev_layer:TLayer=None, stepnum=None,
							 prev_layer_only_outline=True, preview_layer=True):
	#Default plotting style
	steps       = steps_obj.steps
	layer       = steps_obj.layer

	if preview_layer:
		step = steps[0]
		print(f'Preview of {len(steps)} steps for layer {step.layer.layernum}')
		fig = go.Figure()
		step.printer.bed.plot(fig)

		#Plot the outline of the previous layer, if provided
		if prev_layer:
			prev_layer.plot(fig, style=styles['old_layer'], only_outline=prev_layer_only_outline)

		plot_segments(fig, layer.geometry.segments, style=styles['gc_segs'],
								name='gc segs', line_width=1)

		#Plot the entire thread path that will be routed this layer
		if snapped_thread := getattr(layer, 'snapped_thread', None):
			#Plot original thread
			plot_segments(fig, snapped_thread.keys(), name='original thread',
								 style=styles['original_thread'])

			#Plot trajectories of endpoint moves for snapping
			x, y = [], []
			for old,new in snapped_thread.items():
				if new is not None and new != old:
					x.extend([old.end_point.x, new.end_point.x, None])
					y.extend([old.end_point.y, new.end_point.y, None])
			if x:
				fig.add_trace(go.Scatter(x=x, y=y, name='thread_snaps', mode='lines',
															**styles['moved_thread']))

			#Plot new thread
			plot_segments(fig, snapped_thread.values(), name='thread',
									style=styles['future_thread'])

		#Plot all of the anchors
		plot_points(fig, [seg.end_point for seg in layer.thread], style=styles['anchor'])
		if hasattr(layer, 'start_anchor'):
			plot_points(fig, [layer.start_anchor], style=styles['anchor'],
							 name='start anchor', marker_symbol='circle', marker_size=6)

		show_dark(fig, zoom_box=layer.extents())


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

		#Plot segments to be printed this layer
		plot_segments(fig, layer.geometry.segments, style=styles['to_print'])

		#Plot any geometry that was printed in the previous step
		if stepnum > 0:
			segs = set.union(*[set(s.gcsegs) for s in steps[:stepnum]])
			plot_segments(fig, segs, name='prev step segs', style=styles['old_segs'])

		##Plot the thread from the previous steps
		#for i in range(1, stepnum):
		#	steps[i].plot_thread(fig, steps[i-1].printer.anchor, style={'thread': styles['old_thread']})
		for i in range(1, stepnum):
			if steps[i-1].printer.anchor != steps[i].printer.anchor:
				plot_segments(fig, [GSegment(steps[i-1].printer.anchor, steps[i].printer.anchor)],
									style=styles['printed_thread'], name='finished thread')

		#Plot geometry printed in this step
		plot_segments(fig, step.gcsegs, name='gcsegs', style=styles['gc_segs'])

		#Print segments to avoid, if any
		if avoid_seg := getattr(step.printer, 'debug_avoid'):
			plot_segments(fig, avoid_seg, style=styles['avoid_segs'], name='avoid')

		#Plot thread trajectory from current anchor to ring
		plot_segments(fig, [GSegment(
			steps[stepnum-1].printer.anchor if stepnum > 0 else steps[0].printer.anchor,
			step.printer.ring.point)], name='thread', style=styles['thread_ring'])

		#Plot anchor/enter/exit points if any
		plot_points(fig, [step.printer.anchor], name='anchor', style=styles['anchor'])
		if hasattr(layer, 'start_anchor'):
			plot_points(fig, [layer.start_anchor], style=styles['anchor'],
							 name='start anchor', marker_symbol='circle', marker_size=6)

		#Plot the ring
		step.printer.ring.plot(fig)#, offset=Vector(ender3.bed_config['zero'], ender3.ring_config['zero']))

		#Show the figure for this step
		(x1,y1),(x2,y2) = layer.extents()
		exp_x = (x2-x1)*1.1
		exp_y = (y2-y1)*1.1
		fig.update_layout(template='plotly_dark',# autosize=False,
				xaxis={'range': [x1-exp_x, x2+exp_x]},
				yaxis={'range': [y1-exp_y, y2+exp_y],
							'scaleanchor': 'x', 'scaleratio':1, 'constrain':'domain'},
				margin=dict(l=0, r=20, b=0, t=0, pad=0),
				width=450, height=450,
				showlegend=False,)
		fig.show()

	print('Finished routing this layer')
