from copy import copy
from typing import Collection, Set
from Geometry3D import Vector, Segment, Point, Line
from fastcore.basics import listify
from .gpoint import GPoint

class GSegment(Segment):
	def __init__(self, a, b=None, z=None, gc_lines=None, is_extrude=False, **kwargs):
		#Label whether this is an extrusion move or not
		self.is_extrude = is_extrude

		self.printed = False

		#Save the movement lines of gcode
		self.gc_line1 = None
		self.gc_line2 = None

		#Save *all* lines of gcode involved in this segment
		self.gc_lines = gc_lines

		#Argument |a| is a GSegment: instantiate a copy
		if isinstance(a, Segment):
			# if b is not None:
			# 	raise ValueError('Second argument must be None when first is a Segment')
			copyseg = a
			#Make copies of the start/end points to ensure we avoid accidents
			a = copy(kwargs.get('start_point', copyseg.start_point))
			b = copy(kwargs.get('end_point',   copyseg.end_point))
			z = a.z if z is None else z
			gc_lines   = getattr(copyseg, 'gc_lines', []) if gc_lines is None else gc_lines
			is_extrude = getattr(copyseg, 'is_extrude', is_extrude)

		#If instantiating a copy, |a| and |b| have been set from the passed GSegment
		if isinstance(a, Point):
			point1 = a if isinstance(a, GPoint) else GPoint(a)
		elif type(a).__name__ == 'GCLine': #Using type() rather than isinstance() to avoid circular import issues
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
		elif type(b).__name__ == 'GCLine': #Using type() rather than isinstance() to avoid circular import issues
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

		self.line = Line(point1, point2)
		self.start_point = point1
		self.end_point   = point2

		#Sort any gcode lines by line number
		if self.gc_lines:
			self.gc_lines.sort()


	def __repr__(self):
		if not(self.gc_line1 and self.gc_line2):
			return "<{}←→{} ({:.2f} mm)>".format(self.start_point, self.end_point,
					self.length())
		return "<{}[{:>2}] {}:{}←→{}:{} ({:.2f} mm)>".format(
				'S' if self.printed else 's',
				len(self.gc_lines),
				self.gc_line1.lineno, self.start_point,
				self.gc_line2.lineno, self.end_point,
				self.length())


	#We define __eq__ so have to inherit __hash__:
	# https://docs.python.org/3/reference/datamodel.html#object.__hash__
	__hash__ = Segment.__hash__

	def __eq__(self, other):
		return False if not isinstance(other, Segment) else super().__eq__(other)


	def intersection(self, other):
		from .gcast import gcast
		return gcast(super().intersection(other))


	def intersecting(self, check, ignore:Point | Collection[Point]=()) -> Set[Segment]:
		"""Return objects in check that this GSegment intersects with, optionally
		ignoring intersections with Points in ignore."""
		ignore = [None] + listify(ignore)
		return {o for o in listify(check) if
				self != o and
				(isinstance(o, Point) and o not in ignore and o in self) or
				(self.intersection(o) not in ignore)}


	def intersection2d(self, other):
		return self.as2d().intersection(other.as2d())


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
		self.line = Line(self.start_point, self.end_point)
		return self


	def copy(self, start_point=None, end_point=None, z=None):
		return GSegment(self, None,
			start_point=start_point or self.start_point,
			end_point=end_point     or self.end_point,
			z=z)


	def moved(self, vec):
		"""Return a copy of this GSegment moved by vector vec."""
		sp = self.start_point if isinstance(self.start_point, GPoint) else GPoint(self.start_point)
		ep = self.end_point   if isinstance(self.end_point,   GPoint) else GPoint(self.end_point)
		return self.copy(sp.moved(vec), ep.moved(vec))


	def parallels2d(self, distance=1, inc_self=False):
		"""Return two GSegments parallel to this one, offset by `distance` to either
		side. Include this segment if in_self is True."""
		v = self.line.dv.normalized()
		mv1 = Vector(v[1], -v[0], v[2]) * distance
		mv2 = Vector(-v[1], v[0], v[2]) * distance
		return [self.moved(mv1), self.moved(mv2)] + ([self] if inc_self else [])


	def __mul__(self, other):
		if not isinstance(other, (int, float)):
			return self * other
		return self.copy(end_point=self.end_point.moved(self.line.dv.normalized() * other))

