import plotly.graph_objects as go
from copy import deepcopy
from Geometry3D import Circle, Vector, Segment, Point, intersection, distance
from math import sin, cos, degrees, radians
from typing import List, Collection
from geometry_helpers import GPoint, GSegment, HalfLine, visibility2, angsort, \
														 split_segs, avoid_visible
from plot_helpers import segs_xy, update_figure
from fastcore.basics import store_attr
from math import atan2
from tlayer import TLayer
from gcline import GCLine
from util import Saver, find
from enum import Enum
from gcode import GcodeFile
from rich import print
from more_itertools import grouper, pairwise, partition, bucket

import logging
from lablogging   import AccordionHandler
from rich_output_handler import RichOutputWidgetHandler
import rich.terminal_theme
acclog = None
_rlog = logging.getLogger('threader')
_rlog.setLevel(logging.DEBUG)

def rprint(*args, indent_char=' ', indent=0, **kwargs):
	msg = ''
	for i,arg in enumerate(args):
		if isinstance(arg, (list,tuple)):
			if len(arg) == 0:
				if i > 0: msg += ' '
				msg += str(arg)
			else:
				nl = '\n' + indent_char * indent
				if i > 0: msg += nl
				msg += nl.join(map(str,arg))
				if i < len(args)-1: msg += '\n'
		else:
			if i > 0: msg += ' '
			msg += str(arg)

	style = kwargs.get('style', {})
	if '\n' in msg:
		style.setdefault('line-height', 'normal')

	_rlog.debug(msg, extra={'style':style})


def reinit_logging():
	global acclog
	_rlog.removeHandler(acclog)
	acclog = AccordionHandler(
			handler_class = RichOutputWidgetHandler,
			handler_args  = {
				'theme': rich.terminal_theme.MONOKAI,
				'html_style': {'line-height': 2},
			})
	_rlog.addHandler(acclog)

print('reload threader')

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

#Epsilon for various things
epsilon = 0.25
avoid_epsilon = 1  #how much room to leave around segments

"""
Usage notes:
	* The thread should be anchored on the bed such that it doesn't intersect the
		model on the way to its first model-anchor point.
"""

def unprinted(iterable):
	return set(filter(lambda s:not s.printed, iterable))

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


	def attr_changed(self, attr, old_value, new_value):
		pass


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
			GCLine(code='T1', comment='Switch to ring extruder', fake=True),
			GCLine(code='M82', comment='Set relative extrusion mode', fake=True),
			GCLine(code='G1', args={'E':round(extrude,3), 'F':8000},
				comment=f'Ring move from {self.initial_angle:.2f}° to {self.angle:.2f}°', fake=True),
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
		self._x, self._y, self._z = 0, 0, z
		self.bed  = Bed(size=effective_bed_size)
		self.ring = Ring(radius=ring_radius, center=GPoint(ring_center[0], ring_center[1], z))

		self.anchor = GPoint(self.bed.anchor[0], self.bed.anchor[1], z)

		#Default states
		self.extruder_no    = GCLine(code='T0',  args={}, comment='Switch to main extruder', fake=True)
		self.extrusion_mode = GCLine(code='M82', args={}, comment='Set relative extrusion mode', fake=True)

		self.thread_seg = None


	#Create attributes which call Printer.attr_changed on change
	x = property(**attrhelper('_x'))
	y = property(**attrhelper('_y'))
	z = property(**attrhelper('_z'))

	@property
	def xy(self): return self.x, self.y


	def __repr__(self):
		return f'Printer(⚓︎{self.anchor}, ⌾ {self.ring._angle:.2f}°)'


	def attr_changed(self, attr, old_value, new_value):
		if attr[1] in 'xyz':
			setattr(self.ring, attr[1], new_value)
			if attr[1] in 'xy':
				#Move the ring to keep the thread intersecting the anchor
				self.thread_intersect(self.anchor, set_new_anchor=False, move_ring=True)


	def freeze_state(self):
		"""Return a copy of this Printer object, capturing the state."""
		return deepcopy(self)

		# bed = Bed(self.bed.anchor, self.bed.size)
		# bed.x, bed.y = self.bed.x, self.bed.y

		# ring = Ring(self.ring.radius, self.ring.angle, self.ring.center)

		# printer = Printer(self.z)
		# printer.bed = bed
		# printer.ring = ring
		# printer.anchor = self.anchor
		# printer.thread_seg = self.thread_seg
		# printer.extruder_no = self.extruder_no
		# printer.extrusion_mode = self.extrusion_mode
		# printer._x, printer._y, printer._z = self._x, self._y, self._z

		# return printer


	def gcode(self, lines) -> List:
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

				#Restore extruder state if it was changed
				for var in save_vars:
					if var in saver.changed:
						self.printer.execute_gcode(saver.saved[var])
						newlines.append(saver.saved[var])

				#Manufacture bogus fractional line numbers for display
				for i,l in enumerate(newlines):
					l.lineno = line.lineno + (i+1)/len(newlines)

				gc.extend(newlines)

		return gc
		#filter gc to drop None values
		#return list(filter(None, gc))


	def execute_gcode(self, gcline:GCLine):
		"""Update the printer state according to the passed line of gcode. Return
		the line of gcode for convenience."""
		if gcline.is_xymove():
			self.x = gcline.args['X']
			self.y = gcline.args['Y']
		elif gcline.code in ['M82', 'M83']:
			self.extrusion_mode = gcline
		elif gcline.code and gcline.code[0] == 'T':
			self.extruder_no = gcline
		return gcline


	def anchor_to_ring(self) -> Segment:
		"""Return a Segment representing the current thread, from the anchor point
		to the ring."""
		return GSegment(self.anchor, self.ring.point, z=self.z)


	# TODO TODO TODO
	"""New approach to thread avoid:
		1. Use visibility2(anchor, segs) on the segment(s) that the anchor is
			 snapped to and move the thread to avoid those segments.
		2. Print those segments.
		3. Find segments not intersecting thread, print them.
		4. Use visibilty2() on the remaining segments, move thread, print.

		The point here is that there is no reason to treat the existing
		thread->ring trajectory as important.
	"""

	def thread_avoid(self, avoid: Collection[Segment]=[], move_ring=True, avoid_by=1):
		"""Try to rotate the ring so that the thread is positioned to not intersect the
		geometry in avoid. If we can't find a way to move the ring to avoid
		intersecting anything, return a list of the segments in avoid that the
		thread intersects. Otherwise return an empty set."""
		avoid = set(avoid)

		#Get the thread path from the anchor to the ring
		thr = self.anchor_to_ring()
		anchor = thr.start_point

		#First check to see if we have intersections at all; if not, the thread
		# doesn't need to move, and we're done. Don't count intersections with the
		# anchor, since we'll want to print over that.
		# non_isecs, isecs = map(set, partition(thr.intersection, avoid))
		b = bucket(avoid, key=lambda seg:
				bool(thr.intersection(seg)))
		isecs, non_isecs, anchored = set(b[True]), set(b[False]), set(b['anchored'])
		non_isecs.update(anchored)
		rprint(f"  Try to avoid {len(avoid)} segments with {len(non_isecs)} not intersecting")

		avoid = non_isecs or isecs

		if len(avoid) == 1:
			avoid = list(avoid)
			seg = avoid[0]
			avoidables = angsort(avoid_visible(
				anchor,
				{p:avoid for p in seg},
				avoid_by), ref=thr)
			rprint(f"Avoiding at {avoidables[0]}")
			self.thread_intersect(avoidables[0], set_new_anchor=False)
			return set()


		vis_points = avoid_visible(anchor, visibility2(anchor, avoid))
		rprint(f"  Got {len(vis_points)} from {len(avoid)} segments")

		if len(vis_points) < 2 and not avoid: raise ValueError("oh noes")
		while len(vis_points) < 2:
			avoid -= isecs
			rprint(f"  Avoid {len(avoid)} segments")
			if not avoid:
				#This means that we don't have at least two visibility points, and that
				# there are no non-intersecting segments to consider. So let's try
				# splitting the segments and trying again.
				isecs, avoid = split_segs(isecs, thr)
				if not avoid: raise ValueError("Can't split, omg")

			#Find segment end points where a line from the anchor point to that end
			# point intersects no other segments.
			visible    = visibility2(anchor, avoid)
			vis_points = avoid_visible(anchor, visible)
			too_close  = visible.keys() - vis_points
			rprint(f"  Found {len(vis_points)} visible points")

			##Find segments that come too close to the thread, remove them from visible
			## and add them to isecs
			#too_close = [p for p in visible if thr.line.distance(p) < avoid_by]
			#isecs.update(sum([visible[p] for p in too_close], []))
			#vis_points = [p for p in visible if p not in too_close]

			rprint('too close:', too_close)
			rprint('vis_points:', vis_points)


		#Find a point halfway between two vis_points, then move
		# the ring so the thread is halfway. Keep checking if the distance
		# between the moved thread and the two points is too small.
		vis_points = angsort(vis_points, ref=thr)
		self.debug_non_isecs = vis_points
		check = [seg for seg in avoid if anchor not in seg]

		rprint(f"Try to avoid from {len(vis_points)} points")
		for a,b in grouper(vis_points, 2, fillvalue=vis_points[0]):
			move_to = a.moved(Vector(a, b) * .5)
			self.thread_intersect(move_to, set_new_anchor=False)
			thr = self.anchor_to_ring()
			if thr.intersects(check): self.ring.angle += 180
			if (md := min(thr.line.distance(a), thr.line.distance(b))) > avoid_by:
				rprint(f"Angle of {self.ring.angle:.2f}° avoids by {md:.2f} mm")
				break
			else:
				rprint(f"Angle of {self.ring.angle}° avoids by {md:.2f} mm")

		if min(thr.line.distance(a), thr.line.distance(b)) < 1:
			rprint(f"[yellow]Warning:[/] Couldn't avoid by min distance of {avoid_by} mm")

		return isecs



	def thread_intersect(self, target, anchor=None, set_new_anchor=True, move_ring=True):
		"""Rotate the ring so that the thread starting at anchor intersects the
		target Point. By default sets the anchor to the intersection. Return the
		rotation value."""
		anchor = anchor or self.anchor.as2d()
		if target.as2d() != anchor.as2d():
			#Form a half line (basically a ray) from the anchor through the target
			hl = HalfLine(anchor, target.as2d())

			#isecs = filter(None, map(hl.intersection, self.ring.geometry.segments))

			isec = intersection(hl, self.ring.geometry)
			if isec is None:
				raise GCodeException(hl, "Anchor->target ray doesn't intersect ring")

			#The intersection is always a Segment; we want the endpoint furthest from
			# the anchor
			try:
				ring_point = sorted(isec[:], key=lambda p: distance(anchor, p),
						reverse=True)[0]
			except NotImplementedError:
				rprint(f'Error: isec is ({type(isec)}): {isec}')
				raise

			#Now we need the angle between center->ring and the x axis
			ring_angle = degrees(atan2(ring_point.y - self.ring.center.y,
																 ring_point.x - self.ring.center.x))

			if move_ring:
				self.ring.set_angle(ring_angle)

		else:
			rprint('thread_intersect with target == anchor, doing nothing')
			ring_angle = self.ring.angle

		if set_new_anchor:
			rprint(f'thread_intersect set new anchor to {target}')
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
		'gc_segs':    {'mode':'lines', 'line': dict(color='green',  width=2)},
		'thread':     {'mode':'lines', 'line': dict(color='yellow', width=1, dash='dot')},
		'old_segs':   {'line': dict(color= 'gray', width=1)},
		'old_thread': {'line_color': 'blue'},
		'old_layer':  {'line': dict(color='gray', dash='dot', width=.5)},
		'all_thread': {'line': dict(color='cyan', dash='dot', width=.5)},
	}

	def __init__(self, steps_obj, name=''):
		store_attr()
		self.printer = steps_obj.printer
		self.layer   = steps_obj.layer
		self.gcsegs  = []
		self.number  = -1


	def __repr__(self):
		return f'<Step {self.number} ({len(self.gcsegs)} segments)>: [light_sea_green italic]{self.name}[/]\n  {self.printer}'


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
		return self


	def __exit__(self, exc_type, value, traceback):
		self.printer = self.printer.freeze_state()
		#Die if there's an exception
		if exc_type is not None:
			print(f'Exception on Step.__exit__: {exc_type}')
			return False


	#def plot(self, prev_layer:TLayer=None, prev_layer_only_outline=True):
	#	print(f'Step {self.number}: {step.name}')
	#	fig = go.Figure()

	#	#Plot the bed
	#	self.printer.bed.plot(fig)

	#	#Plot the outline of the previous layer, if provided
	#	if prev_layer:
	#		prev_layer.plot(fig,
	#				move_colors    = [self.style['old_layer']['line']['color']],
	#				extrude_colors = [self.style['old_layer']['line']['color']],
	#				only_outline   = prev_layer_only_outline,
	#		)

	#	#Print the entire thread path that will be routed this layer
	#	if hasattr(self.printer.layer, 'thread'):
	#		fig.add_trace(go.Scatter(**segs_xy(*self.printer.layer.thread,
	#			mode='lines', **self.style['all_thread'])))

	#	#Plot the thread from the layer starting anchor (or bed anchor if none) to
	#	# the


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
		self.steps.append(Step(self, ' '.join(map(str,messages))))
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
		plot_stepnum = stepnum
		steps        = self.steps
		last_anchor  = steps[0].printer.anchor

		for stepnum,step in enumerate(steps):
			if plot_stepnum is not None and stepnum != plot_stepnum:
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



class Threader:
	def __init__(self, gcode_file:GcodeFile):
		self.gcode_file  = gcode_file
		self.printer     = Printer()
		self.layer_steps = []


	def gcode(self):
		"""Return the gcode for all layers."""
		r = self.gcode_file.preamble.lines.data if self.gcode_file.preamble else []
		for steps_obj in self.layer_steps:
			r.append(GCLine(fake=True, comment=f'==== Start layer {steps_obj.layer.layernum} ===='))
			r.extend(steps_obj.gcode())
		return r


	def route_model(self, thread_list: List[GSegment], start_layer=None, end_layer=None):
		if self.layer_steps: raise ValueError("This Threader has been used already")
		reinit_logging()
		acclog.show()
		for layer in self.gcode_file.layers[start_layer:end_layer]:
			try:
				self._route_layer(thread_list, layer, self.printer.anchor.copy(z=layer.z))
			except:
				acclog.unfold()
				raise


	def route_layer(self, thread_list: List[GSegment], layer, start_anchor=None):
		"""Goal: produce a sequence of "steps" that route the thread through one
		layer. A "step" is a set of operations that diverge from the original
		gcode; for example, printing all of the non-thread-intersecting segments
		would be one "step".
		"""
		reinit_logging()
		acclog.show()
		try:
			self._route_layer(thread_list, layer, start_anchor)
		except:
			acclog.unfold()
			raise


	def _route_layer(self, thread_list: List[GSegment], layer, start_anchor=None):
		self.printer.layer = layer
		self.printer.z     = layer.z

		self.layer_steps.append(Steps(layer=layer, printer=self.printer))
		steps = self.layer_steps[-1]

		thread = deepcopy(thread_list)

		if thread[0].start_point == self.printer.bed.anchor:
			raise ValueError("Don't set the first thread anchor to the bed anchor")

		#Is the first thread anchor above the top of this layer, or is the last thread anchor
		# below it? If so, we can skip most of the processing; we just need to be
		# sure the print head will avoid the thread.
		bot_z = layer.z - layer.layer_height/2
		top_z = layer.z + layer.layer_height/2
		if thread[0].start_point.z > top_z or thread[-1].end_point.z < bot_z:
			#We want to avoid the computational cost of making geometry from the
			# entire layer if we're not doing anything with it, so we'll just make a
			# rectangle of segments based on the layer extents and avoid that. Might
			# not work if the extents are too big.
			(min_x, min_y), (max_x, max_y) = layer.extents()
			ext_rect = [GSegment(a, b) for a,b in (
				((min_x, min_y, layer.z), (min_x, max_y, layer.z)),
				((min_x, max_y, layer.z), (max_x, max_y, layer.z)),
				((max_x, max_y, layer.z), (max_x, min_y, layer.z)),
				((max_x, min_y, layer.z), (min_x, min_y, layer.z)))]
			with steps.new_step('Move thread to avoid layer extents', debug=False):
				self.printer.thread_avoid(ext_rect)
			#Set the Layer's postamble to the entire set of gcode lines so that we
			# correctly generate the output gcode with Steps.gcode()
			layer.postamble = layer.lines
			return steps

		#If we got here, the first thread anchor is inside this layer, so we need
		# to do the actual work

		acclog.add_fold(f'Layer {layer.layernum}', keep_closed=True)

		#If there's no start_anchor, we need to assume it's the Bed anchor
		if start_anchor is None:
			thread.insert(0, GSegment(self.printer.bed.anchor, thread[0].start_point))

		rprint(f'Route {len(thread_list)}-segment thread through layer:\n {layer}',
				[f'\t{i}. {tseg}' for i, tseg in enumerate(thread)])

		#Get the thread segments to work on
		thread = layer.flatten_thread(thread)

		rprint('\nFlattened thread:',
			[f'  {i}. {tseg}' for i, tseg in enumerate(thread)])

		#Collect layer segments that involve extrusion
		extrude_segs = [gcseg for gcseg in layer.geometry.segments if gcseg.is_extrude]

		if not thread:
			rprint('Thread not in layer at all')
			with steps.new_step('Thread not in layer') as s:
				s.add(extrude_segs)
			return steps

		#If there's a start anchor (e.g. from the previous layer), check to see if
		# we need to add a thread segment that goes from that anchor to the start
		# point of the thread on this layer. We do so only if the distance from the
		# start anchor to the thread start point is greater than epsilon. If it's
		# not long enough, just move the first thread point to be the start anchor.
		if start_anchor:
			rprint('+++++ START ANCHOR:', start_anchor)
			start_anchor = start_anchor.copy(z=layer.z)
			layer.start_anchor = start_anchor
			if (sdist := start_anchor.distance(thread[0].start_point.copy(z=layer.z))) > epsilon:
				thread.insert(0, GSegment(start_anchor, thread[0].start_point, z=layer.z))
				rprint(f'Added start anchor seg: {thread[0]}')
			else:
				rprint(f'Start anchor to first thread point only {sdist:.2f} mm, moving thread start point')
				thread[0] = thread[0].copy(start_point=start_anchor, z=layer.z)

		#Snap thread to printed geometry
		snapped_thread = layer.geometry_snap(thread)
		if snapped_thread:
			rprint('Snapped thread:',
					[(f'  {i}. Old: {o}\n     New: {n}' +
						('' if n is None else f' ({o.end_point.distance(n.end_point):.4f} mm)'))
					for i,(o,n) in enumerate(snapped_thread.items())])
			thread = list(filter(None, snapped_thread.values()))
			layer.snapped_thread = snapped_thread

		layer.thread = thread

		rprint(f'\n{len(thread)} thread segments in this layer:',
			[f'  {i}. {tseg} ({tseg.length():>5.2f} mm)' for i, tseg in enumerate(thread)])

		#Done preprocessing thread; now we can start figuring out what to print and how
		rprint('[yellow]————[/] Start [yellow]————[/]', div=True)

		#Find segments that intersect the incoming thread anchor (if there is one)
		# so we can print those separately to fix the anchor in place. This will be
		# the snapped start point of the first thread segment.
		if start_anchor:
			a = thread[0].start_point if thread else start_anchor
			anchorsegs = [seg for seg in layer.geometry.segments if a in seg]
			rprint(f'{len(anchorsegs)} segments intersecting start anchor {a}:',
					anchorsegs, indent=2)
			if anchorsegs:
				with steps.new_step(f"Move thread to avoid {len(anchorsegs)} segments fixing start anchor"):
					isecs = self.printer.thread_avoid(anchorsegs)
					if isecs: raise ValueError("Couldn't avoid anchor segments???")
				with steps.new_step(f"Print {len(anchorsegs)} anchor-fixing segments") as s:
					s.add(anchorsegs)
			else:
				rprint("[yellow]No segments contain the anchor")
			#endpoints = angsort(set(sum([seg[:] for seg in anchorsegs], ())) - {a},
			#		ref=self.printer.anchor_to_ring())
			#if endpoints:
			#	#These can be viewed as a collection of segments starting at the
			#	# anchor, so any two angularly adjacent endpoints will have visibility
			#	# in between them
			#	avoided = False
			#	for e1, e2 in pairwise(endpoints):
			#		if e1.distance(e2) > avoid_epsilon * 2:
			#			avoided = True
			#			move_to = e1.moved(Vector(e1, e2) * .5)
			#			with steps.new_step(f"Move thread to avoid {len(anchorsegs)} segments fixing start anchor"):
			#					self.printer.thread_intersect(move_to, set_new_anchor=False)
			#			break
			#	if not avoided: raise ValueError("Couldn't avoid fixing segments")
			#	with steps.new_step("Print anchor-fixing segments") as s:
			#		s.add(anchorsegs)
			#else:
			#	rprint("[yellow]No segments contain the anchor")

		#Drop thread segments that are too short to worry about
		thread = [tseg for tseg in thread if tseg.length() > epsilon]
		if (t1:=len(thread)) != (t2:=len(layer.thread)):
			rprint(f'Dropped {t2-t1} thread segs due to being shorter than {epsilon}',
					f'now {t1} left')
			if t1 > 0: rprint('\n'.join([f'  {tseg}' for tseg in thread]))

		#Find geometry that will not be intersected by any thread segments
		to_print = unprinted(layer.non_intersecting(thread) if thread else layer.geometry.segments)
		rprint(f'Layer has {len(unprinted(extrude_segs))} unprinted extruding segments,'
				f'with {len(to_print)} not intersecting thread path.')

		while to_print:
			self.printer.debug_non_isecs = []
			with steps.new_step(f"Move thread to avoid {len(to_print)} segments"):
				self.printer.debug_avoid = to_print
				isecs = self.printer.thread_avoid(to_print)
				to_print -= isecs
				rprint(f'{len(isecs)} isecs, {len(to_print)} to print')
			# if isecs:
			# 	with steps.new_step(f"Move thread to avoid {len(to_print)} segments"):
			# 		self.printer.thread_avoid(to_print)
			if to_print:
				with steps.new_step("Print", f'{len(to_print)}/{len(unprinted(extrude_segs))}',
						"segments thread doesn't intersect") as s:
					s.add(to_print)
			to_print = isecs




		# with steps.new_step(f'Move thread to avoid {len(to_print)}/{len(extrude_segs)} segments of non-intersecting geometry'):
		# 	isecs = self.printer.thread_avoid(to_print)
		# self.printer.debug_non_isecs = []

		# if isecs:
		# 	new_print = set(to_print) - set(isecs)
		# 	self.new_print = new_print
		# 	with steps.new_step(f"Can't avoid all; move thread to avoid {len(new_print)} segments"):
		# 		self.isecs2 = self.printer.thread_avoid(new_print)
		# 		if self.isecs2:
		# 			raise ValueError("oh noes")

		# 	with steps.new_step("Print", f'{len(new_print)}/{len(extrude_segs)}',
		# 			"segments thread doesn't intersect") as s:
		# 		s.add(new_print)

		# 	with steps.new_step(f'Move thread to avoid {len(isecs)} remaining segments'):
		# 		self.isecs3 = self.printer.thread_avoid(isecs)
		# 		self.curr_thread = self.printer.anchor_to_ring()
		# 		if self.isecs3:
		# 			raise ValueError("oh noes")
		# 		to_print = isecs
		# 	self.printer.debug_non_isecs = []

		# with steps.new_step(f'Print {len(to_print)} segments of non-intersecting geometry') as s:
		# 	s.add(to_print)

		rprint(f"[red]———[/] Now process {len(thread)} thread segments [red]———[/]")
		self.debug_threads = thread

		#At this point we've printed everything that does not intersect the
		# thread path. Now we need to work with the individual thread segments
		# one by one:
		# 1. Move the ring so the thread crosses the next anchor point
		# 2. Print gcode segments that intersect this part of the thread, but
		#    that don't intersect:
		#    - the anchor->ring trajectory
		#    - the future thread path
		#    except where those intersections are only at the anchor point iself.
		for i,thread_seg in enumerate(thread):
			rprint(f'[yellow]————[/] Thread {i}: {thread_seg} [yellow]————[/]')

			anchor      = thread_seg.end_point
			thread_traj = self.printer.anchor_to_ring()

			with steps.new_step(f'Move thread to overlap anchor at {anchor}') as s:
				self.printer.thread_intersect(anchor)

			#Get non-printed segments that overlap the current thread segment. We
			# want to print these to fix the thread in place.
			to_print = unprinted(layer.intersecting(thread_seg))

			#Find gcode segments that intersect future thread segments and the
			# anchor->ring thread
			avoid = unprinted(layer.intersecting(thread[i+1:] + [thread_traj]))

			#Remove from avoid gcode segments that include the anchor point, but
			# that *don't* include future anchor points
			future_anchors = [seg.end_point for seg in thread[i+1:]]
			keep = {seg for seg in avoid if
					(anchor in seg) and (not any(a in seg for a in future_anchors))}
			avoid -= keep

			#Now remove the remaining segments in avoid from to_print
			to_print -= avoid

			if to_print:
				with steps.new_step(f'Print {len(to_print)} overlapping layers segments') as s:
					s.add(to_print)
			# else:
			# 	raise GCodeException((i, thread), "Can't print anchor!")


		# --- Print what's left
		remaining = [s for s in layer.geometry.segments if not s.printed]
		if remaining:
			with steps.new_step('Move thread to avoid remaining geometry') as s:
				self.printer.thread_avoid(remaining)

			with steps.new_step(f'Print {len(remaining)} remaining geometry lines') as s:
				s.add(remaining)

		rprint('[yellow]Done with thread for this layer[/];',
				len([s for s in layer.geometry.segments if not s.printed]),
				'gcode lines left')
		rprint(f'Printer state: {self.printer}')

		return steps


if __name__ == "__main__":
	import gcode
	import numpy as np
	from Geometry3D import Segment
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
