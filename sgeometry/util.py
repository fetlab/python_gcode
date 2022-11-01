from skgeom import squared_distance
from .gpoint import GPoint

def distance(a,b):
	return squared_distance(a,b)**.5


#Source: https://math.stackexchange.com/questions/543496/
def tangent_points(center:GPoint, radius, p:GPoint):
	"""Given a circle at center with radius, return the points on the circle that
	form tanget lines with point p."""

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


