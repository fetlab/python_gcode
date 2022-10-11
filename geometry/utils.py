from math import atan2, pi
from typing import Collection
from more_itertools import first
from Geometry3D import Point, Segment, Line, Vector, Plane


def sign(n): return -1 if n < 0 else (1 if n > 0 else 0)


def min_max_xyz(objs:Collection):
	"""Given a list of Points or Segments, return
		(minx, miny, minz), (maxx, maxy, maxz)"""
	if isinstance(first(objs), Point):
		return min_max_xyz_points(objs)
	if isinstance(first(objs), Segment):
		return min_max_xyz_segs(objs)


def min_max_xyz_points(points:Collection[Point]):
	"""Return (minx, miny, minz), (maxx, maxy, maxz)"""
	x,y,z = list(zip(*[p[:] for p in points]))
	return (min(x), min(y), min(z)), (max(x), max(y), max(z))


def min_max_xyz_segs(segs:Collection[Segment]):
	"""Return (minx, miny, minz), (maxx, maxy, maxz)"""
	x,y,z = list(zip(*
				[((seg.start_point.x, seg.end_point.x),
					(seg.start_point.y, seg.end_point.y),
					(seg.start_point.z, seg.end_point.z)) for seg in segs]))
	return (min(x), min(y), min(z)), (max(x), max(y), max(z))


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


def ang_dist(p,c,a):
	"""Return the angular distance of Point p with respect to the line formed by c->a"""
	return atan2(p.y-c.y, p.x-c.x) - atan2(a.y-c.y, a.x-c.x)


def angsort(points: Collection[Point], ref:Segment):
	"""Return points sorted with respect to their (absolute) angle to the
	reference segment."""
	return sorted(points, key=lambda p: abs(ang_dist(p, ref.start_point, ref.end_point)))


def point_plane_comp(point:Point, plane:Plane):
	"""Return whether point is below (-1), on (0), or above (1) plane."""
	isec = Line(point, plane.n).intersection(plane)
	return sign(Vector(isec, point) * plane.n)


#Source: https://math.stackexchange.com/questions/543496/
def tangent_points(center:Point, radius, p:Point):
	"""Given a circle at center with radius, return the points on the circle that
	form tanget lines with point p."""
	from .gpoint import GPoint

	dx, dy = p.x-center.x, p.y-center.y
	dxr, dyr = -dy, dx
	d = (dx**2 + dy**2)**.5
	if d < radius:
		raise ValueError(f'Point {p} is closer to center {center} than radius {radius}')

	rho = radius/d
	ad = rho**2
	bd = rho*(1-rho**2)**.5
	return (
		GPoint(center.x + ad*dx + bd*dxr, center.y + ad*dy + bd*dyr, center.z),
		GPoint(center.x + ad*dx - bd*dxr, center.y + ad*dy - bd*dyr, center.z))

