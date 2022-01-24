import gclayer
from copy import deepcopy
from Geometry3D import Circle, Vector, Segment, Point, Plane, intersection, distance, angle
from math import radians, sin, cos, degrees
from typing import List
from geometry_helpers import GSegment, Geometry, Planes, HalfLine
from fastcore.basics import basic_repr, store_attr
from rich import print
#from loguru import logger

"""TODO:
	* [X] layer.intersect(thread)
	* [ ] gcode generator for ring
	* [ ] plot() methods
	* [X] thread_avoid()
	* [X] thread_intersect
	* [ ] wrap Geometry3D functions with units; or maybe get rid of units again?
	* [X] think about how to represent a layer as a set of time-ordered segments
				that we can intersect but also as something that has non-geometry components
				* Also note the challenge of needing to have gCode be Segments but keeping the
					gcode info such as move speed and extrusion amount
					* But a Segment represents two lines of gcode as vertices....
	* [X] Order isecs['isec_points'] in the Layer.anchors() method
"""

class GCodeException(Exception):
	def __init__(self, obj, message):
		self.obj = obj
		self.message = message



class TLayer(gclayer.Layer):
	def __init__(self, *args, layer_height=0.4, **kwargs):
		super().__init__(*args, **kwargs)
		self.geometry = None
		self.layer_height = layer_height
		self._isecs = {}


	def add_geometry(self):
		"""Add geometry to this Layer based on the list of lines, using
		GSegment."""
		if self.geometry or not self.has_moves:
			return
		self.geometry = Geometry(segments=[], planes=None)

		last = None
		for line in self.lines:
			if last is not None:   #wait until we have two moves in the layer
				if line.is_xymove():
					try:
						self.geometry.segments.append(GSegment(last, line, z=self.z))
					except (AttributeError, TypeError) as e:
						raise GCodeException((self,last),
								f'GSegment {line.lineno}: {line}') from e
			if line.is_xymove():
				last = line

		(min_x, min_y), (max_x, max_y) = self.extents()
		mid_x = min_x + .5 * (max_x - min_x)
		z = self.z

		plane_points = [(min_x, min_y), (mid_x, max_y), (max_x, max_y)]
		bot_z = z - self.layer_height/2
		top_z = z + self.layer_height/2
		bottom = Plane(*[Point(p[0], p[1], bot_z) for p in plane_points])
		top    = Plane(*[Point(p[0], p[1], top_z) for p in plane_points])
		bottom.z = bot_z
		top.z    = top_z
		self.geometry.planes = Planes(bottom=bottom, top=top)


	def in_layer(self, thread: List[Segment]) -> List[Segment]:
		"""Return a list of the thread segments which are inside this layer."""
		self.intersect(thread)
		return [tseg for tseg in thread if self._isecs[tseg]['in_layer']]

	def non_intersecting(self, thread: List[Segment]) -> List[GSegment]:
		"""Return a list of GSegments which the given thread segments do not
		intersect."""
		self.intersect(thread)
		return sum([self._isecs[tseg]['nsec_segs'] for tseg in thread], [])


	def intersecting(self, thread: List[Segment]) -> List[GSegment]:
		"""Return a list of GSegments which the given thread segments intersect."""
		self.intersect(thread)
		return sum([self._isecs[tseg]['isec_segs'] for tseg in thread], [])


	def anchors(self, tseg: Segment) -> List[Point]:
		"""Return a list of "anchor points" - Points at which the given thread
		segment intersects the layer geometry, ordered by distance to the
		end point of the thread segment (with the assumption that this the
		"true" anchor point, as the last location the thread will be stuck down."""
		self.intersect([tseg])
		anchors = sum([self._isecs[tseg][k] for k in ('enter', 'isec_points', 'exit')], [])
		return sorted(anchors, key=lambda p:distance(tseg.end_point.as2d(), p.as2d()))



	def intersect(self, thread: List[Segment]):
		"""Call this in each of the intersection methods above to cache any
		 intersections for each thread segment."""
		self.add_geometry()

		bot = self.geometry.planes.bottom
		top = self.geometry.planes.top

		for tseg in thread:
			#Caching
			if tseg in self._isecs:
				continue
			self._isecs[tseg] = isecs = {
					'in_layer': False,                  # Is the thread in this layer at all?
					'nsec_segs': [],                    # Non-intersecting gcode segments
					'isec_segs': [], 'isec_points': [], # Intersecting gcode segments and locations
					'enter':     [],  'exit': [],       # Thread segment entry and/or exit locations
			}

			#Is the thread segment entirely below or above the layer? If so, skip it.
			if((tseg.start_point.z <  bot.z and tseg.end_point.z <  bot.z) or
				 (tseg.start_point.z >= top.z and tseg.end_point.z >= top.z)):
				continue

			isecs['in_layer'] = True

			#See if the thread segment enters and/or exits the layer
			isecs['enter'] = [tseg.intersection(bot)]
			isecs['exit']  = [tseg.intersection(top)]

			#And find the gCode lines the thread segment intersects with
			for gcseg in self.geometry.segments:
				gcseg.printed = False
				inter = gcseg.intersection2d(tseg)
				if inter:
					isecs['isec_segs'  ].append(gcseg)
					isecs['isec_points'].append(inter)
				else:
					isecs['nsec_segs'].append(gcseg)



class Ring:
	#Defaults
	_radius = 110  #mm
	_angle  = 0    #radians
	_center = Point(110, 110, 0) #mm

	#Default plotting style
	_style = {
		'ring':      {'line': dict(color='white', width=10)},
		'indicator': {'line': dict(color='blue',  width= 2)},
	}

	__repr__ = basic_repr('_radius,_angle,_center')

	def __init__(self, radius=_radius, angle:radians=_angle, center=_center, style=None):
		store_attr(but='style')

		self._angle        = angle
		self.initial_angle = angle
		self.geometry      = Circle(self.center, Vector.z_unit_vector(), self.radius, n=50)
		self.x_axis        = Vector(self.center, Point(self.radius, 0, 0))

		self.style = deepcopy(self._style)
		if style is not None:
			for item in style:
				self.style[item].update(style[item])


	def __repr__(self):
		return f'Ring({degrees(self._angle):.2f}°)'


	@property
	def angle(self):
		return self._angle


	@angle.setter
	def angle(self, new_pos:radians):
		self.set_angle(new_pos)


	@property
	def point(self):
		return self.angle2point(self.angle)


	def set_angle(self, new_angle:radians, direction=None):
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


	def angle2point(self, angle:radians):
		"""Return an x,y,z=0 location on the ring based on the given angle, without
		moving the ring. Assumes that the bed's bottom-left corner is (0,0).
		Doesn't take into account a machine that uses bed movement for the y-axis,
		but just add the y value to the return from this function."""
		return Point(
			cos(angle) * self.radius + self.center.x,
			sin(angle) * self.radius + self.center.y,
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
	__repr__ = basic_repr('anchor_location')

	def __init__(self, anchor_location=(0,0), size=(220, 220)):
		store_attr()



class State:
	def __init__(self, bed, ring):
		store_attr()
		self.anchor = Point(bed.anchor_location[0], bed.anchor_location[1], 0)


	def __repr__(self):
		return f'State(Bed, {self.ring})'


	def freeze(self):
		return deepcopy(self)


	def thread(self) -> Segment:
		"""Return a Segment representing the current thread, from the anchor point
		to the ring."""
		#TODO: account for bed location (y axis)
		return Segment(self.anchor, self.ring.point)


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
		hl = HalfLine(self.anchor.as2d(), target.as2d())

		#Find intersection with the ring; this returns a Segment starting at the anchor
		ring_point = intersection(hl, self.ring.geometry).end_point

		#Now we need the angle between center->ring and the x axis
		ring_angle = angle(self.ring.x_axis, Vector(self.ring.center, ring_point))

		if move_ring:
			self.ring.set_angle(ring_angle)

		if set_new_anchor:
			self.anchor = target

		return ring_angle



class Step:
	def __init__(self, state, name=''):
		store_attr()
		self.gcode = []


	def __repr__(self):
		return f'<Step ({len(self.gcode)} lines)>: [light_sea_green italic]{self.name}[/]\n  {self.state}'


	def add(self, gclines):
		for l in gclines:
			if not l.printed:
				self.gcode.append(l)
				l.printed = True


	def __enter__(self):
		return self


	def __exit__(self, exc_type, value, traceback):
		if exc_type is not None:
			return False
		#Otherwise store the current state
		self.state = self.state.freeze()
		print(repr(self))


	def plot(self):
		#Plot things in order
		raise NotImplementedError


class Steps:
	def __init__(self, layer, state):
		store_attr()
		self._steps = []
		self._current_step = None


	def __repr__(self):
		return '\n'.join(map(repr, self._steps))


	@property
	def current(self):
		return self._steps[-1] if self._steps else None

	def new_step(self, name=''):
		self._steps.append(Step(self.state, name))
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
		print(f'Route {len(thread)}-segment thread through layer:\n  {layer}')
		steps = Steps(layer=layer, state=self.state)

		layer.intersect(thread)

		with steps.new_step('Move thread out of the way') as s:
			#rotate ring to avoid segments it shouldn't intersect
			#context manager should store state when this step context finishes,
			# so we should just be able to rotate the ring
			#To rotate ring, we need to know: current anchor location and things thread
			# shouldn't intersect
			self.state.thread_avoid(layer.non_intersecting(thread))

		with steps.new_step('Print non-intersecting layer segments') as s:
			s.add(layer.non_intersecting(thread))

		for thread_seg in layer.in_layer(thread):
			anchors = layer.anchors(thread_seg)
			if anchors:
				with steps.new_step('Move thread to overlap last anchor') as s:
					self.state.thread_intersect(anchors[0])

			with steps.new_step('Print overlapping layers segments')	as s:
				s.add(layer.intersecting([thread_seg]))

		print('[yellow]Done with thread for this layer[/];',
				len([s for s in layer.geometry.segments if not s.printed]),
				'gcode lines left')

		return steps


if __name__ == "__main__":
	import gcode
	import numpy as np
	from Geometry3D import Segment, Point
	from danutil import unpickle
	tpath = np.array(unpickle('/Users/dan/r/thread_printer/stl/test1/thread_from_fusion.pickle')) * 10
	thread_transform = [131.164, 110.421, 0]
	tpath += [thread_transform, thread_transform]
	thread_geom = tuple([Segment(Point(*s), Point(*e)) for s,e in tpath])
	g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode',
			layer_class=TLayer)
	t = Threader(g)
	steps = t.route_layer(thread_geom, g.layers[43])
	#print(steps)
