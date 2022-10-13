#from Geometry3D import Vector, Point, Segment, Line, Plane
from gcline import GCLines
from dataclasses import make_dataclass
from typing import List, Dict, Collection
from collections import defaultdict
from more_itertools import flatten

from geometry.gpoint import GPoint
from geometry.gsegment import GSegment
from geometry.ghalfline import GHalfLine, GHalfLine as HalfLine
from geometry.utils import tangent_points


Geometry = make_dataclass('Geometry', ['segments', 'planes', 'outline'])
Planes   = make_dataclass('Planes',   ['top', 'bottom'])


def visibility(thread, avoid):
	endpoints = set(sum([seg[:] for seg in avoid], ()))
	non_isecs = endpoints.copy()
	for p in endpoints:
		h = HalfLine(thread.start_point, p)
		for seg in avoid:
			if thread.start_point in seg or seg.start_point == p or seg.end_point == p:
				continue
			if h.intersection(seg):
				non_isecs.remove(p)
				break
	return non_isecs


def visibility2(origin:GPoint, query:List[GSegment]):
	"""Given a point origin and a query list of segments, find endpoints of the
	segments that are visible from origin (no intersections between origin and
	the endpoints). Return a dict of those endpoints and the segments associated
	with them: {endpoint: [segments]}."""
	endpoints = defaultdict(list)
	for seg in query:
		endpoints[seg.start_point].append(seg)
		endpoints[seg.end_point  ].append(seg)
	non_isecs = endpoints.copy()
	non_isecs.pop(origin, None)
	for p,point_segs in endpoints.items():
		if p not in non_isecs: continue
		h = HalfLine(origin, p)
		for seg in query:
			if origin in seg or seg.start_point == p or seg.end_point == p:
				continue
			if h.intersection(seg):
				non_isecs.pop(p, None)
				break
	return non_isecs


def avoid_visible(origin:GPoint, visible:Dict, query:Collection[GSegment], avoid_by=1):
	"""Given a point origin and a visibilty dict as returned by visibility2,
	return points where for each point:
		* the point is avoid_by away from the endpoints of visible segments
		* a half-line between origin and the point does not intersect any segment in query
	"""
	tan_points = set(flatten([tangent_points(p, avoid_by, origin) for p in visible]))
	isec_points = set()
	for p in tan_points:
		include = True
		for seg in query:
			isec = GSegment(origin, p).intersection(seg)
			if isec is not None and isec != origin:
				include = False
				break
			if isec is not None and isec != origin:
				include = False
				break
		if include: isec_points.add(p)
	return isec_points



def visibility3(origin:GPoint, query:Collection[GSegment], avoid_by=1):
	"""Return a tuple:
		(the set of endpoints of Segments in query that are visible from origin,
			segments in query that are "in the way" of other endpoints)

		Visibility for each point means:
			* a half-line between origin and the point does not intersect any segment
				in query
			* the point is avoid_by away from the endpoint of any segment in query
	"""
	endpoints = set(flatten(query))

	#Find points that form a tanget line between the origin and a circle of
	# avoid_by radius around each end point
	tanpoints = set(flatten(tangent_points(p, avoid_by, origin) for p in endpoints))

	#Return tangent points where a half-line from the origin to that point does
	# not intersect any segment in query, ignoring intersections with the origin
	vis_points = set()
	# for tp in tanpoints:
	# 	hl = HalfLine(origin, tp)
	# 	if(not any(hl.intersection(seg) not in [None, origin] for seg in query)
	# 			and all(hl.line.distance(ep) >= avoid_by for ep in endpoints)):
	# 		vis_points.add(tp)
	# return vis_points

	isec_segs = set()
	for tp in tanpoints:
		hl = HalfLine(origin, tp)
		for seg in query:
			if (hl.intersection(seg) not in [None, origin]   or
					hl.line.distance(seg.start_point) < avoid_by or
					hl.line.distance(seg.end_point  ) < avoid_by):
				include = False
				isec_segs.add(seg)
		if include:
			vis_points.add(tp)

	return vis_points, isec_segs


def visibility4(origin:GPoint, query:Collection[GSegment], avoid_by=1):
	endpoints = set(flatten(query)) - {origin}
	tanpoints = set(flatten(
			tangent_points(p, avoid_by, origin) for p in endpoints))
	isecs = {}

	for tp in tanpoints:
		hl = HalfLine(origin, tp)
		isecs[tp] = set()
		for seg in query:
			isec = False
			if hl.intersecting(seg):
				isec = True
			if not isec:
				if seg.start_point != origin:
					d = hl.distance(seg.start_point)
					if d is not None and d < avoid_by:
						isec = True
			if not isec:
				d = hl.distance(seg.end_point)
				if d is not None and d < avoid_by:
					isec = True

			if isec:
				isecs[tp].add(seg)

	return dict(sorted(isecs.items(), key=lambda x:len(x[1])))


def visibility5(origin:GPoint, query:Collection[GSegment], avoid_by=.5):
	"""Return
		{point: set(segments), ...},
	where a half-line drawn from `origin` to `point` intersects {segments}. The
	returned dict is sorted by the number of intersected segments.
	"""
	endpoints = set(flatten(query)) - {origin}
	tanpoints = set(flatten(
			tangent_points(p, avoid_by, origin) for p in endpoints))
	r = {}
	for ep in tanpoints:
		hls = GHalfLine(origin, ep).parallels2d(avoid_by, inc_self=True)
		r[ep] = {seg for seg in query if seg.intersecting(hls)}
	return dict(sorted(r.items(), key=lambda x:len(x[1])))



def split_segs(segments, by:Segment):
	"""Split the given segments by a plane defined by using the segment 'by' as
	the origin and direction vector for the plance. Return lists
	(same_side, opp_side), where segments in same_side have at least one point in
	the direction of 'by' and segments in opp_side are the rest."""
	plane = Plane(by.start_point, by.line.dv)
	b = bucket(segments, key=lambda s:plane.pointcmp(s[0]) >= 0 or plane.pointcmp(s[1]) >= 0)
	return set(b[True]), set(b[False])




#Combine subsequent segments on the same line
def seg_combine(segs):
	if not segs: return []
	r = [segs[0]]
	for seg in segs[1:]:
		if seg.line == r[-1].line:
			# print(f'Combine {r[-1]}, {seg}', end='')
			if seg.end_point == r[-1].start_point:
				r[-1] = GSegment(seg.start_point, r[-1].end_point)
			elif r[-1].end_point == seg.start_point:
				r[-1] = GSegment(r[-1].start_point, seg.end_point)
			else:
				s1 = GSegment(  seg.start_point, r[-1].end_point)
				s2 = GSegment(r[-1].start_point,   seg.end_point)
				r[-1] = max(s1, s2, key=lambda s: s.length())
			# print(f' -> {r[-1]}')
		else:
			# print(f"Don't combine {r[-1]}, {seg}")
			r.append(seg)
	return r


def gcode2segments(lines:GCLines, z, keep_moves_with_extrusions=True):
	"""Turn GCLines into GSegments. Keep in mind that the first line denotes the start
	point only, and the second line denotes the action (e.g. extrude) *and* the end
	point. Mark extrusion GSegments. Return preamble, segments, postamble.

	Set keep_moves_with_extrusions to False to make pairs of non-extruding
	movements into independent GSegments; otherwise, sequences of non-extrusion
	moves preceding an extrusion move will be grouped into the extrusion move.
	"""
	lines    = lines.copy()
	last     = None
	extra    = GCLines()
	preamble = GCLines()
	segments = []

	#Put all beginning non-extrusion lines into preamble
	while lines and not lines.first.is_xymove():
		preamble.append(lines.popidx(0))

	#Put the first xymove as the "last" item
	last = lines.popidx(0)

	if keep_moves_with_extrusions:
		for line in lines:
			if line.is_xyextrude():
				line.segment = GSegment(last, line, z=z, gc_lines=extra, is_extrude=line.is_xyextrude())
				segments.append(line.segment)
				last = line
				extra = []
			elif line.is_xymove():
				if not last.is_xyextrude():
					extra.append(last)
				last = line
			else:
				extra.append(line)
		if not last.is_xyextrude() and last not in extra:
			extra.append(last)
			extra.sort()

	else:
		#Now take pairs of xymove lines, accumulating intervening non-move lines in
		# extra
		for line in lines:
			if line.is_xymove():
				line.segment = GSegment(last, line, z=z, gc_lines=extra, is_extrude=line.is_xyextrude())
				segments.append(line.segment)
				last  = line
				extra = []
			else: #non-move line following a move line
				extra.append(line)

	return preamble, segments, extra


# ------- Monkey patching for improved Geometry3D objects ------

# --- Point
@patch
def __repr__(self:Point):
	return "!{{{:>6.2f}, {:>6.2f}, {:>6.2f}}}".format(self.x, self.y, self.z)
@patch
def as2d(self:Point):
	return Point(self.x, self.y, 0)
@patch
def xyz(self:Point):
	return self.x, self.y, self.z
@patch
def xy(self:Point):
	return self.x, self.y
Point.inside = GPoint.inside


# --- Segment
@patch
def __repr__(self:Segment):
	return "<{}←→{}>".format(self.start_point, self.end_point)
@patch
def as2d(self:Segment):
	return GSegment(self.start_point.as2d(), self.end_point.as2d())
@patch
def xyz(self:Segment):
	x, y, z = tuple(zip(self.start_point.xyz(), self.end_point.xyz()))
	return dict(x=x, y=y, z=z)
@patch
def xy(self:Segment):
	x, y = tuple(zip(self.start_point.xy(), self.end_point.xy()))
	return dict(x=x, y=y)


# --- Vector
@patch
def __repr__(self:Vector):
	return "V({:.2f}, {:.2f}, {:.2f})".format(*self._v)


# --- Plane
@patch
def pointcmp(self:Plane, point:Point):
	"""Return whether point is below (-1), on (0), or above (1) plane."""
	isec = Line(point, self.n).intersection(self)
	return sign(Vector(isec, point) * self.n)
