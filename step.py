from typing import List
from enum import Enum
from fastcore.basics import store_attr

from geometry import GSegment, GPoint
from util import linf, Saver
from logger import rprint, rich_log
import logging

import plotly.graph_objects as go
from plot_helpers import update_figure


class Step:
	#Default plotting style
	style = {
		'gc_segs':    {'mode':'lines', 'line': dict(color='green',  width=2)},
		'thread':     {'mode':'lines', 'line': dict(color='yellow', width=1, dash='dot')},
		'old_segs':   {'line': dict(color= 'gray', width=1)},
		'old_thread': {'line_color': 'blue'},
		'old_layer':  {'line': dict(color='gray', dash='dot', width=.5)},
		'all_thread': {'line': dict(color='cyan', dash='dot', width=.5)},
	}

	def __init__(self, steps_obj, name='', debug=True):
		store_attr()
		self.printer = steps_obj.printer
		self.layer   = steps_obj.layer
		self.gcsegs  = []
		self.number  = -1
		self.debug   = debug
		self.caller  = linf(2)
		self.valid   = True


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

		if False:

			last_lineno = gcode[-1].lineno if gcode else float('inf')
			first_move = seg.gc_lines.start()

			for line in seg.gc_lines:
				action = None
				line_diff = line.lineno - last_lineno

				if line_diff == 0:
					#This line is the same as the last one, or the first extruding
					# movement line in a Step, so skip it
					action = actions.SKIP

				#elif line.is_xyextrude() and line == first_move:
				#	#This is an extrusion move, and the first move in the Segment; skip it
				#	action = actions.SKIP

				elif line_diff == 1:
					#The first line of this segment directly follows the last saved line
					# of gcode, so we can save it
					action = actions.SAVE

				else:
					#There is a line-number gap between the last-saved line of gcode and
					# the current line, or this is the first line in a new Step
					if line.is_xymove():
						if line_diff < 0 and include_start:
							action = actions.SAVE
						elif self.printer.xy != line.xy:
							if line.is_xyextrude():
								if line == first_move:
									#Extruding line as the first move, so we need to make a fake
									# line instead
									action = actions.FAKE_SKIP
								else:
									action = actions.FAKE_SAVE
							else:
								action = actions
							#There's a gap, so we need to manufacture a fake line. Save the
							# current line if it's not the first line in the Step
							action = actions.FAKE_SKIP if line_diff < 0 else actions.FAKE_SAVE
						else:
							action = actions.SKIP
					else:
						#Not a move line, so just save it
						action = actions.SAVE

				#Now take the requested action
				old_last_lineno = last_lineno if last_lineno != float('inf') else 'XX'
				last_lineno = line.lineno
				if action == actions.SKIP:
					continue
				elif action == actions.SAVE:
					pass
				elif action == actions.FAKE_SAVE or action == actions.FAKE_SKIP:
					rprint(f'[{i}] {old_last_lineno} → {line.lineno} ({line_diff}): {action.name}')
					#Need to construct a move to get the head in the right place; find
					# the last move before this line and move the print head to that
					# line's destination
					if missing_move := self.layer.lines[:line.lineno].end():
						new_line = missing_move.as_xymove()
						new_line.fake = True
						new_line.lineno = ''
						if gcode:
							new_line.comment = f'---- Skipped {gcode[-1].lineno+1}–{line.lineno-1}; fake move from {missing_move.lineno}'
						else:
							new_line.comment = f'---- Fake move from {missing_move.lineno}'
						rprint(f'new line from {missing_move.lineno}: {new_line}')
						gcode.append(new_line)
						self.printer.execute_gcode(new_line)
				else:
					raise ValueError(f'No action set for line {i}:\n  {line}\nof segment {seg}')

				#We get here for actions.SAVE and actions.FAKE_*
				if action != actions.FAKE_SKIP:
					gcode.append(line)
					self.printer.execute_gcode(line)

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


	def plot_gcsegments(self, fig, gcsegs=None, style=None):
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

