from typing import List
from util import find
from step import Step
from logger import rprint
from gcline import GCLine


class Steps:
	def __init__(self, layer, printer, debug_plot=False):
		self.layer         = layer
		self.printer       = printer
		self.debug_plot    = debug_plot
		self.steps         = []
		self._current_step = None


	def __repr__(self):
		return f'{len(self.steps)} Steps for layer {self.layer}\n' + '\n'.join(map(repr, self.steps))


	@property
	def current(self):
		return self.steps[-1] if self.steps else None


	def new_step(self, *messages, debug=True, debug_plot=None):
		self.steps.append(Step(self, ' '.join(map(str,messages)), debug=debug,
												 debug_plot=self.debug_plot if debug_plot is None else debug_plot))
		self.current.number = len(self.steps) - 1
		self.current.printer.debug_avoid = set()
		if debug: rprint(f'\n{self.current}')
		return self.current


	def step_exited(self, step):
		"""When a Step exits it will call this. Janky!"""
		# if step.debug_plot:
		# 	with get_output():
		# 		self.plot(stepnum=step.number)
		if not step.valid:
			rprint(f"Step {step.number} invalid, deleting")
			del(self.steps[-1])


	def gcode(self):
		"""Return the gcode for all steps."""
		r: List[GCLine] = []
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
