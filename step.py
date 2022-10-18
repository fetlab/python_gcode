from typing import List
from enum import Enum

from geometry import GSegment, GPoint
from util import linf, Saver
from logger import rprint, rich_log
import logging

import plotly.graph_objects as go
from plot_helpers import update_figure, plot_segments


class Step:
	#Default plotting style
	style: dict[str, dict] = {
		'gc_segs':    {'mode':'lines', 'line': dict(color='green',  width=2)},
		'thread':     {'mode':'lines', 'line': dict(color='yellow', width=1, dash='dot')},
		'old_segs':   {'line': dict(color= 'gray', width=1)},
		'old_thread': {'line_color': 'blue'},
		'old_layer':  {'line': dict(color='gray', dash='dot', width=.5)},
		'all_thread': {'line': dict(color='cyan', dash='dot', width=.5)},
	}

	def __init__(self, steps_obj, name='', debug=True, debug_plot=False):
		self.name       = name
		self.debug      = debug
		self.debug_plot = debug_plot
		self.steps_obj  = steps_obj
		self.printer    = steps_obj.printer
		self.layer      = steps_obj.layer
		self.gcsegs:List[GSegment] = []
		self.number     = -1
		self.caller     = linf(2)
		self.valid      = True


	def __repr__(self):
		return(self.caller + ' ' +
					 f'<Step {self.number} ' +
					(f'{len(self.gcsegs)} segments)>: ' if self.gcsegs else '') +
					 f'[light_sea_green italic]{self.name}[/]>')


	def gcode(self, include_start=False) -> List:
		"""Render the gcode involved in this Step, returning a list of GCLines:
			* Sort added gcode lines by line number. If there are breaks in line
				number, check whether the represented head position also has a break.
				If so, add gcode to move the head correctly.

		self.gcsegs is made of GSegment objects, each of which should have a .gc_line1
		and .gc_line2 member which are GCLines.
		"""
		rprint(f'[red]————— START STEP {self.number}: {self.name} —————')

		gcode = []

		if not self.gcsegs:
			if self.printer.ring.initial_angle != self.printer.ring.angle:
				#Variables to be restored, in the order they should be restored: we
				# "execute" each line of ring-movement gcode to update the machine
				# state, but want to reset the extruder to the current state after the
				# ring moves.
				save_vars = 'extruder_no', 'extrusion_mode'

				newlines = []
				with Saver(self.printer, save_vars) as saver:
					for rline in self.printer.ring.gcode_move():
						self.printer.execute_gcode(rline)
						newlines.append(rline)

				#Restore extruder state if it was changed
				for var in save_vars:
					if var in saver.changed:
						self.printer.execute_gcode(saver.saved[var])
						newlines.append(saver.saved[var])

				gcode.extend(newlines)
			return gcode
		return []

		#Sort gcsegs by the first gcode line number in each
		self.gcsegs.sort(key=lambda s:s.gc_lines.first.lineno)

		"""
		Conditions:
			In a 2-line Segment:
				If the first line is an Extrude:
					SKIP
				If the first line is an XY move:
					SAVE
				The second line is always an Extrude. Do:
					If the previous saved line number is 1 less:
						SAVE
					else:
						create and SAVE a FAKE
						SAVE this line

			In a > 2-line Segment, there is always one or more X/Y Move lines, but
				only ever one Extrude line, which is always the last line.
			SAVE every line
		"""

		actions = Enum('Actions', 'SKIP SAVE FAKE_SAVE FAKE_SKIP')
		for i, seg in enumerate(self.gcsegs):

			#In a > 2-line Segment, there is always one or more X/Y Move
			# lines, but only ever one Extrude line, which is always the last line.
			# Save and execute every line, as the XY move will put the head in the
			# right place for the extrude.
			if len(seg.gc_lines) > 2:
				for line in seg.gc_lines:
					gcode.append(self.printer.execute_gcode(line))
				continue

			#For 2-line Segments
			l1, l2 = seg.gc_lines.data

			if l1.is_xymove() and not l1.is_xyextrude():
				gcode.append(self.printer.execute_gcode(l1))

			line_diff = l2.lineno - gcode[-1].lineno if gcode else float('inf')
			if line_diff > 0:
				if line_diff > 1:
					new_line = self.layer.lines[:l2.lineno].end().as_xymove()
					new_line.fake = True
					if gcode:
						new_line.comment = f'---- Skipped {gcode[-1].lineno+1}–{l2.lineno-1}; fake move from {new_line.lineno}'
					else:
						new_line.comment = f'---- Fake move from {new_line.lineno}'
					rprint(f'new line from {new_line.lineno}')
					new_line.lineno = ''
					gcode.append(self.printer.execute_gcode(new_line))
				gcode.append(self.printer.execute_gcode(l2))

		return gcode


	def add(self, gcsegs:List[GSegment]):
		rprint(f'Adding {len([s for s in gcsegs if not s.printed])}/{len(gcsegs)} unprinted gcsegs to Step')
		for seg in gcsegs:
			if not seg.printed:
				self.gcsegs.append(seg)
				seg.printed = True


	def __enter__(self):
		if self.debug is False: rich_log.setLevel(logging.CRITICAL)
		return self


	def __exit__(self, exc_type, value, traceback):
		if self.debug is False: rich_log.setLevel(logging.DEBUG)
		self.printer = self.printer.freeze_state()
		#Die if there's an exception
		if exc_type is not None:
			print(f'Exception on Step.__exit__: {exc_type}')
			return False
		#Tell parent Steps object we exited
		self.steps_obj.step_exited(self)


	def plot_gcsegments(self, fig, gcsegs=None, style=None):
		plot_segments(fig,
									gcsegs if gcsegs is not None else self.gcsegs,
									style=self.style['gc_segs'])
		update_figure(fig, 'gc_segs', style)
		return


		#Plot gcode segments. The 'None' makes a break in a line so we can use
		# just one add_trace() call.
		segs = {'x': [], 'y': []}
		segs_to_plot = gcsegs if gcsegs is not None else self.gcsegs
		for seg in segs_to_plot:
			segs['x'].extend([seg.start_point.x, seg.end_point.x, None])
			segs['y'].extend([seg.start_point.y, seg.end_point.y, None])
		fig.add_trace(go.Scatter(**segs, name='gc_segs', **self.style['gc_segs']))
		update_figure(fig, 'gc_segs', style)


	def plot_thread(self, fig, start:GPoint, style=None):
		#Plot a thread segment, starting at 'start', ending at the current anchor
		if start == self.printer.anchor:
			return
		fig.add_trace(go.Scatter(
			x=[start.x, self.printer.anchor.x],
			y=[start.y, self.printer.anchor.y],
			**self.style['thread'],
		))
		update_figure(fig, 'thread', style)

