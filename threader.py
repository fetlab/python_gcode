import plotly.graph_objects as go
from copy import deepcopy
from Geometry3D import Circle, Vector, Segment, Point, intersection, distance
from math import sin, cos, degrees, radians
from typing import List
from geometry_helpers import GPoint, GSegment, HalfLine, segs_xy
from fastcore.basics import store_attr
from math import atan2
from tlayer import TLayer
from gcline import GCLine, GCLines
from util import Saver

from rich.console import Console
rprint = Console(style="on #272727", force_jupyter=True).print

# --- Options for specific setups ---
# What size does the slicer think the bed is?
effective_bed_size =  79, 220

#Where is the ring center, according to the effective bed coordinate system?
# Note that the ring will be wider than the bed. I got these coordinates via
# the Ender 3 CAD model.
ring_center = 36, 28

#What is the radius of the circle inscribed by the thread outlet from the
# carrier?
ring_radius = 92.5

"""
Usage notes:
	* The thread should be anchored on the bed such that it doesn't intersect the
		model on the way to its first model-anchor point.
"""

###########
# TO DO NEXT:
# Account for skipped line numbers in TLayer.gcode()
##########

"""TODO:
	* [X] layer.intersect(thread)
	* [ ] gcode generator for ring
	* [X] plot() methods
	* [X] thread_avoid()
	* [X] thread_intersect
	* [X] wrap Geometry3D functions with units; or maybe get rid of units again?
	* [X] think about how to represent a layer as a set of time-ordered segments
				that we can intersect but also as something that has non-geometry components
				* Also note the challenge of needing to have gCode be Segments but keeping the
					gcode info such as move speed and extrusion amount
					* But a Segment represents two lines of gcode as vertices....
	* [X] Order isecs['isec_points'] in the Layer.anchors() method
	* [ ] gcode -> move to start point of a Segment after a print order change
"""

#https://stackoverflow.com/a/31174427/49663
import functools
def rgetattr(obj, attr, *args):
	def _getattr(obj, attr):
		return getattr(obj, attr, *args)
	return functools.reduce(_getattr, [obj] + attr.split('.'))
def rsetattr(obj, attr, val):
	pre, _, post = attr.rpartition('.')
	return setattr(rgetattr(obj, pre) if pre else obj, post, val)

#Modified from https://stackoverflow.com/a/2123602/49663
def attrhelper(attr, after=None):
	"""Generate functions which get and set the given attr. If the parent object
	has a '.attr_changed' function or if after is defined, and the attr changes,
	call that function with arguments (attr, old_value, new_value):

		class Foo:
			a = property(**attrsetter('_a'))
			b = property(**attrsetter('_b'))
			def attr_changed(self, attr, old_value, new_value):
				print(f'{attr} changed from {old_value} to {new_value}')

	Uses rgetattr and rsetattr to work with nested values like '_a.x'.
	"""
	def set_any(self, value):
		old_value = rgetattr(self, attr)
		rsetattr(self, attr, value)
		if value != old_value:
			f = getattr(self, 'attr_changed', after) or (lambda a,b,c: 0)
			f(attr, old_value, value)

	def get_any(self):
		return rgetattr(self, attr)

	return {'fget': get_any, 'fset': set_any}



def update_figure(fig, name, style, what='traces'):
	"""Update traces, shapes, etc for the passed figure object for figure members with
	the given name.  style should be a dict like {name: {'line': {'color': 'red'}}} .
	"""
	if style and name in style:
		getattr(fig, f'update_{what}')(selector={'name':name}, **style[name])


class GCodeException(Exception):
	"""Utility class so we can get an object for debugging easily. Use in this
	code like:

		raise GCodeException(segs, 'here are segments')

	then (e.g. in Jupyter notebook):

		try:
			steps.plot()
		except GCodeException as e:
			print(len(e.obj), 'segments to print')
	"""

	def __init__(self, obj, message):
		self.obj = obj
		self.message = message



class Ring:
	"""A class representing the ring and thread carrier."""
	#Default plotting style
	style = {
		'ring':      {'line': dict(color='white', width=10), 'opacity':.25},
		'indicator': {'line': dict(color='blue',  width= 4)},
	}

	#TODO: add y-offset between printer's x-axis and ring's x-axis
	def __init__(self, radius=100, angle=0, center:GPoint=None):
		self.radius        = radius
		self._angle        = angle
		self.initial_angle = angle
		self.center        = center or GPoint(radius, 0, 0)
		self.geometry      = Circle(self.center, Vector.z_unit_vector(), self.radius, n=100)

		#Defaults for rotating gear
		steps_per_rotation  = 200 * 16   #For the stepper motor; 16 microsteps
		motor_gear_teeth    = 30
		ring_gear_teeth     = 125

		#Set to -1 if positive E commands make the ring go clockwise
		self.rot_mul        = 1  # 1 since positive steps make it go CCW

		#How many motor steps per degree?
		self.esteps_degree = int(
			steps_per_rotation * ring_gear_teeth / motor_gear_teeth / 360)


	x = property(**attrhelper('center.x'))
	y = property(**attrhelper('center.y'))
	z = property(**attrhelper('center.z'))


	def __repr__(self):
		return f'Ring({self._angle:.2f}°, {self.center})'


	def gcode_preamble(self) -> GCLines:
		"""Return any code that should go in the preamble of a .gcode file."""
		return [
			GCLine(code='T1', comment='Switch to ring extruder'),
			GCLine(code='M302', args={'P1':1}, comment='Disable cold extrusion prevention'),
			GCLine(code='M92', args=dict(T=1, E=self.esteps_degree),
				comment='Set steps per degree of ring rotation'),
			GCLine(code='T0', comment='Switch back to default extruder'),
		]


	def attr_changed(self, attr, old_value, new_value):
		rprint(f'Ring.{attr} changed from {old_value} to {new_value}')


	@property
	def angle(self):
		return self._angle


	@angle.setter
	def angle(self, new_pos:degrees):
		self.set_angle(new_pos)


	@property
	def point(self):
		return self.angle2point(self.angle)


	def set_angle(self, new_angle:degrees, direction=None):
		"""Set a new angle for the ring. Optionally provide a preferred movement
		direction as 'CW' or 'CCW'; if None, it will be automatically determined."""
		self.initial_angle = self._angle
		self._angle = new_angle
		self._direction = direction


	def carrier_location(self, offset=0):
		"""Used in plotting."""
		return GPoint(
			self.center.x + cos(radians(self.angle))*(self.radius+offset),
			self.center.y + sin(radians(self.angle))*(self.radius+offset),
			self.center.z
		)


	def angle2point(self, angle:degrees):
		"""Return an x,y,z=0 location on the ring based on the given angle, without
		moving the ring. Assumes that the bed's bottom-left corner is (0,0).
		Doesn't take into account a machine that uses bed movement for the y-axis,
		but just add the y value to the return from this function."""
		return GPoint(
			cos(radians(angle)) * self.radius + self.center.x,
			sin(radians(angle)) * self.radius + self.center.y,
			self.center.z
		)


	def gcode_move(self):
		"""Return the gcode necessary to move the ring from its current angle
		to its requested one."""
		#Were there any changes in angle?
		if self.angle == self.initial_angle:
			return []

		#Find "extrusion" amount - requires M92 has set steps/degree correctly
		dist = self.angle - self.initial_angle
		dir_mul = -1 if ((dist+360)%360 < 180) else 1  #Determine CW/CCW rotation
		extrude = self.rot_mul * dist * dir_mul

		gc = ([
			GCLine(code='T1', comment='Switch to ring extruder'),
			GCLine(code='M82', comment='Set relative extrusion mode'),
			GCLine(code='G1', args={'E':round(extrude,3), 'F':8000},
				comment=f'Ring move from {self.initial_angle:.2f}° to {self.angle:.2f}°'),
		])

		self._angle = self.initial_angle
		return gc


	def plot(self, fig, style=None):
		fig.add_shape(
			name='ring',
			type='circle',
			xref='x', yref='y',
			x0=self.center.x-self.radius, y0=self.center.y-self.radius,
			x1=self.center.x+self.radius, y1=self.center.y+self.radius,
			**self.style['ring'],
		)
		update_figure(fig, 'ring', style, what='shapes')

		ringwidth = next(fig.select_shapes(selector={'name':'ring'})).line.width

		c1 = self.carrier_location(offset=-ringwidth/2)
		c2 = self.carrier_location(offset=ringwidth/2)
		fig.add_shape(
			name='indicator',
			type='line',
			xref='x', yref='y',
			x0=c1.x, y0=c1.y,
			x1=c2.x, y1=c2.y,
			**self.style['indicator'],
		)
		update_figure(fig, 'indicator', style, what='shapes')



class Bed:
	"""A class representing the print bed."""
	#Default plotting style
	style = {
			'bed': {'line': dict(color='rgba(0,0,0,0)'),
							'fillcolor': 'LightSkyBlue',
							'opacity':.25,
						 },
	}

	def __init__(self, anchor=(0, 0, 0), size=(220, 220)):
		"""Anchor is where the thread is initially anchored on the bed. Size is the
		size of the bed. Both are in mm."""
		self.anchor = GPoint(*anchor)
		self.size   = size

		#Current gcode coordinates of the bed
		self.x      = 0
		self.y      = 0


	def __repr__(self):
		return f'Bed({self.x}, {self.y}, ⚓︎{self.anchor})'


	def plot(self, fig, style=None):
		fig.add_shape(
			name='bed',
			type='rect',
			xref='x',                 yref='y',
			x0=self.x,                y0=self.y,
			x1=self.x + self.size[0], y1=self.y + self.size[1],
			**self.style['bed'],
		)
		update_figure(fig, 'bed', style, what='shapes')



class Printer:
	"""Maintains the state of the printer/ring system. Holds references to the
	Ring and Bed objects.
	"""
	style = {
		'thread': {'mode':'lines', 'line': dict(color='white', width=1, dash='dot')},
		'anchor': {'mode':'markers', 'marker': dict(color='red', symbol='x', size=4)},
	}

	def __init__(self, z=0):
		self._x, self._y, self._z = 0, 0, 0
		self.bed  = Bed(size=effective_bed_size)
		self.ring = Ring(radius=ring_radius, center=GPoint(ring_center[0], ring_center[1], z))

		self.anchor = GPoint(self.bed.anchor[0], self.bed.anchor[1], z)

		#Default states
		self.extruder_no    = GCLine(code='T0',  args={}, comment='Switch to main extruder')
		self.extrusion_mode = GCLine(code='M82', args={}, comment='Set relative extrusion mode')



	#Create attributes which call Printer.attr_changed on change
	x = property(**attrhelper('_x'))
	y = property(**attrhelper('_y'))
	z = property(**attrhelper('_z'))


	def __repr__(self):
		return f'Printer({self.bed}, {self.ring})'


	def attr_changed(self, attr, old_value, new_value):
		return
		if attr[1] in 'xyz':
			setattr(self.ring, attr[1], new_value)
			if attr[1] in 'xy':
				#Move the ring to keep the thread intersecting the anchor
				self.thread_intersect(self.anchor, set_new_anchor=False, move_ring=True)


	def freeze_state(self):
		"""Return a copy of this Printer object, capturing the state."""
		return deepcopy(self)


	def gcode(self, lines):
		"""Return gcode. lines is a list of GCLines involved in the current step.
		Use them to generate gcode for the ring to maintain the thread
		trajectory."""
		gc = []

		#Variables to be restored, in the order they should be restored
		save_vars = 'extruder_no', 'extrusion_mode'

		#"Execute" each line of gcode. If a line is a xymove, Printer.attr_changed()
		# will be called, which in turn will assign a new relative location to the
		# Ring, then call Printer.thread_intersect to move the ring to maintain the
		# intersection between the thread and the target.
		for line in lines:
			self.execute_gcode(line)
			gc.append(line)

			if line.is_xymove():
				newlines = []
				with Saver(self, save_vars) as saver:
					for rline in self.ring.gcode_move():
						self.execute_gcode(rline)
						newlines.append(rline)

				saved = [saver.saved[var] for var in save_vars if var in saver.changed]
				for oldline in saved:
					self.execute_gcode(oldline)
					newlines.append(oldline)

				#Manufacture bogus fractional line numbers for display
				for i,l in enumerate(newlines):
					l.lineno = line.lineno + (i+1)/len(newlines)

				gc.extend(newlines)

		return gc
		#filter gc to drop None values
		#return list(filter(None, gc))


	def execute_gcode(self, gcline:GCLine):
		"""Update the printer state according to the passed line of gcode."""
		if gcline.is_xymove():
			self.x = gcline.args['X']
			self.y = gcline.args['Y']
		elif gcline.code in ['M82', 'M83']:
			self.extrusion_mode = gcline
		elif gcline.code and gcline.code[0] == 'T':
			self.extruder_no = gcline


	def anchor_to_ring(self) -> Segment:
		"""Return a Segment representing the current thread, from the anchor point
		to the ring."""
		return GSegment(self.anchor, self.ring.point)


	def thread_avoid(self, avoid: List[Segment]=[], move_ring=True):
		"""Rotate the ring so that the thread is positioned to not intersect the
		geometry in avoid. Return the rotation value."""
		"""Except in the case that the anchor is still on the bed, the anchor is
			guaranteed to be inside printed material (by definition). We might have
			some cases where for a given layer there are two gcode regions (Cura sets
			this up) and the anchor is in one of them. Probably the easiest thing
			here is just to exhaustively test.
		"""
		#First check to see if we have intersections at all; if not, we're done!
		thr = self.anchor_to_ring()
		if not any(thr.intersection(i) for i in avoid):
			rprint(f"Thread intersects 0 of {len(avoid)} geometry segments")
			return

		#TODO: this is the computational geometry visibility problem and should be
		# done with a standard algorithm
		#Next, try to move in increments around the current position to minimize movement time
		# use angle2point()
		for inc in range(10, 190, 10):
			for ang in (self.ring.angle + inc, self.ring.angle - inc):
				thr = GSegment(self.anchor, self.ring.angle2point(ang))
				if not any(thr.intersection(i) for i in avoid):
					if move_ring:
						self.ring.set_angle(ang)
					return ang

		rprint("Couldn't find a way to avoid thread/geometry intersections")
		return


	def thread_intersect(self, target, anchor=None, set_new_anchor=True, move_ring=True):
		"""Rotate the ring so that the thread starting at anchor intersects the
		target Point. By default sets the anchor to the intersection. Return the
		rotation value."""
		anchor = anchor or self.anchor.as2d()
		# if target.as2d() == anchor.as2d():
		# 	rprint('thread_intersect with target == anchor, doing nothing')
		# 	return self.ring.angle

		#Form a half line (basically a ray) from the anchor through the target
		hl = HalfLine(anchor, target.as2d())
		rprint(f'HalfLine from {self.anchor} to {target}:\n', hl)

		isec = intersection(hl, self.ring.geometry)
		if isec is None:
			raise GCodeException(hl, "Anchor->target ray doesn't intersect ring")

		#The intersection is always a Segment; we want the endpoint furthest from
		# the anchor
		ring_point = sorted(isec[:], key=lambda p: distance(anchor, p),
				reverse=True)[0]

		#Now we need the angle between center->ring and the x axis
		ring_angle = degrees(atan2(ring_point.y - self.ring.center.y,
															 ring_point.x - self.ring.center.x))

		if move_ring:
			self.ring.set_angle(ring_angle)

		if set_new_anchor:
			self.anchor = target

		return ring_angle


	def plot_thread_to_ring(self, fig, style=None):
		#Plot a thread from the current anchor to the carrier
		fig.add_trace(go.Scatter(**segs_xy(self.anchor_to_ring(),
			name='thread', **self.style['thread'])))
		update_figure(fig, 'thread', style)


	def plot_anchor(self, fig, style=None):
		fig.add_trace(go.Scatter(x=[self.anchor.x], y=[self.anchor.y],
			name='anchor', **self.style['anchor']))
		update_figure(fig, 'anchor', style)



class Step:
	#Default plotting style
	style = {
		'gc_segs': {'mode':'lines', 'line': dict(color='green',  width=1)},
		'thread':  {'mode':'lines', 'line': dict(color='yellow', width=1, dash='dot')},
	}

	def __init__(self, steps_obj, name=''):
		store_attr()
		self.printer = steps_obj.printer
		self.layer   = steps_obj.layer
		self.gcsegs  = []
		self.number  = -1


	def __repr__(self):
		return f'<Step {self.number} ({len(self.gcsegs)} segments)>: [light_sea_green italic]{self.name}[/]\n  {self.printer}'


	def gcode(self):
		"""Render the gcode involved in this Step, returning a list of GCLines:
			* Sort added gcode lines by line number. If there are breaks in line
				number, check whether the represented head position also has a break.
				If so, add gcode to move the head correctly.
			* Whenever there is a movement, we need to check with the Printer object
				whether we should move the ring to keep the thread at the correct angle.

		self.gcsegs is made of GSegment objects, each of which should have a .gc_line1
		and .gc_line2 member which are GCLines.
		"""
		gcode = []

		if not self.gcsegs:
			if self.printer.ring.initial_angle != self.printer.ring.angle:
				#Variables to be restored, in the order they should be restored
				save_vars = 'extruder_no', 'extrusion_mode'

				newlines = []
				with Saver(self.printer, save_vars) as saver:
					for rline in self.printer.ring.gcode_move():
						self.printer.execute_gcode(rline)
						newlines.append(rline)

				saved = [saver.saved[var] for var in save_vars if var in saver.changed]
				for oldline in saved:
					self.printer.execute_gcode(oldline)
					newlines.append(oldline)

				gcode.extend(newlines)
			return gcode

		#Sort gcsegs by the first gcode line number in each
		self.gcsegs.sort(key=lambda s:s.gc_lines.first.lineno)

		#Find breaks in line numbers between gc_lines for two adjacent segments
		for seg1, seg2 in zip(self.gcsegs[:-1], self.gcsegs[1:]):
			#Get line numbers bordering the interval between the two segments
			seg1_last  = seg1.gc_lines.last.lineno
			seg2_first = seg2.gc_lines.first.lineno

			if seg2_first - seg1_last == 0:
				#Don't add last line to avoid double lines from adjacent segments
				gcode.extend(seg1.gc_lines.data[:-1])
			else:
				#Include the last line since the next segment doesn't duplicate it
				gcode.extend(seg1.gc_lines.data)

				#If the line numbers are not contiguous, check if a move is required
				if missing_move := self.layer.lines[seg1_last+1:seg2_first].end():
					#seg2 won't have the repeated last line from seg1, so add it
					gcode.append(seg1.gc_lines.last)

					#Create a "fake" new gcode line to position the head in the right place
					# for the next extrusion
					new_line = missing_move.as_xymove()
					new_line.lineno = float(new_line.lineno) #hack for easy finding "fake" lines
					new_line.comment = f'---- Skipped {seg2_first-seg1_last-1} lines; fake move'
					gcode.append(new_line)

		#Add last segment's lines
		gcode.extend(self.gcsegs[-1].gc_lines)

		#And any extra attached to the layer
		gcode.extend(self.layer.postamble)

		#"Execute" the gcode so we can keep up with the printer state
		for line in gcode:
			self.printer.execute_gcode(line)

		return gcode


	def add(self, layer:TLayer, gcsegs:List[GSegment]):
		#TODO: layer argument not used
		rprint(f'Adding {len([s for s in gcsegs if not s.printed])}/{len(gcsegs)} segs to Step')
		for seg in gcsegs:
			if not seg.printed:
				self.gcsegs.append(seg)
				seg.printed = True


	def __enter__(self):
		return self


	def __exit__(self, exc_type, value, traceback):
		if exc_type is not None:
			return False
		#Otherwise store the current state
		self.printer = self.printer.freeze_state()


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


	def plot_thread(self, fig, start:Point, style=None):
		#Plot a thread segment, starting at 'start', ending at the current anchor
		if start == self.printer.anchor:
			return
		fig.add_trace(go.Scatter(
			x=[start.x, self.printer.anchor.x],
			y=[start.y, self.printer.anchor.y],
			**self.style['thread'],
		))
		update_figure(fig, 'thread', style)



class Steps:
	#Default plotting style
	style = {
		'old_segs':   {'line_color': 'gray'},
		'old_thread': {'line_color': 'blue'},
		'old_layer':  {'line': dict(color='gray', dash='dot')},
	}
	def __init__(self, layer, printer):
		store_attr()
		self.steps = []
		self._current_step = None


	def __repr__(self):
		return '\n'.join(map(repr, self.steps))


	@property
	def current(self):
		return self.steps[-1] if self.steps else None


	def new_step(self, *messages):
		self.steps.append(Step(self, ' '.join(map(str,messages))))
		self.current.number = len(self.steps)
		rprint(f'[light_sea_green italic]{self.current}')
		return self.current


	def gcode(self):
		"""Return the gcode for all steps."""
		r = GCLines()
		for i,step in enumerate(self.steps):
			g = step.gcode()
			g.insert(0, GCLine(lineno=r.last.lineno+.5 if r else 0.5,
				comment=f'Step {i} ({len(g)} lines) ---------------------------'))
			if g[1:] and not isinstance(g[1].lineno, (int,float)):
				last = r.last.lineno if r else 0
				for i,l in enumerate(g[1:]):
					l.lineno = last + (i+1)/len(g[1:])
			r.extend(g)
		return r


	def plot(self, prev_layer:TLayer=None):
		steps = self.steps
		last_anchor = steps[0].printer.anchor

		for stepnum,step in enumerate(steps):
			rprint(f'Step {stepnum}: {step.name}')
			fig = go.Figure()

			#Plot the bed
			step.printer.bed.plot(fig)

			#Plot the outline of the previous layer, if provided
			if prev_layer:
				prev_layer.plot(fig,
						move_colors    = [self.style['old_layer']['line']['color']],
						extrude_colors = [self.style['old_layer']['line']['color']],
						only_outline   = True,
				)

			#Plot the thread from the bed anchor to the first step's anchor
			steps[0].plot_thread(fig, steps[0].printer.bed.anchor)

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

			#Plot thread trajectory from current anchor to ring
			step.printer.plot_thread_to_ring(fig)

			#Plot thread from last step's anchor to current anchor
			step.plot_thread(fig, last_anchor)
			last_anchor = step.printer.anchor

			#Plot anchor/enter/exit points if any
			if thread_seg := getattr(step.printer, 'thread_seg', None):
				step.printer.plot_anchor(fig)

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
			fig.update_layout(template='plotly_dark',# autosize=False,
					yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
					margin=dict(l=0, r=20, b=0, t=0, pad=0),
					showlegend=False,)
			fig.show('notebook')

		rprint('Finished routing this layer')



class Threader:
	def __init__(self, gcode):
		store_attr()
		self.printer = Printer()

		#TODO: add special preamble to gcode object for when gcode is generated to
		# e.g. set M92. Maybe call each gcode-generating class for preamble
		# commands first?


	def route_model(self, thread):
		for layer in self.gcode.layers:
			self.layer_steps.append(self.route_layer(thread, layer))
		return self.layer_steps


	def route_layer(self, thread_list, layer):
		"""Goal: produce a sequence of "steps" that route the thread through one
		layer. A "step" is a set of operations that diverge from the original
		gcode; for example, printing all of the non-thread-intersecting segments
		would be one "step".
		"""
		rprint(f'Route {len(thread_list)}-segment thread through layer:\n  {layer}')
		for i, tseg in enumerate(thread_list):
			rprint(f'\t{i}. {tseg}')

		self.printer.z = layer.z

		self.steps = Steps(layer=layer, printer=self.printer)
		steps = self.steps

		#Get the thread segments to work on
		thread = layer.flatten_thread(thread_list)
		steps.flat_thread = thread

		if not thread:
			rprint('Thread not in layer at all')
			with steps.new_step('Thread not in layer') as s:
				s.add(layer, layer.lines)
			return steps

		#Snap thread to anchors
		thread = layer.anchor_snap(thread)

		rprint(f'{len(thread)} thread segments in this layer:\n\t{thread}')

		#Find geometry that will not be intersected by any segments
		# TODO: do these need to be half-lines from each anchor to the ring?
		to_print = layer.non_intersecting(thread)

		try:

			with steps.new_step(f'Move thread to avoid {len(to_print)} lines of non-intersecting geometry'):
				self.printer.thread_avoid(to_print)

			with steps.new_step('Print non-intersecting geometry') as s:
				s.add(layer, to_print)


			# --- Individual thread segments
			for i,thread_seg in enumerate(thread):
				self.printer.layer = layer
				self.printer.thread_seg = thread_seg
				anchor = thread_seg.end_point
				with steps.new_step(f'Move thread to overlap anchor at {anchor}') as s:
					self.printer.thread_intersect(anchor)

				traj = self.printer.anchor_to_ring().set_z(layer.z)
				layer.intersect_model(traj)
				to_print = [s for s in layer.non_intersecting(thread[i:] + [traj]) if not s.printed]
				if to_print:
					msg = (f'Print {len(to_print)} segments not overlapping thread trajectory {traj}',
								 f'or the {len(thread[i:])} remaining thread segments')
					with steps.new_step(*msg) as s:
						rprint(len(layer.non_intersecting(thread[i:] + [traj])), 'non-intersecting')
						s.add(layer, layer.non_intersecting(thread[i:] + [traj]))

				to_print = [s for s in layer.intersecting(thread_seg) if not s.printed]
				if to_print:
					with steps.new_step(f'Print {len(to_print)} overlapping layers segments') as s:
						s.add(layer, to_print)


			# --- Print what's left
			remaining = [s for s in layer.geometry.segments if not s.printed]
			if remaining:
				with steps.new_step('Move thread to avoid remaining geometry') as s:
					self.printer.thread_avoid(remaining)

				with steps.new_step(f'Print {len(remaining)} remaining geometry lines') as s:
					s.add(layer, remaining)

			rprint('[yellow]Done with thread for this layer[/];',
					len([s for s in layer.geometry.segments if not s.printed]),
					'gcode lines left')

		except Exception as e:
			raise GCodeException((steps, e), "There was a problem")

		return steps


"""
TODO:
Need to have a renderer that will take the steps and the associated Layer and
spit out the final gcode. It needs to take into account preambles, postambles,
and non-extrusion lines, and also to deal with out-of-order extrusions so it
can move to the start of the necessary line. Possibly there needs to be some
retraction along the way.
"""


if __name__ == "__main__":
	import gcode
	import numpy as np
	from Geometry3D import Segment, Point
	from danutil import unpickle
	tpath = np.array(unpickle('/Users/dan/r/thread_printer/stl/test1/thread_from_fusion.pickle')) * 10
	thread_transform = [131.164, 110.421, 0]
	tpath += [thread_transform, thread_transform]
	thread_geom = tuple([Segment(Point(*s), Point(*e)) for s,e in tpath])
	excp = None
	try:
		g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode', layer_class=TLayer)
	except GCodeException as e:
		excp = e.obj
		rprint(f'GCodeException: {e.message}')
	else:
		t = Threader(g)
		steps = t.route_layer(thread_geom, g.layers[49])
