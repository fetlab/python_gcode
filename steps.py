from util import store_attr, find
from step import Step
from logger import rprint
from gcline import GCLine
from tlayer import TLayer

import plotly.graph_objects as go
from plot_helpers import segs_xy

class Steps:
	#Default plotting style
	style = {
		'old_segs':   {'line': dict(color= 'gray', width=1)},
		'old_thread': {'line_color': 'blue'},
		'old_layer':  {'line': dict(color='gray', dash='dot', width=.5)},
		'all_thread': {'line': dict(color='cyan', dash='dot', width=.5)},
	}
	def __init__(self, layer, printer):
		store_attr()
		self.steps = []
		self._current_step = None


	def __repr__(self):
		return f'{len(self.steps)} Steps for layer {self.layer}\n' + '\n'.join(map(repr, self.steps))


	@property
	def current(self):
		return self.steps[-1] if self.steps else None


	def new_step(self, *messages, debug=True):
		self.steps.append(Step(self, ' '.join(map(str,messages)), debug=debug))
		self.current.number = len(self.steps) - 1
		if debug: rprint(f'\n{self.current}')
		return self.current


	def gcode(self):
		"""Return the gcode for all steps."""
		r = []
		for i,step in enumerate(self.steps):
			g = step.gcode(include_start=not any([isinstance(l.lineno, int) for l in r]))

			if not g:
				continue

			#--- Fill in any fake moves we need between steps ---
			#Find the first "real" extruding move in this step, if any
			start_extrude = find(g, lambda l:l.is_xyextrude() and isinstance(l.lineno, int))

			if r and start_extrude:
				#Find the last print head position
				if missing_move := self.layer.lines[:start_extrude.lineno].end():
					new_line = missing_move.as_xymove()
					new_line.comment = f'---- fake inter-step move from {missing_move.lineno}'
					new_line.fake = True
					new_line.lineno = ''
					g.append(new_line)
					rprint(f'  new step line: {new_line}')

			#Put the step-delimiter comment first; do it last to prevent issues
			g.insert(0, GCLine(#lineno=r[-1].lineno+.5 if r else 0.5,
				fake=True,
				comment=f'Step {step.number} ({len(g)} lines): {step.name} ---------------------------'))

			r.extend(g)

		#Finally add any extra attached to the layer
		if r:
			r.append(GCLine(fake=True, comment='Layer postamble ------'))
		r.extend(self.layer.postamble)

		return r


	def plot(self, prev_layer:TLayer=None, stepnum=None, prev_layer_only_outline=True):
		steps        = self.steps
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
				prev_layer.plot(fig,
						move_colors    = [self.style['old_layer']['line']['color']],
						extrude_colors = [self.style['old_layer']['line']['color']],
						only_outline   = prev_layer_only_outline,
				)

			#Plot the entire thread path that will be routed this layer
			if hasattr(self.layer, 'snapped_thread'):
				fig.add_trace(go.Scatter(**segs_xy(*self.layer.snapped_thread,
					mode='lines', **self.style['all_thread'])))

			#Plot the thread from the bed anchor or the layer anchor to the first
			# step's anchor
			steps[0].plot_thread(fig,
				getattr(self.layer, 'start_anchor', steps[0].printer.bed.anchor))

			#Plot any geometry that was printed in the previous step
			if stepnum > 0:
				segs = set.union(*[set(s.gcsegs) for s in steps[:stepnum]])
				steps[stepnum-1].plot_gcsegments(fig, segs,
						style={'gc_segs': self.style['old_segs']})

			#Plot geometry and thread from previous steps
			for i in range(0, stepnum):

				#Plot the thread from the previous steps's anchor to the current step's
				# anchor
				if i > 0:
					steps[i].plot_thread(fig,
							steps[i-1].printer.anchor,
							style={'thread': self.style['old_thread']},
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
