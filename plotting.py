import re
import plotly.graph_objects as go
from plot_helpers import segs_xy, plot_segments, plot_points, show_dark, styles
from tlayer import TLayer
from util import deep_update
from geometry import GSegment, GPoint
from geometry.utils import angle2point
from Geometry3D import Vector
from gcline import GCLine
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



def animate_gcode(gclines:list[GCLine], bed_config, ring_config, start_angle=0):
	#Shift coordinates so bed 0,0 is actually at 0,0 and ring is moved relative
	zvec = Vector(bed_config['zero'], GPoint(0, 0, bed_config['zero'].z))
	bed_zero = bed_config['zero'].moved(zvec)
	ring_zero = ring_config['zero'].moved(zvec)

	fig_dict = {'data': [], 'frames': [],
		'layout': {
			'xaxis': {'range': [bed_zero.x, bed_zero.x + bed_config['size'][0]]},
			'yaxis': {'range': [bed_zero.y, bed_zero.y + bed_config['size'][1]],
				'scaleanchor': 'x', 'scaleratio': 1, 'constrain': 'domain'},
			'template': 'plotly_dark',
			'margin': dict(l=0, r=20, b=0, t=0, pad=0),
			'width': 450, 'height': 450,
			'showlegend': False,
			}
	}

	bed = dict(
		name='bed',
		type='rect',
		xref='x',
		yref='y',
		x0=bed_zero.x,
		y0=bed_zero.y,
		x1=bed_zero.x + bed_config['size'][0],
		y1=bed_zero.y + bed_config['size'][1],
		line=dict(color='rgba(0,0,0,0)'),
		fillcolor='LightSkyBlue',
		opacity=.25,
	)

	#Add traces for each line of gcode
	gc_style = deep_update(styles['segments'], styles['gc_segs'], {'line':{'width':1}})
	thread_style = deep_update(styles['thread_ring'], styles['anchor'])

	#Ref: https://plotly.com/python-api-reference/generated/plotly.graph_objects.layout.html#plotly.graph_objects.layout.Slider
	slider = dict(
		# active=1,                           #active button (??)
		# currentvalue={'prefix': 'Line:'},   #current value label
		pad={'t': 50},                        #UI padding in pixels
		steps=[]
	)

	frames = []

	xs, ys = [], []
	cur_x, cur_y = 0, 0
	for i,line in enumerate(gclines):
		if line.is_xymove():
			cur_x, cur_y = line.xy
			break

	extruder = 0
	anchors = [GPoint(0, 0, 0)]
	angle = start_angle
	tx, ty = angle2point(angle, ring_zero, ring_config['radius']).xy
	thread = [
				dict(x=[0, tx], y=[0, ty], name='thread', mode='lines+markers', **thread_style),
				dict(x=[0, tx], y=[0, ty], name='target', mode='markers',
							**deep_update(styles['anchor'], {'marker': {'symbol': 'circle-dot'}})),
	]

	fig_dict['data'] = [ dict(x=[0,1], y=[0,1], name='0', **gc_style)]
	fig_dict['data'].extend(thread)
	fig_dict['data'].extend([
		dict(x=[0],   y=[0],   name='anchor', mode='markers', **styles['anchor']),
		dict(x=[0],   y=[0],   name='target', mode='markers', **styles['anchor']),
	])

	for line in gclines[i:]:
		frame = {'data': [], 'layout': {'shapes': [bed]}, 'name': f'[{len(frames):>3}] Line {line.lineno}'}

		if line.is_xymove():
			x,y = line.xy
			# ring_zero = ring_zero.moved(Vector(0, y - ring_zero.y, 0))
			if line.is_xyextrude():
				xs = xs.copy()
				ys = ys.copy()
				xs.extend([cur_x, x, None])
				ys.extend([cur_y, y, None])
				frame['data'].append(dict(
						x=xs,
						y=ys,
						name=line.lineno,
						**gc_style))
				frame['layout']['shapes'].append(dict(
					type='circle', xref='x', yref='y',
					x0=ring_zero.x - ring_config['radius'],
					x1=ring_zero.x + ring_config['radius'],
					y0=ring_zero.y - ring_config['radius'],
					y1=ring_zero.y + ring_config['radius'],
					line=dict(color='white', width=10), opacity=.25))

				frame['data'].extend(thread)
				if not frames: fig_dict['data'] = frame['data'].copy()
				frames.append(frame)

				slider['steps'].append({'args': [
						[frame['name']],   #Frame to animate, by name
						{'frame': {'duration': 0, 'redraw': False}, 'mode': 'immediate'}],
					'label': f'({cur_x}, {cur_y}) → ({x}, {y}); {angle:.2f}°', 'method': 'animate'})

			cur_x, cur_y = x, y

		elif line.is_extrude() and extruder == 1:
			if line.args["E"] > 400: print(line)
			angle += line.args['E']
			angle = angle % 360
			p = angle2point(angle, ring_zero, ring_config['radius'])
			tx = [a.x for a in anchors] + [p.x]
			ty = [a.y for a in anchors] + [p.y]
			thread = [
				dict(x=tx, y=ty, name='thread', mode='lines+markers', **thread_style),
				dict(x=[p.x], y=[p.y], name=f'target {angle:.2f}°', mode='markers',
							**deep_update(styles['anchor'], {'marker': {'symbol': 'circle-dot'}})),
			]
			frame['data'].append(dict(
					x=xs,
					y=ys,
					name=line.lineno,
					**gc_style))
			frame['data'].extend(thread)
			frames.append(frame)
			slider['steps'].append({'args': [
					[frame['name']],   #Frame to animate, by name
					{'frame': {'duration': 0, 'redraw': False}, 'mode': 'immediate'}],
				'label': f'({cur_x}, {cur_y}) → ({x}, {y}); {angle:.2f}°', 'method': 'animate'})

		elif m := re.search('anchor at {\s*([0-9., ]+)\s*}', line.comment or ''):
			anchors.append(GPoint(*map(float, m.group(1).split(','))))

		elif line.code and line.code.startswith('T'):
			extruder = int(line.code[1])

	fig_dict['frames'] = frames
	fig_dict['layout']['sliders']=[slider]

	fig = go.Figure(fig_dict)
	fig.show()
	return fig, fig_dict
