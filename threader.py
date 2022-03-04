import plotly, plotly.graph_objects as go
from copy import deepcopy
from Geometry3D import Circle, Vector, Segment, Point, Plane, intersection, distance
from math import radians, sin, cos, degrees
from typing import List
from geometry_helpers import GPoint, GSegment, Geometry, Planes, HalfLine,
														 segs_xy, seg_combine, GCLine, gcode2segments
from fastcore.basics import store_attr
from math import atan2
from parsers.cura4 import Cura4Layer
from itertools import cycle

from rich.console import Console
print = Console(style="on #272727").print
"""
Usage notes:
	* The thread should be anchored on the bed such that it doesn't intersect the
		model on the way to its first model-anchor point.
"""

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



class TLayer(Cura4Layer):
	"""A gcode layer that has thread in it."""
	def __init__(self, *args, layer_height=0.4, **kwargs):
		super().__init__(*args, **kwargs)
		self.geometry     = None
		self.layer_height = layer_height
		self.model_isecs  = {}
		self.in_out       = []
		self.preamble     = []
		self.postamble    = []


	def plot(self, fig,
			move_colors:List=plotly.colors.qualitative.Set2,
			extrude_colors:List=plotly.colors.qualitative.Dark2,
			plot3d=False, only_outline=True):
		"""Plot the geometry making up this layer. Set only_outline to True to
		print only the outline of the gcode in the layer .
		"""
		self.add_geometry()
		colors = cycle(zip(extrude_colors, move_colors))

		for gcline, part in self.parts.items():
			if only_outline and 'wall-outer' not in gcline.line.lower():
				continue
			colorD, colorL = next(colors)

			Esegs = {'x': [], 'y': [], 'z': []}
			Msegs = {'x': [], 'y': [], 'z': []}
			for line in part:
				try:
					seg = line.segment
				except AttributeError:
					#print(line)
					continue

				segs = Esegs if line.is_xyextrude() else Msegs
				segs['x'].extend([seg.start_point.x, seg.end_point.x, None])
				segs['y'].extend([seg.start_point.y, seg.end_point.y, None])
				segs['z'].extend([seg.start_point.z, seg.end_point.z, None])

			if plot3d:
				scatter = go.Scatter3d
				lineprops = {'width': 2}
				plotprops = {'opacity': 1}
			else:
				scatter = go.Scatter
				lineprops = {}
				plotprops = {'opacity': .5}
				if 'z' in Esegs: Esegs.pop('z')
				if 'z' in Msegs: Msegs.pop('z')


			if Esegs['x']:
				fig.add_trace(scatter(**Esegs, mode='lines',
					name='Ex'+(repr(gcline).lower()),
					line=dict(color=colorD, **lineprops), **plotprops))
			if Msegs['x']:
				fig.add_trace(scatter(**Msegs, mode='lines',
					name='Mx'+(repr(gcline).lower()),
					line=dict(color=colorL, dash='dot', **lineprops), **plotprops))


	def add_geometry(self):
		"""Add geometry to this Layer based on the list of gcode lines:
			- segments: a list of GSegments for each pair of extrusion lines
			- planes:   planes representing the top and bottom boundaries of the
								  layer, based on the layer height
			- outline:  a list of GSegments representing the outline of the layer,
									denoted by sections in Cura-generated gcode starting with
									";TYPE:WALL-OUTER"
		"""
		if self.geometry or not self.has_moves:
			return

		self.geometry = Geometry(segments=[], planes=None, outline=[])

		#Make segments from GCLines
		self.preamble, self.geometry.segments, self.postamble = gcode2segments(self.lines)

		#Construct top/bottom planes for intersections
		(min_x, min_y), (max_x, max_y) = self.extents()
		mid_x = min_x + .5 * (max_x - min_x)
		z = self.z

		plane_points = [(min_x, min_y), (mid_x, max_y), (max_x, max_y)]
		bot_z        = z - self.layer_height/2
		top_z        = z + self.layer_height/2
		bottom       = Plane(*[Point(p[0], p[1], bot_z) for p in plane_points])
		top          = Plane(*[Point(p[0], p[1], top_z) for p in plane_points])
		bottom.z     = bot_z
		top.z        = top_z

		self.geometry.planes = Planes(bottom=bottom, top=top)

		#Find the outline by using Cura comments for "wall-outer"
		for part, lines in self.parts.items():
			if 'type:wall-outer' in (lines[0].comment or '').lower():
				self.geometry.outline.extend(
						[line.segment for line in lines if line.is_xyextrude()])


	def flatten_thread(self, thread: List[Segment]) -> List[GSegment]:
		"""Return the input thread "flattened" to have the same z-height as the
		layer, clipped to the top/bottom layer planes, and with resulting segments
		that are on the same line combined."""
		self.add_geometry()

		top = self.geometry.planes.top
		bot = self.geometry.planes.bottom
		segs = []

		for i,tseg in enumerate(thread):
			#Is the thread segment entirely below or above the layer? If so, skip it.
			if((tseg.start_point.z <  bot.z and tseg.end_point.z <  bot.z) or
				 (tseg.start_point.z >= top.z and tseg.end_point.z >= top.z)):
				print(f'Thread segment {tseg} endpoints not in layer')
				continue

			#Clip segments to top/bottom of layer (note "walrus" operator := )
			if s := tseg.intersection(bot): self.in_out.append(s)
			if e := tseg.intersection(top): self.in_out.append(e)
			segs.append(GSegment(s or tseg.start_point, e or tseg.end_point))
			if s or e:
				print(f'Crop {tseg} to\n'
						  f'     {segs[-1]}')

			#Flatten segment to the layer's z-height
			segs[-1].set_z(self.z)

		#Combine collinear segments
		segs = seg_combine(segs)

		#Cache intersections
		for seg in segs:
			self.intersect_model(seg)

		return segs


	def non_intersecting(self, thread: List[Segment]) -> List[GSegment]:
		"""Return a list of GSegments which the given thread segments do not
		intersect."""
		#First find all *intersecting* GSegments
		intersecting = set.union(*[set(self.model_isecs[tseg]['isec_segs']) for tseg in thread])

		#And all non-intersecting GSegments
		non_intersecting = set.union(*[set(self.model_isecs[tseg]['nsec_segs']) for tseg in thread])

		#And return the difference
		return non_intersecting - intersecting


	def intersecting(self, tseg: GSegment) -> List[GSegment]:
		"""Return a list of GSegments which the given thread segment intersects."""
		return self.model_isecs[tseg]['isec_segs']


	def anchors(self, tseg: Segment) -> List[Point]:
		"""Return a list of "anchor points" - Points at which the given thread
		segment intersects the layer geometry, ordered by distance to the
		end point of the thread segment (with the assumption that this the
		"true" anchor point, as the last location the thread will be stuck down."""
		anchors = self.model_isecs[tseg]['isec_points']
		entry   = tseg.start_point
		exit    = tseg.end_point

		print(f'anchors with thread segment: {tseg}')
		print(f'isec anchors: {anchors}')
		if entry in self.in_out and entry.inside(self.geometry.outline):
			anchors.append(entry)
			print(f'Entry anchor: {entry}')
		if exit in self.in_out and exit.inside(self.geometry.outline):
			anchors.append(exit)
			print(f'Exit anchor: {exit}')

		return sorted(anchors, key=lambda p:distance(tseg.end_point, p))


	def intersect_model(self, tseg: GSegment):
		"""Given a thread segment, return all of the intersections with the model's
		printed lines of gcode. Returns
			nsec_segs, isec_segs, isec_points
		where
			nsec_segs is non-intersecting GCLines
			isec_segs is intersecting GCLines
			isec_points is a list of GPoints for the intersections
		"""
		self.add_geometry()

		#Caching
		if tseg in self.model_isecs:
			return self.model_isecs[tseg]

		isecs = {
			'nsec_segs': [],                      # Non-intersecting gcode segments
			'isec_segs': [],   'isec_points': [], # Intersecting gcode segments and locations
		}

		for gcseg in self.geometry.segments:
			if not hasattr(gcseg, 'printed'):
				gcseg.printed = False
			inter = gcseg.intersection(tseg)
			if inter:
				isecs['isec_segs'  ].append(gcseg)
				isecs['isec_points'].append(inter)
			else:
				isecs['nsec_segs'].append(gcseg)

		self.model_isecs[tseg] = isecs



class Ring:
	"""A class representing the ring and thread carrier."""
	#Default plotting style
	style = {
		'ring':      {'line': dict(color='white', width=10), 'opacity':.25},
		'indicator': {'line': dict(color='blue',  width= 4)},
	}

	def __init__(self, radius=110, angle=0, center:GPoint=None):
		self.radius        = radius
		self._angle        = angle
		self.initial_angle = angle
		self.center        = center or GPoint(radius, 0, 0)
		self.geometry      = Circle(self.center, Vector.z_unit_vector(), self.radius, n=100)


	x = property(**attrhelper('center.x'))
	y = property(**attrhelper('center.y'))
	z = property(**attrhelper('center.z'))


	def __repr__(self):
		return f'Ring({degrees(self._angle):.2f}°)'


	def changed(self, attr, old_value, new_value):
		print(f'Ring.{attr} changed from {old_value} to {new_value}')


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
		"""Used in plotting."""
		return GPoint(
			self.center.x + cos(self.angle)*(self.radius+offset),
			self.center.y + sin(self.angle)*(self.radius+offset),
			self.center.z
		)


	def angle2point(self, angle:radians):
		"""Return an x,y,z=0 location on the ring based on the given angle, without
		moving the ring. Assumes that the bed's bottom-left corner is (0,0).
		Doesn't take into account a machine that uses bed movement for the y-axis,
		but just add the y value to the return from this function."""
		return GPoint(
			cos(angle) * self.radius + self.center.x,
			sin(angle) * self.radius + self.center.y,
			self.center.z
		)


	def gcode(self):
		"""Return the gcode necessary to move the ring from its starting angle
		to its requested one."""
		#Were there any changes in angle?
		if self.angle == self.initial_angle:
			return
		#TODO: generate movement code here; by default move the minimum angle
		gc = GCLine(comment=
			f'----- Ring move from {degrees(self.initial_angle)} to {degrees(self.angle)}')
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
		self.bed  = Bed()
		self.ring = Ring(center=GPoint(110, 110, z))

		self._anchor = GPoint(self.bed.anchor[0], self.bed.anchor[1], z)


	x = property(**attrhelper('_x'))
	y = property(**attrhelper('_y'))
	z = property(**attrhelper('_z'))


	def __repr__(self):
		return f'Printer({self.bed}, {self.ring})'


	@property
	def anchor(self):
		"""Return the current anchor, adjusted for the bed position."""
		return self._anchor

	@anchor.setter
	def anchor(self, new_anchor):
		self._anchor = new_anchor


	def changed(self, attr, old_value, new_value):
		print(f'Printer.{attr} changed from {old_value} to {new_value}')
		setattr(self.ring, attr[1])
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
		gc.append(self.ring.gcode())

		for line in lines:
			self.execute_gcode(line)
			gc.append()

		#filter gc to drop None values
		return filter(None, gc)


	def execute_gcode(self, gcline:GCLine):
		"""Update the printer state according to the passed line of gcode."""
		if gcline.is_xymove():
			self.x = gcline.args['X']
			self.y = gcline.args['Y']


	def thread(self) -> Segment:
		"""Return a Segment representing the current thread, from the anchor point
		to the ring."""
		#TODO: account for bed location (y axis)
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
		thr = self.thread()
		if not any(thr.intersection(i) for i in avoid):
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

		return None


	def thread_intersect(self, target, set_new_anchor=True, move_ring=True):
		"""Rotate the ring so that the thread intersects the target Point. By default
		sets the anchor to the intersection. Return the rotation value."""
		anchor = self.anchor.as2d()
		#Form a half line (basically a ray) from the anchor through the target
		hl = HalfLine(anchor, target.as2d())
		print(f'HalfLine from {self.anchor} to {target}:\n', hl)

		isec = intersection(hl, self.ring.geometry)
		if isec is None:
			raise GCodeException(hl, "Anchor->target ray doesn't intersect ring")

		#The intersection is always a Segment; we want the endpoint furthest from
		# the anchor
		ring_point = sorted(isec[:], key=lambda p: distance(anchor, p),
				reverse=True)[0]

		#Now we need the angle between center->ring and the x axis
		ring_angle = atan2(ring_point.y - self.ring.center.y, ring_point.x - self.ring.center.x)

		if move_ring:
			self.ring.set_angle(ring_angle)

		if set_new_anchor:
			self.anchor = target

		return ring_angle


	def plot_thread_to_ring(self, fig, style=None):
		#Plot a thread from the current anchor to the carrier
		fig.add_trace(go.Scatter(**segs_xy(self.thread(),
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

	def __init__(self, printer, name=''):
		store_attr()
		self.gcsegs = []


	def __repr__(self):
		return f'<Step ({len(self.gcsegs)} segments)>: [light_sea_green italic]{self.name}[/]\n  {self.printer}'


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


	def add(self, gcsegs):
		print(f'Adding {len([s for s in gcsegs if not s.printed])}/{len(gcsegs)} segs')
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
		self.steps.append(Step(self.printer, ' '.join(map(str,messages))))
		return self.current


	def plot(self, prev_layer:TLayer=None):
		steps = self.steps
		last_anchor = steps[0].printer.anchor

		for stepnum,step in enumerate(steps):
			print(f'Step {stepnum}: {step.name}')
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

		print('Finished routing this layer')



class Threader:
	def __init__(self, gcode):
		store_attr()
		self.printer = Printer()


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
		print(f'Route {len(thread_list)}-segment thread through layer:\n  {layer}')
		for i, tseg in enumerate(thread_list):
			print(f'\t{i}. {tseg}')

		self.printer.z = layer.z
		steps = Steps(layer=layer, printer=self.printer)

		#Get the thread segments to work on
		thread = layer.flatten_thread(thread_list)
		steps.flat_thread = thread

		if not thread:
			print('Thread not in layer at all')
			with steps.new_step('Thread not in layer') as s:
				s.add(layer.lines)
			return steps

		print(f'{len(thread)} thread segments in this layer:\n\t{thread}')
		for i,thread_seg in enumerate(thread):
			anchors = layer.anchors(thread_seg)
			self.printer.layer = layer
			self.printer.thread_seg = thread_seg
			with steps.new_step(f'Move thread to overlap anchor at {anchors[0]}') as s:
				self.printer.thread_intersect(anchors[0])

			traj = self.printer.thread().set_z(layer.z)

			msg = (f'Print segments not overlapping thread trajectory {traj}',
						 f'and {len(thread[i:])} remaining thread segments')
			with steps.new_step(*msg) as s:
				layer.intersect_model(traj)
				print(len(layer.non_intersecting(thread[i:] + [traj])), 'non-intersecting')
				s.add(layer.non_intersecting(thread[i:] + [traj]))

			if len(layer.intersecting(thread_seg)) > 0:
				with steps.new_step('Print', len(layer.intersecting(thread_seg)),
						'overlapping layers segments') as s:
					s.add(layer.intersecting(thread_seg))

		remaining = [s for s in layer.geometry.segments if not s.printed]
		if remaining:
			with steps.new_step('Move thread to avoid remaining geometry') as s:
				self.printer.thread_avoid(remaining)

			with steps.new_step(f'Print {len(remaining)} remaining geometry lines') as s:
				s.add(remaining)

		print('[yellow]Done with thread for this layer[/];',
				len([s for s in layer.geometry.segments if not s.printed]),
				'gcode lines left')

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
	g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode', layer_class=TLayer)
	t = Threader(g)
	steps = t.route_layer(thread_geom, g.layers[3])
	#print(steps)
