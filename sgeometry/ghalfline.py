from typing import Collection, Set
from fastcore.basics import listify
from skgeom import Ray3, Point3, Vector3
from .gpoint import GPoint
from .gsegment import GSegment
from .util import distance

class GHalfLine(Ray3):
	def __init__(self, a, b=None):
		if isinstance(a, Ray3):
			a, b = a.source(), a.to_vector()
		else:
			a = GPoint(a) if isinstance(a, (tuple, list, set, Point3)) else a
			b = GPoint(b) if isinstance(b, (tuple, list, set, Point3)) else b
		super().__init__(a, b)


	def as2d(self):
		return self.__class__(GPoint.as2d(self.point), self.vector)


	def intersecting(self, check:Collection[GSegment]) -> Set[GSegment]:
		"""Return Segments in check which this HalfLine intersects with,
		ignoring intersections with the start point of this HalfLine."""
		return {seg for seg in listify(check) if self.intersection(seg) not in [None, self.point]}


	def __repr__(self):
		return "H({}, {})".format(self.point, self.vector)


	__contains__ = Ray3.has_on


	def distance(self, other):
		return distance(self, other)


	def moved(self, vec):
		point = self.point if isinstance(self.point, GPoint) else GPoint(self.point)
		return self.__class__(point.moved(vec), self.vector)


	def parallels2d(self, distance=1, inc_self=False):
		"""Return two GHalfLines parallel to this one, offset by `distance` to either
		side. Include this halfline if in_self is True."""
		v = self.vector.normalized()
		mv1 = Vector3(v[1], -v[0], v[2]) * distance
		mv2 = Vector3(-v[1], v[0], v[2]) * distance
		return [self.moved(mv1), self.moved(mv2)] + ([self] if inc_self else [])

