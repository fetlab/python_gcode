import plotly, plotly.graph_objects as go
from copy import deepcopy
from Geometry3D import Circle, Vector, Segment, Point, Plane, intersection, distance
from math import radians, sin, cos, degrees
from typing import List
from geometry_helpers import GPoint, GSegment, Geometry, Planes, HalfLine, segs_xy, seg_combine
from fastcore.basics import basic_repr, store_attr
from rich import print
from math import atan2
from parsers.cura4 import Cura4Layer
from time import time
from itertools import cycle

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
	* [ ] Take care of moving to start point of a Segment after an order change
"""


def update_traces(fig, name, style):
	"""Update traces for the passed figure object for traces with the given name.
	style should be a dict like {name: {'line': {'color': 'red'}}} .
	"""
	if style and name in style:
		fig.update_traces(selector={'name':name}, **style[name])

class GCodeException(Exception):
	def __init__(self, obj, message):
		self.obj = obj
		self.message = message



class TLayer(Cura4Layer):
	def __init__(self, *args, layer_height=0.4, **kwargs):
		super().__init__(*args, **kwargs)
		self.geometry = None
		self.layer_height = layer_height
		self.model_isecs = {}
		self.in_out = []


	def plot(self, fig,
			move_colors=plotly.colors.qualitative.Set2,
			extrude_colors=plotly.colors.qualitative.Dark2,
			plot3d=False, only_outline=True):
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
		"""Add geometry to this Layer based on the list of lines, using
		GSegment."""
		if self.geometry or not self.has_moves:
			return
		self.geometry = Geometry(segments=[], planes=None, outline=[])

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
					'in_layer': False,                    # Is the thread in this layer at all?
					'nsec_segs': [],                      # Non-intersecting gcode segments
					'isec_segs': [],   'isec_points': [], # Intersecting gcode segments and locations
					'enter':     None, 'exit': None,      # Thread segment entry and/or exit locations
			}

			enter = tseg.intersection(bot)
			exit  = tseg.intersection(top)
			isecs['enter'] = enter
			isecs['exit']  = exit

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

			isecs['in_layer'] = any([
				(enter and enter.inside(self.geometry.outline)),
				(exit  and exit .inside(self.geometry.outline)),
				tseg.start_point.inside(self.geometry.outline),
				tseg.end_point  .inside(self.geometry.outline)] +
				isecs['isec_segs'])


class Ring:
	#Defaults
	_radius = 110  #mm
	_angle  = 0    #radians
	_center = Point(110, 110, 0) #mm

	#Default plotting style
	style = {
		'ring':      {'line': dict(color='white', width=10), 'opacity':.25},
		'indicator': {'line': dict(color='blue',  width= 4)},
	}

	__repr__ = basic_repr('_radius,_angle,_center')

	def __init__(self, radius=_radius, angle:radians=_angle, center=_center):
		store_attr()

		self._angle        = angle
		self.initial_angle = angle
		self.geometry      = Circle(self.center, Vector.z_unit_vector(), self.radius, n=50)
		self.x_axis        = Vector(self.center,
																Point(self.center.x + self.radius,
																			self.center.y, self.center.z))


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


	def set_z(self, z):
		self.center.z = z


	def set_angle(self, new_angle:radians, direction=None):
		"""Set a new angle for the ring. Optionally provide a preferred movement
		direction as 'CW' or 'CCW'; if None, it will be automatically determined."""
		self.initial_angle = self._angle
		self._angle = new_angle
		self._direction = direction


	def carrier_location(self, offset=0):
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
		pass


	def plot(self, fig, style=None):
		fig.add_trace(go.Scatter(
			**segs_xy(*list(self.geometry.segments()),
				name='ring', **self.style['ring'])))
		update_traces(fig, 'ring', style)

		ringwidth = next(fig.select_traces(selector={'name':'ring'})).line.width

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
		if style and 'indicator' in style:
			fig.update_shapes(selector={'name':'indicator'}, **style['indicator'])



class Bed:
	__repr__ = basic_repr('anchor')

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


	def plot(self, fig, style=None):
		fig.add_shape(
			name='bed',
			type='rect',
			xref='x', yref='y',
			x0=0, y0=0,
			x1=self.size[0], y1=self.size[1],
			**self.style['bed'],
		)
		update_traces(fig, 'bed', style)



class State:
	"""Maintains the state of the printer/ring system. Holds references to the
	Ring and Bed objects.
	"""
	style = {
		'thread': {'mode':'lines', 'line': dict(color='white', width=1, dash='dot')},
		'anchor': {'mode':'markers', 'marker': dict(color='red', symbol='x', size=4)},
	}

	def __init__(self, bed:Bed, ring:Ring, z=0):
		store_attr()
		self.ring.set_z(z)
		self.anchor = GPoint(bed.anchor[0], bed.anchor[1], z)


	def __repr__(self):
		return f'State(Bed, {self.ring})'


	def freeze(self):
		"""Return a copy of this State object, capturing the state."""
		return deepcopy(self)


	def set_z(self, z):
		self.z = z
		self.ring.set_z(z)


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
			print(f'new anchor: {target}')
			self.anchor = target

		return ring_angle


	def plot_thread_to_ring(self, fig, style=None):
		#Plot a thread from the current anchor to the carrier
		fig.add_trace(go.Scatter(**segs_xy(self.thread(),
			name='thread', **self.style['thread'])))
		update_traces(fig, 'thread', style)


	def plot_anchor(self, fig, style=None):
		fig.add_trace(go.Scatter(x=[self.anchor.x], y=[self.anchor.y],
			name='anchor', **self.style['anchor']))
		update_traces(fig, 'anchor', style)



class Step:
	#Default plotting style
	style = {
		'gc_segs': {'mode':'lines', 'line': dict(color='green',  width=1)},
		'thread':  {'mode':'lines', 'line': dict(color='yellow', width=1, dash='dot')},
	}

	def __init__(self, state, name=''):
		store_attr()
		self.gcsegs = []


	def __repr__(self):
		return f'<Step ({len(self.gcsegs)} segments)>: [light_sea_green italic]{self.name}[/]\n  {self.state}'


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
		self.state = self.state.freeze()


	def plot_gcsegments(self, fig, gcsegs=None, style=None):
		#Plot gcode segments. The 'None' makes a break in a line so we can use
		# just one add_trace() call.
		segs = {'x': [], 'y': []}
		segs_to_plot = gcsegs if gcsegs is not None else self.gcsegs
		for seg in segs_to_plot:
			segs['x'].extend([seg.start_point.x, seg.end_point.x, None])
			segs['y'].extend([seg.start_point.y, seg.end_point.y, None])
		fig.add_trace(go.Scatter(**segs, name='gc_segs', **self.style['gc_segs']))
		update_traces(fig, 'gc_segs', style)


	def plot_thread(self, fig, start:Point, style=None):
		#Plot a thread segment, starting at 'start', ending at the current anchor
		if start == self.state.anchor:
			return
		fig.add_trace(go.Scatter(
			x=[start.x, self.state.anchor.x],
			y=[start.y, self.state.anchor.y],
			**self.style['thread'],
		))
		update_traces(fig, 'thread', style)


class Steps:
	#Default plotting style
	style = {
		'old_segs':   {'line_color': 'gray'},
		'old_thread': {'line_color': 'blue'},
		'old_layer':  {'line': dict(color='gray', dash='dot')},
	}
	def __init__(self, layer, state):
		store_attr()
		self.steps = []
		self._current_step = None


	def __repr__(self):
		return '\n'.join(map(repr, self.steps))


	@property
	def current(self):
		return self.steps[-1] if self.steps else None


	def new_step(self, *messages):
		self.steps.append(Step(self.state, ' '.join(map(str,messages))))
		return self.current


	def plot(self, prev_layer:TLayer=None):
		steps = self.steps
		last_anchor = steps[0].state.anchor

		for stepnum,step in enumerate(steps):
			print(f'Step {stepnum}: {step.name}')
			fig = go.Figure()

			#Plot the bed
			step.state.bed.plot(fig)

			#Plot the outline of the previous layer, if provided
			if prev_layer:
				prev_layer.plot(fig,
						move_colors    = [self.style['old_layer']['line']['color']],
						extrude_colors = [self.style['old_layer']['line']['color']],
						only_outline   = True,
				)

			#Plot the thread from the bed anchor to the first step's anchor
			steps[0].plot_thread(fig, steps[0].state.bed.anchor)

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
							steps[i-1].state.anchor,
							style={'thread': self.style['old_thread']},
					)

			#Plot geometry printed in this step
			step.plot_gcsegments(fig)

			#Plot thread trajectory from current anchor to ring
			step.state.plot_thread_to_ring(fig)

			#Plot thread from last step's anchor to current anchor
			step.plot_thread(fig, last_anchor)
			last_anchor = step.state.anchor

			#Plot anchor/enter/exit points if any
			if thread_seg := getattr(step.state, 'thread_seg', None):
				step.state.plot_anchor(fig)

				if enter := getattr(thread_seg.start_point, 'in_out', None):
					if enter.inside(step.state.layer.geometry.outline):
						fig.add_trace(go.Scatter(x=[enter.x], y=[enter.y], mode='markers',
							marker=dict(color='yellow', symbol='x', size=8), name='enter'))

				if exit := getattr(thread_seg.end_point, 'in_out', None):
					if exit.inside(step.state.layer.geometry.outline):
						fig.add_trace(go.Scatter(x=[exit.x], y=[exit.y], mode='markers',
							marker=dict(color='orange', symbol='x', size=8), name='exit'))

			#Plot the ring
			step.state.ring.plot(fig)

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
		self.state = State(Bed(), Ring())


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

		self.state.set_z(layer.z)
		steps = Steps(layer=layer, state=self.state)

		#Get the thread segments to work on
		thread = layer.flatten_thread(thread_list)
		steps.flat_thread = thread

		if not thread:
			print('Thread not in layer at all')
			return steps

		"""
		with steps.new_step('Move thread out of the way') as s:
			#rotate ring to avoid segments it shouldn't intersect
			#TODO: in the case where lots of segments are non-intersecting, we need
			# to do a multi-step procedure to move the thread, print, then move the
			# thread over the printed ones and print again.
			self.state.thread_avoid(layer.non_intersecting(thread + [traj]))

		with steps.new_step('Print non-intersecting layer segments') as s:
			#TODO: this also needs to take into account the strand from the anchor to
			# the ring, if we can't completely avoid printed geometry
			s.add(layer.non_intersecting(thread))
		"""

		# with steps.new_step('Set thread location') as s:
		# 	pass

		print(f'{len(thread)} thread segments in this layer:\n\t{thread}')
		for i,thread_seg in enumerate(thread):
			anchors = layer.anchors(thread_seg)
			self.state.layer = layer
			self.state.thread_seg = thread_seg
			with steps.new_step(f'Move thread ({thread_seg}) to overlap anchor at {anchors[0]}') as s:
				self.state.thread_intersect(anchors[0])

			traj = self.state.thread().set_z(layer.z)

			msg = (f'Print segments not overlapping thread trajectory {traj}',
						 f'and {len(thread[i:])} remaining thread segments')
			with steps.new_step(*msg) as s:
				#BUG: intersect_model sets all segments' .printed = False, then we end
				# up re-printing
				layer.intersect_model(traj)
				print(len(layer.non_intersecting(thread[i:] + [traj])), 'non-intersecting')
				s.add(layer.non_intersecting(thread[i:] + [traj]))

			with steps.new_step('Print', len(layer.intersecting(thread_seg)),
					'overlapping layers segments') as s:
				s.add(layer.intersecting(thread_seg))

		remaining = [s for s in layer.geometry.segments if not s.printed]
		if remaining:
			with steps.new_step(f'Move thread {thread_seg} to avoid remaining geometry') as s:
				self.state.thread_avoid(remaining)

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
	g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode',
			layer_class=TLayer)
	t = Threader(g)
	steps = t.route_layer(thread_geom, g.layers[3])
	#print(steps)
