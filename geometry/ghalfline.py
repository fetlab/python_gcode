from typing import Collection, Set
from fastcore.basics import listify
from Geometry3D import Vector, HalfLine, Point, Segment, Plane
from .gpoint import GPoint
from .utils import distance_linelike_point

class GHalfLine(HalfLine):
	def __init__(self, a, b=None):
		if isinstance(a, HalfLine):
			a, b = a.parametric()
		else:
			a = GPoint(a) if isinstance(a, (tuple, list, set, Point)) else a
			b = GPoint(b) if isinstance(b, (tuple, list, set, Point)) else b
		super().__init__(a, b)


	def as2d(self):
		return self.__class__(GPoint.as2d(self.point), self.vector)


	def intersecting(self, check:Collection[Segment]) -> Set[Segment]:
		"""Return Segments in check which this HalfLine intersects with,
		ignoring intersections with the start point of this HalfLine."""
		return {seg for seg in listify(check) if self.intersection(seg) not in [None, self.point]}


	def __repr__(self):
		return "H({}, {})".format(self.point, self.vector)


	def distance(self, other):
		return distance_linelike_point(self, other)
		if not isinstance(other, Point):
			return super().distance(other)
		p = other
		aux_plane = Plane(p, self.vector)
		foot = aux_plane.intersection(self)
		return None if foot is None else p.distance(foot)


	def moved(self, vec):
		point = self.point if isinstance(self.point, GPoint) else GPoint(self.point)
		return self.__class__(point.moved(vec), self.vector)


	def parallels2d(self, distance=1, inc_self=False):
		"""Return two GHalfLines parallel to this one, offset by `distance` to either
		side. Include this halfline if in_self is True."""
		v = self.vector.normalized()
		mv1 = Vector(v[1], -v[0], v[2]) * distance
		mv2 = Vector(-v[1], v[0], v[2]) * distance
		return [self.moved(mv1), self.moved(mv2)] + ([self] if inc_self else [])

