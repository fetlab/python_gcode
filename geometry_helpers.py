import Geometry3D
from Geometry3D import Vector, Point, Segment, intersection
from gcline import GCLine, GCLines
from dataclasses import make_dataclass
from copy import copy
from fastcore.basics import patch
from math import atan2, pi
from functools import partial
from typing import List

Geometry = make_dataclass('Geometry', ['segments', 'planes', 'outline'])
Planes   = make_dataclass('Planes',   ['top', 'bottom'])

def atan2p(y, x):
	"""Return atan2(y,x), but ensure it's positive by adding 2pi if it's
	negative."""
	ang = atan2(y,x)
	return ang if ang > 0 else ang + 2*pi


def ccw(a:Point, b:Point, c:Point):
	"""Compare the angles of a and b with respect to c as a center point. If a is
	collinear to b, return 0; return negative if a is counter-clockwise from b,
	and positive if it is clockwise."""
	return atan2p(a.y-c.y, a.x-c.x) - atan2p(b.y-c.y, b.x-c.x)


def ccw_dist(p,a,c):
	"""Return CCW angular distance of point P from the line formed by a-c"""
	v = atan2(a.y-c.y,a.x-c.x)-atan2(p.y-c.y,p.x-c.x)
	return v if v > 0 else v + 2*pi


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


def angsort(points: List[Point], ref:Segment):
	"""Return points sorted counter-clockwise with respect to the reference
	segment."""
	return sorted(points, key=partial(ccw_dist, a=ref.end_point, c=ref.start_point), reverse=True)


#Help in plotting
def segs_xyz(*segs, **kwargs):
	#Plot gcode segments. The 'None' makes a break in a line so we can use
	# just one add_trace() call.
	x, y, z = [], [], []
	for s in segs:
		x.extend([s.start_point.x, s.end_point.x, None])
		y.extend([s.start_point.y, s.end_point.y, None])
		z.extend([s.start_point.z, s.end_point.z, None])
	return dict(x=x, y=y, z=z, **kwargs)


def segs_xy(*segs, **kwargs):
	d = segs_xyz(*segs, **kwargs)
	del(d['z'])
	return d


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



class HalfLine(Geometry3D.HalfLine):
	def __init__(self, a, b):
		self._a = a
		self._b = b
		super().__init__(a, b)


	def as2d(self):
		if not isinstance(self._b, Point):
			raise ValueError(f"Can't convert {type(self._b)} to 2D")
		return Geometry3D.HalfLine(
				GPoint.as2d(self._a),
				GPoint.as2d(self._b))


	def __repr__(self):
		return "H({}, {})".format(self.point, self.vector)



class GPoint(Point):
	def __init__(self, *args, **kwargs):
		"""Pass Geometry3D.Point arguments or a gcline.GCLine and optionally a *z*
		argument. If *z* is missing it will be set to 0."""
		self.line = None
		z = kwargs.get('z', 0) or 0

		if len(args) == 1:
			if isinstance(args[0], GCLine):
				l = args[0]
				if not (l.code in ('G0', 'G1') and 'X' in l.args and 'Y' in l.args):
					raise ValueError(f"GCLine instance isn't an X or Y move:\n\t{args[0]}")
				super().__init__(l.args['X'], l.args['Y'], z)
				self.line = l

			elif isinstance(args[0], (list,tuple)):
				super().__init__(args[0])

			elif isinstance(args[0], (GPoint, Point)):
				super().__init__(
					kwargs.get('x', args[0].x),
					kwargs.get('y', args[0].y),
					kwargs.get('z', args[0].z))

			else:
				raise ValueError(f'Invalid type for arg to GPoint: ({type(args[0])}) {args[0]}')

		elif len(args) == 2:
			super().__init__(*args)

		elif len(args) == 3:
			super().__init__(*args)

		else:
			raise ValueError(f"Can't init GPoint with args {args}")

	def __repr__(self):
		return "{{{:>6.2f}, {:>6.2f}, {:>6.2f}}}".format(self.x, self.y, self.z)

	def as2d(self):
		"""Return a copy of this point with *z* set to 0. If z is already 0, return self."""
		if self.z == 0: return self
		return self.copy(z=0)


	def inside(self, seglist):
		"""Return True if this point is inside the polygon formed by the Segments
		in seglist."""
		#We make a segment from this point to 0,0,0 and test intersections; if
		# there are an even number, the point is inside the polygon.
		test_seg = GSegment(self.as2d(), (0,0,0))
		return len([s for s in seglist if intersection(test_seg, s.as2d())]) % 2


	def copy(self, z=None):
		c = copy(self)
		if z is not None: c.z = z
		return c


	def moved(self, vec):
		"""Return a copy of this point moved by vector vec."""
		return self.copy().move(vec)


class GSegment(Geometry3D.Segment):
	def __init__(self, a, b, z=None, gc_lines=None, is_extrude=False, **kwargs):
		#Label whether this is an extrusion move or not
		self.is_extrude = is_extrude

		self.printed = False

		#Save the movement lines of gcode
		self.gc_line1 = None
		self.gc_line2 = None

		#Save *all* lines of gcode involved in this segment
		self.gc_lines = GCLines(gc_lines) or GCLines()

		#Argument |a| is a GSegment: instantiate a copy
		if isinstance(a, GSegment):
			if b is not None:
				raise ValueError('Second argument must be None when first is a GSegment')
			if not ('start_point' in kwargs or 'end_point' in kwargs):
				raise ValueError('Provide explicit start_point and/or end_point argument')
			copyseg = a
			a = kwargs.get('start_point', copyseg.start_point)
			b = kwargs.get('end_point', copyseg.end_point)
			z = a.z if z is None else z
			gc_lines = copyseg.gc_lines if gc_lines is None else gc_lines
			is_extrude = copyseg.is_extrude or is_extrude

		#If instantiating a copy, |a| and |b| have been set from the passed GSegment
		if isinstance(a, Point):
			point1 = a if isinstance(a, GPoint) else GPoint(a)
		elif isinstance(a, GCLine):
			point1 = GPoint(a, z=z)
			self.gc_line1 = a
			self.gc_lines.append(a)
		elif isinstance(a, (tuple,list)):
			point1 = GPoint(*a)
		else:
			print(a, type(a), type(a) == GSegment)
			raise ValueError("Attempt to instantiate a GSegment with argument |a| as "
					f"type {type(a)}, but only <GSegment>, <Point>, <GCLine>, <tuple> and <list> are supported.\n"
					" If this occurrs in a Jupyter notebook, it's because reloading messes things up. Try restarting the kernel.")

		if isinstance(b, Point):
			point2 = b if isinstance(b, GPoint) else GPoint(b)
		elif isinstance(b, GCLine):
			point2 = GPoint(b, z=z)
			self.gc_line2 = b
			self.gc_lines.append(b)
		elif isinstance(b, (tuple,list)):
			point2 = GPoint(*b)
		else:
			raise ValueError(f"Arg b is type {type(b)} = {b} but that's not supported!")

		if z is not None:
			point1.z = point2.z = z

		if point1 == point2:
			raise ValueError("Cannot initialize a Segment with two identical Points\n"
					f"Init args: a={a}, b={b}, z={z}")

		self.line = Geometry3D.Line(point1, point2)
		self.start_point = point1
		self.end_point   = point2

		#Sort any gcode lines by line number
		self.gc_lines.sort()


	def __repr__(self):
		if not(self.gc_line1 and self.gc_line2):
			return super().__repr__()
		return "<{}[{}] {}:{}←→{}:{}>".format(
				'S' if self.printed else 's',
				len(self.gc_lines),
				self.gc_line1.lineno, self.start_point,
				self.gc_line2.lineno, self.end_point)


	def intersection2d(self, other):
		return intersection(self.as2d(), other.as2d())


	def as2d(self):
		if self.start_point.z == 0 and self.end_point.z == 0:
			return self
		return GSegment(self.start_point.as2d(), self.end_point.as2d())


	def set_z(self, z):
		"""Set both endpoints of this Segment to a new z."""
		if self.start_point.z == z and self.end_point.z == z:
			return self
		self.start_point.z = z
		self.end_point.z = z
		self.line = Geometry3D.Line(self.start_point, self.end_point)
		return self


	def copy(self, start_point=None, end_point=None, z=None):
		return GSegment(self, None,
			start_point=start_point or self.start_point,
			end_point=end_point     or self.end_point,
			z=z)



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
