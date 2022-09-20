import logging
import plotly, plotly.graph_objects as go
from Geometry3D import Point, Segment, Plane, distance
from geometry_helpers import GPoint, GSegment, Geometry, Planes, seg_combine, gcode2segments
from typing import List, Set
from itertools import cycle
from cura4layer import Cura4Layer
from fastcore.basics import listify

log = logging.getLogger('threader')

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


	def plot(self, fig=None,
			move_colors:List=plotly.colors.qualitative.Set2,
			extrude_colors:List=plotly.colors.qualitative.Dark2,
			plot3d=False, only_outline=True, show=False):
		"""Plot the geometry making up this layer. Set only_outline to True to
		print only the outline of the gcode in the layer .
		"""
		self.add_geometry()
		colors = cycle(zip(extrude_colors, move_colors))

		if fig is None:
			fig = go.Figure()

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

		if show:
			fig.update_layout(template='plotly_dark',# autosize=False,
					yaxis={'scaleanchor':'x', 'scaleratio':1, 'constrain':'domain'},
					margin=dict(l=0, r=20, b=0, t=0, pad=0),
					showlegend=False,)
			fig.show()

		return fig



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
		self.preamble, self.geometry.segments, self.postamble = gcode2segments(self.lines, self.z)

		#Construct top/bottom planes for intersections
		(min_x, min_y), (max_x, max_y) = self.extents()
		mid_x = min_x + .5 * (max_x - min_x)
		z = self.z

		plane_points = [(min_x, min_y), (mid_x, max_y), (max_x, max_y)]
		bot_z        = z - self.layer_height/2
		top_z        = z + self.layer_height/2
		bottom       = Plane(*[GPoint(p[0], p[1], bot_z) for p in plane_points])
		top          = Plane(*[GPoint(p[0], p[1], top_z) for p in plane_points])
		bottom.z     = bot_z
		top.z        = top_z

		self.geometry.planes = Planes(bottom=bottom, top=top)

		#Find the outline by using Cura comments for "wall-outer"
		for part, lines in self.parts.items():
			if 'type:wall-outer' in (lines[0].comment or '').lower():
				self.geometry.outline.extend(
						[line.segment for line in lines if line.is_xyextrude()])


	def flatten_thread(self, thread: List[Segment]) -> List[GSegment]:
		"""Process the input thread:
			* Clip it to the top/bottom of the layer (the layer height)
			* Flatten in-layer segments to have the same z-height as the layer
			* Combine resulting segments that are on the same line into a single segment"""
		self.add_geometry()

		top = self.geometry.planes.top
		bot = self.geometry.planes.bottom
		segs = []

		for i,tseg in enumerate(thread):
			#Is the thread segment entirely below or above the layer? If so, skip it.
			if((tseg.start_point.z <  bot.z and tseg.end_point.z <  bot.z) or
				 (tseg.start_point.z >= top.z and tseg.end_point.z >= top.z)):
				log.debug(f'{i}. {tseg} endpoints not in layer',
						extra=dict(style={'line-height':'normal'}))
				continue


			#Clip segments to top/bottom of layer (note "walrus" operator := )
			if s := tseg.intersection(bot): self.in_out.append(s)
			if e := tseg.intersection(top): self.in_out.append(e)
			newseg = GSegment(s or tseg.start_point, e or tseg.end_point)

			#Flatten segment to the layer's z-height, but not if the segment is
			# vertical
			if newseg.start_point.as2d() != newseg.end_point.as2d():
				newseg.set_z(self.z)
			segs.append(newseg)
			# if s or e:
			# 	print(f'Crop {tseg} to\n'
			# 			  f'     {segs[-1]}')

			#segs[-1].set_z(self.z)

		#Combine collinear segments
		segs = seg_combine(segs)

		#Cache intersections
		# self.intersect_model(segs)

		return segs


	def geometry_snap(self, thread: List[GSegment]) -> List[GSegment]:
		"""Return new thread segments, modified as follows:
			* Each segment end point is moved to its closest intersection with
				printed layer geometry.
			* Each segment start point (except the first segment's) is moved to the
				end point of the preceding segment.
			* If the closest intersection is the same as the start point, then no new
				segment is generated.
			The return value is a dict: {original_segment: new_segment or None}
		"""
		end = None
		newthread = {}

		for tseg in thread:
			if end and tseg.start_point != end: tseg = tseg.copy(start_point=end)
			mindist = float('inf')
			for s in self.geometry.segments:
				if tseg.end_point in s:
					log.debug(f'{tseg.end_point} in segment {s}')
					end = tseg.end_point
					break
				isec = Plane(tseg.end_point, s.line.dv).intersection(s)
				if isec is None: continue
				dist = isec.distance(tseg.end_point)
				if dist < mindist:
					mindist = dist
					end = isec

			#No intersections with anything
			if end is None: raise ValueError(f"Can't snap segment {tseg}")

			if (move_dist := tseg.end_point.distance(end)) > 1:
				log.debug(f"WARNING: moved end point for {tseg} {move_dist:02f} mm")

			#Not enough distance to intersect anything else
			if end == tseg.start_point:
				log.debug(f'Closest point for {tseg} is its start point, dropping it')
				newthread[tseg] = None
			else:
				newthread[tseg] = tseg.copy(end_point=end)

		return newthread

		#for tseg in thread:
		#	if end: tseg = tseg.copy(start_point=end)
		#	hl = HalfLine(tseg.start_point, tseg.end_point)
		#	self.intersect_model([hl])
		#	isecs = self.model_isecs[hl]['isec_points']
		#	end = sorted(isecs, key=lambda p:distance(tseg.end_point, p))[0]

		#	if (move_dist := end.distance(tseg.end_point)) > 1:
		#		print(f"WARNING: moved end point for {tseg} {move_dist:02f} mm")

		#	#Not enough distance to intersect anything else
		#	if end == tseg.start_point:
		#		continue

		#	tseg = tseg.copy(end_point=end)
		#	newthread.append(tseg)

		#return newthread


	def non_intersecting(self, thread: List[Segment]) -> Set[GSegment]:
		"""Return a list of GSegments which the given thread segments do not
		intersect."""
		thread = listify(thread)
		self.intersect_model(thread)

		#First find all *intersecting* GSegments
		intersecting = self.intersecting(thread)

		#And all non-intersecting GSegments
		non_intersecting = set.union(*[self.model_isecs[tseg]['nsec_segs'] for tseg in thread])

		#And return the difference
		return non_intersecting - intersecting


	def intersecting(self, thread: GSegment|List[GSegment]) -> Set[GSegment]:
		"""Return a set of GSegments which the given thread segment(s) intersect."""
		thread = listify(thread)
		if not thread: return set()
		self.intersect_model(thread)
		return set.union(*[self.model_isecs[t]['isec_segs'] for t in thread])


	def anchors(self, tseg: Segment) -> List[GPoint]:
		"""Return a list of "anchor points" - Points at which the given thread
		segment intersects the layer geometry, ordered by distance to the
		end point of the thread segment (with the assumption that this the
		"true" anchor point, as the last location the thread will be stuck down."""
		anchors = self.model_isecs[tseg]['isec_points'].copy()
		entry   = tseg.start_point
		exit    = tseg.end_point

		log.debug(f'anchors with thread segment: {tseg}')
		log.debug(f'isec anchors: {anchors}')
		if entry in self.in_out and entry.inside(self.geometry.outline):
			anchors.add(entry)
			log.debug(f'Entry anchor: {entry}')
		if exit in self.in_out and exit.inside(self.geometry.outline):
			anchors.add(exit)
			log.debug(f'Exit anchor: {exit}')

		return sorted(anchors, key=lambda p:distance(tseg.end_point, p))


	def intersect_model(self, segs):
		"""Given a list of thread segments, calculate all of the intersections with the model's
		printed lines of gcode. Caches in self.model_isecs:
			nsec_segs, isec_segs, isec_points
		where
			nsec_segs is non-intersecting GCLines
			isec_segs is intersecting GCLines
			isec_points is a list of GPoints for the intersections
		"""
		self.add_geometry()

		for tseg in segs:
			if tseg in self.model_isecs:
				continue

			isecs = {
				'nsec_segs': set(),                       # Non-intersecting gcode segments
				'isec_segs': set(), 'isec_points': set(), # Intersecting gcode segments and locations
			}

			for gcseg in self.geometry.segments:
				if not gcseg.is_extrude: continue

				inter = gcseg.intersection(tseg)
				if inter is None:
					isecs['nsec_segs'].add(gcseg)
				else:
					isecs['isec_segs'].add(gcseg)
					if isinstance(inter, Point):
						inter = GPoint(inter)
						isecs['isec_points'].add(inter)
					elif isinstance(inter, Segment):
						isecs['isec_points'].update(map(GPoint, inter[:]))

			self.model_isecs[tseg] = isecs
