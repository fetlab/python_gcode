import Geometry3D
from Geometry3D import Vector, Point, Segment, intersection
from gcline import Line as GCLine
from dataclasses import make_dataclass
from copy import copy
from fastcore.basics import patch
from rich import print

Geometry = make_dataclass('Geometry', ['segments', 'planes', 'outline'])
Planes   = make_dataclass('Planes',   ['top', 'bottom'])

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


#Monkey-patch Point
@patch
def __repr__(self:Point):
	return "{{{:>6.2f}, {:>6.2f}, {:>6.2f}}}".format(self.x, self.y, self.z)
@patch
def as2d(self:Point):
	return Point(self.x, self.y, 0)
@patch
def xyz(self:Point):
	return self.x, self.y, self.z
@patch
def xy(self:Point):
	return self.x, self.y


#Monkey-patch Segment
@patch
def __repr__(self:Segment):
	return "<{}↔︎{}>".format(self.start_point, self.end_point)
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


@patch
def __repr__(self:Vector):
	return "V({:.2f}, {:.2f}, {:.2f})".format(*self._v)



class GPoint(Point):
	def __init__(self, *args, z=0):
		"""Pass Geometry3D.Point arguments or a gcline.Line and optionally a *z*
		argument. If *z* is missing it will be set to 0."""
		if len(args) == 1 and isinstance(args[0], GCLine):
			l = args[0]
			if not (l.code in ('G0', 'G1') and 'X' in l.args and 'Y' in l.args):
				raise ValueError(f"GCLine instance isn't an X or Y move:\n\t{args[0]}")
			super().__init__(l.args['X'], l.args['Y'], z)
			self.line = l
		elif len(args) == 3:
			super().__init__(*args)
			self.line = None
		elif len(args) == 2:
			if isinstance(args[0], Point):
				super().__init__(args[0].x, args[0].y, z)
			else:
				super().__init__(*args, z)
			self.line = None
		else:
			raise ValueError(f"Can't init GPoint with args {args}")


	def as2d(self):
		"""Return a copy of this point with *z* set to 0. If z is already 0, return self."""
		if self.z == 0:
			return self
		c = copy(self)
		c.z = 0
		return c


	def inside(self, seglist):
		"""Return True if this point is inside the polygon formed by the Segments
		in seglist."""
		#We make a segment from this point to 0,0,0 and test intersections; if
		# there are an even number, the point is inside the polygon.
		test_seg = GSegment(self.as2d(), (0,0,0))
		return len([s for s in seglist if intersection(test_seg, s.as_2d())]) % 2

#Patch Point to also have a inside() method
Point.inside = GPoint.inside


class GSegment(Geometry3D.Segment):
	def __init__(self, a, b, z=0):
		#Save lines of gcode that make this segment, if any
		self.gc_line1 = None
		self.gc_line2 = None

		if isinstance(a, Point):
			point1 = a
		elif isinstance(a, GCLine):
			self.gc_line1 = a
			point1 = GPoint(self.gc_line1, z=z)
		elif isinstance(a, (tuple,list)):
			point1 = GPoint(*a)
		if isinstance(b, Point):
			point2 = b
		elif isinstance(b, GCLine):
			self.gc_line2 = b
			point2 = GPoint(self.gc_line2, z=z)
		elif isinstance(b, (tuple,list)):
			point2 = GPoint(*b)

		if point1 == point2:
			raise ValueError("Cannot initialize a Segment with two identical Points")

		self.line = Geometry3D.Line(point1, point2)
		self.start_point = point1
		self.end_point = point2


	def intersection2d(self, other):
		return intersection(self.as2d(), other.as2d())


	def as_2d(self):
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


"""
def unitwrapper(obj):
	@wraps(obj)
	def wrapper(*args, **kwargs):
		print(f'Doing {obj.__name__}!')
		return obj(*args, **kwargs)
	return wrapper

length = ureg.get_dimensionality('[length]')
angle  = 0*ureg.degrees
# class Point(Geometry3D.Point):
# 	__init__ = check(
"""
