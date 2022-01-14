import plotly.graph_objects as go
import Geometry3D
from functools import partial
from copy import deepcopy
from fastcore.basics import *
from Geometry3D import Segment, Point, intersection
from math import radians, sin, cos
from pint import UnitRegistry

"""TODO:
	* [ ] layer.intersect(thread)
	* [ ] gcode generator for ring
	* [ ] plot() methods
	* [ ] thread_avoid()
	* [ ] thread_intersect
	* [ ] wrap Geometry3D functions with units; or maybe get rid of units again?
"""

ureg = UnitRegistry(auto_reduce_dimensions=True)
#So we can do U.mm(7) instead of (7*ureg.mm)
class UnitHelper:
	def __getattr__(self, attr):
		return partial(ureg.Quantity, units=attr)
U = UnitHelper()


class Ring:
	#Defaults
	_radius = U.mm(110)
	_angle  = U.radians(0)
	_center = Point(110, 110, 0)

	#Default plotting style
	_style = {
		'ring':      {line: dict(color='white', width=10)},
		'indicator': {line: dict(color='blue',  width= 2)},
	}

	__repr__ = basic_repr('diameter,angle,center')

	def __init__(self, radius:U.mm=_radius, angle:U.radians=_angle,
			center:Point=_center, style:dict=None):
		store_attr(but='style', cast=True)

		self._angle        = angle
		self.initial_angle = angle
		self.geometry      = Circle(self.center, Vector.z_unit_vector(), self.radius, n=50)
		self.x_axis        = Vector(self.center, Point(self.radius, 0, 0))

		self.style = deepcopy(self._style)
		if style is not None:
			for item in style:
				self.style[item].update(style[item])


	@property
	def angle(self):
		return self._angle


	@angle.setter
	def angle(self, new_pos):
		self.set_angle(new_pos)


	@property
	def point(self):
		return self.angle2point(self.angle)


	def set_angle(self, new_angle, direction=None):
		"""Set a new angle for the ring. Optionally provide a preferred movement
		direction as 'CW' or 'CCW'; if None, it will be automatically determined."""
		self.initial_angle = self._angle
		self._angle = new_angle
		self._direction = direction


	def carrier_location(self, offset=0):
		return Point(
			self.center.x + cos(self.angle)*(self.radius+offset),
			self.center.y + sin(self.angle)*(self.radius+offset),
		)


	def angle2point(self, angle):
		"""Return an x,y,z=0 location on the ring based on the given angle, without
		moving the ring. Assumes that the bed's bottom-left corner is (0,0).
		Doesn't take into account a machine that uses bed movement for the y-axis,
		but just add the y value to the return from this function."""
		return Point(
			cos(radians(angle)) * self.radius + self.center.x,
			sin(radians(angle)) * self.radius + self.center.y,
			0
		)


	def gcode(self):
		"""Return the gcode necessary to move the ring from its starting angle
		to its requested one."""
		pass


	def plot(self, fig):
		fig.add_shape(
			name='ring',
			type='circle',
			xref='x', yref='y',
			x1=self.center.x-self.diameter/2,
			y1=self.center.y-self.diameter/2,
			x2=self.center.x+self.diameter/2,
			y2=self.center.y+self.diameter/2,
			**self.style['ring'],
		)
		c1 = self.carrier_location()
		c2 = self.carrier_location(offset=3)
		fig.add_shape(
			name='ring_indicator',
			type='line',
			xref='x', yref='y',
			x1=c1.x, y1=c1.y,
			x2=c2.x, y2=c2.y,
			**self.style['indicator'],
		)



class Bed:
	__repr__ = basic_repr('anchor_location,size')

	def __init__(self, anchor_location=(0,0), size=(220, 220)):
		store_attr()



class State:
	__repr__ = basic_repr('bed,ring')
	
	def __init__(self, bed, ring):
		store_attr()
		self.anchor = Point(bed.anchor_location[0], bed.anchor_location[1], 0)


	def freeze(self):
		return deepcopy(self)


	def thread(self):
		"""Return a Segment representing the current thread, from the anchor point to the ring."""
		#TODO: account for bed location (y axis)
		return Segment(self.anchor, self.ring.point)


	def thread_avoid(self, avoid=[], move_ring=True):
		"""Rotate the ring so that the thread is positioned to not intersect the
		geometry in avoid. Return the rotation value."""
		"""Except in the case that the anchor is still on the bed, the anchor is
			guaranteed to be inside printed material (by definition). We might have
			some cases where for a given layer there are two gcode regions (Cura sets
			this up) and the anchor is in one of them. Probably the easiest thing
			here is just to exhaustively test.
		"""
		#First check to see if we have intersections at all; if not, we're done!
		thr = self.thread()
		if not any(thr.intersection(i) for i in avoid):
			return

		#Next, try to move in increments around the current position to minimize movement time
		# use angle2point()
		for inc in range(10, 190, 10):
			for ang in (self.ring.angle + inc, self.ring.angle - inc):
				thr = Segment(self.anchor, self.ring.angle2point(ang))
				if not any(thr.intersection(i) for i in avoid):
					if move_ring:
						self.ring.set_angle(ang)
					return ang

		return None

	def thread_intersect(self, target, set_new_anchor=True, move_ring=True):
		"""Rotate the ring so that the thread intersects the target Point. By default
		sets the anchor to the intersection. Return the rotation value."""
		#Form a half line (basically a ray) from the anchor through the target
		hl = HalfLine(self.anchor, target)

		#Find intersection with the ring; this returns a Segment starting at the anchor
		ring_point = intersection(hl, self.ring.geometry).end_point

		#Now we need the angle between center->ring and the x axis
		ring_angle = degrees(angle(self.ring.x_axis, Vector(self.ring.center, ring_point)))

		if move_ring:
			self.ring.set_angle(ring_angle)

		if set_new_anchor:
			self.anchor = target

		return ring_angle
		


class Step:
	def __init__(self, state, name=''):
		store_attr()
		self.gcode = []


	def add(self, gcode):
		self.gcode.append(gcode)


	def __enter__(self):
		return self


	def __exit__(self, exc_type, value, traceback):
		if exc_type is not None:
			return False
		#Otherwise store the current state
		self.state = self.state.freeze()


	def plot(self):
		#Plot things in order


class Steps:
	def __init__(self, layer, state):
		store_attr()
		self._steps = []
		self._current_step = None

	@property
	def current(self):
		return self._steps[-1] if self._steps else None

	def new_step(self, name=''):
		self.steps.append(Step(self.state, name))
		return self.current



class Threader:
	def __init__(self, gcode):
		store_attr()
		self.state = State(Bed(), Ring())

	
	def route_model(self, thread):
		for layer in self.gcode.layers:
			self.layer_steps.append(self.route_layer(thread, layer))
		return self.layer_steps


	def route_layer(self, thread, layer):
		"""Goal: produce a sequence of "steps" that route the thread through one
		layer. A "step" is a set of operations that diverge from the original
		gcode; for example, printing all of the non-thread-intersecting segments
		would be one "step".
		"""
		"""
		Gcode operations; each is one step:
		1. Move the thread out of the way
		2. Print all gcode segments that don't intersect the thread in this layer
		3. Repeat for each segment of thread, starting with where the thread enters
		 	 the layer:
			A. Move the thread to overlap its end point
			B. Print over all intersecting gcode segments
		"""
		intersections = layer.intersect(thread)

		steps = Steps(layer=layer, state=self.state)

		with steps.new_step('Move thread out of the way') as s:
			#rotate ring to avoid segments it shouldn't intersect
			#context manager should store state when this step context finishes,
			# so we should just be able to rotate the ring
			#To rotate ring, we need to know: current anchor location and things thread
			# shouldn't intersect
			self.state.thread_avoid(intersections.non_intersecting)

		with steps.new_step('Print non-intersecting layer segments') as s:
			s.add(intersections.non_intersecting)

		for thread_seg in thread:
			seg_intersections = intersections.intersecting(thread_seg)

			with steps.new_step('Move thread to overlap next anchor') as s:
				self.state.thread_intersect(next(intersections.anchors))

			with steps.new_step('Print overlapping layers segments')	as s:
				s.add(seg_intersections)

		return steps
