from copy import deepcopy
from typing import List, Collection
from itertools import groupby
from math import degrees, atan2

import plotly.graph_objects as go
from plot_helpers import segs_xy, update_figure

from util import attrhelper, Saver, GCodeException
from geometry import GPoint, GSegment, GHalfLine
from gcline import GCLine
from ring import Ring
from bed import Bed
from logger import rprint
from geometry_helpers import visibility4
from geometry.utils import angsort


class Printer:
	"""Maintains the state of the printer/ring system. Holds references to the
	Ring and Bed objects.
	"""
	style = {
		'thread': {'mode':'lines', 'line': dict(color='white', width=1, dash='dot')},
		'anchor': {'mode':'markers', 'marker': dict(color='red', symbol='x', size=4)},
	}

	def __init__(self, effective_bed_size, ring_center, ring_radius, z=0):
		self._x, self._y, self._z = 0, 0, z
		self.bed  = Bed(size=effective_bed_size)
		self.ring = Ring(radius=ring_radius, center=GPoint(ring_center[0], ring_center[1], z))

		self.anchor = GPoint(self.bed.anchor[0], self.bed.anchor[1], z)

		#Default states
		self.extruder_no    = GCLine(code='T0',  args={}, comment='Switch to main extruder', fake=True)
		self.extrusion_mode = GCLine(code='M82', args={}, comment='Set relative extrusion mode', fake=True)

		self.thread_seg = None

		self.debug_non_isecs = []


	#Create attributes which call Printer.attr_changed on change
	x = property(**attrhelper('_x'))
	y = property(**attrhelper('_y'))
	z = property(**attrhelper('_z'))

	@property
	def xy(self): return self.x, self.y


	def __repr__(self):
		return f'Printer(⚓︎{self.anchor}, ⌾ {self.ring._angle:.2f}°)'


	def attr_changed(self, attr, old_value, new_value):
		if attr[1] in 'xy':
			setattr(self.ring, attr[1], new_value)
			#Move the ring to keep the thread intersecting the anchor
			self.thread_intersect(self.anchor, set_new_anchor=False, move_ring=True)


	def freeze_state(self):
		"""Return a copy of this Printer object, capturing the state."""
		return deepcopy(self)


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


	def anchor_to_ring(self) -> GSegment:
		"""Return a Segment representing the current thread, from the anchor point
		to the ring."""
		return GSegment(self.anchor, self.ring.point, z=self.z)


	def avoid_and_print(self, steps, avoid: Collection[GSegment]=None, extra_message='', avoid_by=1):
		"""Loop to print everything in avoid without thread intersections."""
		avoid = set(avoid or [])
		repeats = 0
		while avoid:
			repeats += 1
			if repeats > 5: raise ValueError("Too many repeats")
			self.debug_non_isecs = []
			with steps.new_step(f"Move thread to avoid {len(avoid)} segments" + extra_message) as s:
				self.debug_avoid = avoid.copy()
				isecs = self.thread_avoid(avoid)
				#if avoid == isecs: s.valid = False
				rprint(f"{len(isecs)} intersections")
				avoid -= isecs
			if avoid:
				with steps.new_step(f"Print {len(avoid)} segments thread doesn't intersect" + extra_message) as s:
					s.add(avoid)
				if not isecs: break
			avoid = isecs
		self.debug_non_isecs = []


	def thread_avoid(self, avoid: Collection[GSegment], move_ring=True, avoid_by=1):
		if not avoid: raise ValueError("Need some Segments in avoid")
		avoid = set(avoid)

		thr = self.anchor_to_ring()
		anchor = thr.start_point

		vis = visibility4(anchor, avoid, avoid_by)

		#Get all of the visibility points with N intersections, where N is the
		# smallest number of intersections
		n_isecs, vis_points = next(groupby(vis, key=lambda k:len(vis[k])))

		#Then sort by distance from the thread
		vis_points = angsort(vis_points, ref=thr)

		#Now move the thread to the closest one
		self.thread_intersect(vis_points[0], set_new_anchor=False)

		#Return the set of segments that we intersected
		return vis[vis_points[0]]



	def thread_intersect(self, target, anchor=None, set_new_anchor=True, move_ring=True):
		"""Rotate the ring so that the thread starting at anchor intersects the
		target Point. By default sets the anchor to the intersection. Return the
		rotation value."""
		anchor = anchor or self.anchor.as2d()
		if target.as2d() != anchor.as2d():
			#Form a half line (basically a ray) from the anchor through the target
			hl = GHalfLine(anchor, target.as2d())

			#isecs = filter(None, map(hl.intersection, self.ring.geometry.segments))

			isec = hl.intersection(self.ring.geometry)
			if isec is None:
				raise GCodeException(hl, "Anchor->target ray doesn't intersect ring")

			#The intersection is always a Segment; we want the endpoint furthest from
			# the anchor
			try:
				ring_point = sorted(isec[:], key=lambda p: anchor.distance(p),
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
