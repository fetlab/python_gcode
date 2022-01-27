import plotly, plotly.graph_objects as go
from copy import deepcopy
from Geometry3D import Circle, Vector, Segment, Point, Plane, intersection, distance
from math import radians, sin, cos, degrees
from typing import List
from geometry_helpers import GPoint, GSegment, Geometry, Planes, HalfLine, segs_xy
from fastcore.basics import basic_repr, store_attr
from rich import print
from math import atan2
from parsers.cura4 import Cura4Layer
from time import time

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
	* [ ] Take care of moving to start point of a Segment after an order change
"""

def style_update(old_style, new_style):
	style = deepcopy(old_style)
	if new_style is not None:
		for item in new_style:
			style[item].update(new_style[item])
	return style


class GCodeException(Exception):
	def __init__(self, obj, message):
		self.obj = obj
		self.message = message



class TLayer(Cura4Layer):
	def __init__(self, *args, layer_height=0.4, **kwargs):
		super().__init__(*args, **kwargs)
		self.geometry = None
		self.layer_height = layer_height
		self._isecs = {}


	def plot(self, fig,
			move_colors=plotly.colors.qualitative.Set2,
			extrude_colors=plotly.colors.qualitative.Dark2):
		self.add_geometry()
		colors = zip(extrude_colors, move_colors)

		for name, part in self.parts.items():
			colorD, colorL = next(colors)

			Esegs = {'x': [], 'y': []}
			Msegs = {'x': [], 'y': []}
			for line in part:
				try:
					seg = line.segment
				except AttributeError:
					#print(line)
					continue

				segs = Esegs if line.is_xyextrude() else Msegs
				segs['x'].extend([seg.start_point.x, seg.end_point.x, None])
				segs['y'].extend([seg.start_point.y, seg.end_point.y, None])

			if Esegs['x']:
				fig.add_trace(go.Scatter(**Esegs, mode='lines', name=repr(name).lower(),
					line=dict(color=colorD)))
			if Msegs['x']:
				fig.add_trace(go.Scatter(**Msegs, mode='lines', name=repr(name).lower(),
					line=dict(color=colorL, dash='dot')))


	def add_geometry(self):
		"""Add geometry to this Layer based on the list of lines, using
		GSegment."""
		if self.geometry or not self.has_moves:
			return
		self.geometry = Geometry(segments=[], planes=None, outline=None)
		#TODO: add outline of layer using the layer.part with the largest extents;
		# need to be able to test intersections, but it's likely a concave polygone
		# with holes so complicated.

		last = None
		for line in self.lines:
			if last is not None:   #wait until we have two moves in the layer
				if line.is_xymove():
					seg = GSegment(last, line, z=self.z)
					try:
						line.segment = seg
						self.geometry.segments.append(seg)
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
		"""Return a list of the thread segments which are inside this layer. Note
		that it's not guaranteed that they actually interact with the geometry, but
		that the ends of the segment are not both above or below the layer."""
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

			#See if the thread segment enters and/or exits the layer
			isecs['enter'] = [tseg.intersection(bot)]
			isecs['exit']  = [tseg.intersection(top)]

			start = time()
			#And find the gCode lines the thread segment intersects with
			for gcseg in self.geometry.segments:
				gcseg.printed = False
				inter = gcseg.intersection2d(tseg)
				if inter:
					isecs['isec_segs'  ].append(gcseg)
					isecs['isec_points'].append(inter)
				else:
					isecs['nsec_segs'].append(gcseg)

			print(f'Intersecting took {time()-start:2.4}s')

			isecs['in_layer'] = bool(isecs['isec_segs'])


class Ring:
	#Defaults
	_radius = 110  #mm
	_angle  = 0    #radians
	_center = Point(110, 110, 0) #mm

	#Default plotting style
	_style = {
		'ring':      {'line': dict(color='white', width=10), 'opacity':.25},
		'indicator': {'line': dict(color='blue',  width= 4)},
	}

	__repr__ = basic_repr('_radius,_angle,_center')

	def __init__(self, radius=_radius, angle:radians=_angle, center=_center, style=None):
		store_attr(but='style')

		self._angle        = angle
		self.initial_angle = angle
		self.geometry      = Circle(self.center, Vector.z_unit_vector(), self.radius, n=50)
		self.x_axis        = Vector(self.center,
																Point(self.center.x + self.radius,
																			self.center.y, self.center.z))

		self.style = style_update(self._style, style)


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
			0
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


	def plot(self, fig, style=None):
		style = style_update(self.style, style)
		"""
		fig.add_shape(
			name='ring',
			type='circle',
			xref='x', yref='y',
			x0=self.center.x-self.radius,
			y0=self.center.y-self.radius,
			x1=self.center.x+self.radius,
			y1=self.center.y+self.radius,
			**style['ring'],
		)
		"""
		fig.add_trace(go.Scatter(**segs_xy(*list(self.geometry.segments()), **style['ring'])))
		ringwidth = style['ring']['line']['width']/2
		c1 = self.carrier_location(offset=-ringwidth/2)
		c2 = self.carrier_location(offset=ringwidth/2)
		fig.add_shape(
			name='ring_indicator',
			type='line',
			xref='x', yref='y',
			x0=c1.x, y0=c1.y,
			x1=c2.x, y1=c2.y,
			**style['indicator'],
		)



class Bed:
	__repr__ = basic_repr('anchor')
	#Default plotting style
	_style = {
			'bed': {'line': dict(color='rgba(0,0,0,0)'), 'fillcolor': 'LightSkyBlue',
				'opacity':.25},
	}

	def __init__(self, anchor=(0,0), size=(220, 220), style=None):
		self.anchor = GPoint(*anchor)
		self.size   = size
		self.style = style_update(self._style, style)


	def plot(self, fig, style=None):
		style = style_update(self.style, style)
		fig.add_shape(
			name='bed',
			type='rect',
			xref='x', yref='y',
			x0=0, y0=0,
			x1=self.size[0], y1=self.size[1],
			**style['bed'],
		)



class State:
	_style = {
		'thread': {'mode':'lines', 'line': dict(color='white', width=1, dash='dot')},
		'anchor': {'mode':'markers', 'marker': dict(color='red', symbol='x', size=2)},
	}

	def __init__(self, bed, ring, style=None):
		store_attr(but='style')
		self.style = style_update(self._style, style)
		self.anchor = Point(bed.anchor[0], bed.anchor[1], 0)


	def __repr__(self):
		return f'State(Bed, {self.ring})'


	def freeze(self):
		"""Return a copy of this State object, capturing the state."""
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
		if distance(self.anchor, self.ring.center) > self.ring.radius:
			ring_point = intersection(hl, self.ring.geometry).end_point
		else:
			ring_point = intersection(hl, self.ring.geometry).start_point

		self.hl_parts = deepcopy([self.anchor, target])
		self.ring_point = ring_point

		#Now we need the angle between center->ring and the x axis
		ring_angle = atan2(ring_point.y - self.ring.center.y, ring_point.x - self.ring.center.x)

		if move_ring:
			self.ring.set_angle(ring_angle)

		if set_new_anchor:
			self.anchor = target

		return ring_angle


	def plot_thread_to_ring(self, fig, style=None):
		#Plot a thread from the current anchor to the carrier
		style = style_update(self.style, style)
		fig.add_trace(go.Scatter(**segs_xy(self.thread(), **style['thread'])))


	def plot_anchor(self, fig, style=None):
		style = style_update(self.style, style)
		fig.add_trace(go.Scatter(x=[self.anchor.x], y=[self.anchor.y], **style['anchor']))



class Step:
	#Default plotting style
	_style = {
		'gc_segs': {'mode':'lines', 'line': dict(color='green',  width=1)},
		'thread':  {'mode':'lines', 'line': dict(color='yellow', width=1, dash='dot')},
	}

	def __init__(self, state, name='', style=None):
		store_attr(but='style')
		self.gcsegs = []
		self.style  = style_update(self._style, style)


	def __repr__(self):
		return f'<Step ({len(self.gcsegs)} segments)>: [light_sea_green italic]{self.name}[/]\n  {self.state}'


	def add(self, gcsegs):
		for seg in gcsegs:
			if not seg.printed:
				self.gcsegs.append(seg)
				seg.printed = True


	def __enter__(self):
		print(f'Start: [light_sea_green italic]{self.name}')
		return self


	def __exit__(self, exc_type, value, traceback):
		if exc_type is not None:
			return False
		#Otherwise store the current state
		self.state = self.state.freeze()


	def plot_gcsegments(self, fig, style=None):
		#Plot gcode segments. The 'None' makes a break in a line so we can use
		# just one add_trace() call.
		style = style_update(self.style, style)
		if len(self.gcsegs) < 10:
			style['gc_segs']['line']['width'] = 3
		segs = {'x': [], 'y': []}
		for seg in self.gcsegs:
			segs['x'].extend([seg.start_point.x, seg.end_point.x, None])
			segs['y'].extend([seg.start_point.y, seg.end_point.y, None])
		fig.add_trace(go.Scatter(**segs, name='gc_segs', **style['gc_segs']))


	def plot_thread(self, fig, start:Point, style=None):
		#Plot a thread segment, starting at 'start'
		style = style_update(self.style, style)
		fig.add_trace(go.Scatter(
			x=[start.x, self.state.anchor.x],
			y=[start.y, self.state.anchor.y],
			**style['thread'],
		))



#TODO: Change new_step() to return Steps class with _current_step set to the
# new Step object. Then raise something like NoChangesException in different
# steps so that we don't add an empty Step to steps[].
class Steps:
	def __init__(self, layer, state):
		store_attr()
		self.steps = []
		self._current_step = None


	def __repr__(self):
		return '\n'.join(map(repr, self.steps))


	@property
	def current(self):
		return self.steps[-1] if self.steps else None


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
		print(f'Route {len(thread)}-segment thread through layer:\n  {layer}')
		steps = Steps(layer=layer, state=self.state)

		if not layer.in_layer(thread):
			print('Thread not in layer at all')
		else:
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
					print(f'  {self.state.anchor} [green]→ anchor:[/] {anchors[0]}')
					self.state.thread_intersect(anchors[0])
					print(f'  [green]→ new anchor:[/] {self.state.anchor}')

			with steps.new_step('Print overlapping layers segments')	as s:
				s.add(layer.intersecting([thread_seg]))

		print('[yellow]Done with thread for this layer[/];',
				len([s for s in layer.geometry.segments if not s.printed]),
				'gcode lines left')

		return steps.steps


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
	g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode',
			layer_class=TLayer)
	t = Threader(g)
	steps = t.route_layer(thread_geom, g.layers[3])
	#print(steps)
