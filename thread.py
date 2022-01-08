import gcode
from copy import deepcopy
from dataclasses import make_dataclass
from Geometry3D import Point, Segment, Plane, Vector, intersection

class GCodeException(Exception):
	def __init__(self, obj, message):
		self.obj = obj
		self.message = message

Geometry = make_dataclass('Geometry', ['segments', 'planes'])
Planes   = make_dataclass('Planes',   ['top', 'bottom'])

def layers_to_geom(g, layer_height=None):
	"""Add a .geometry member to each layer of GcodeFile g. Assumes absolute
	positioning (G90). If g.preamble doesn't have a 'Layer height' entry, provide
	layer_height."""
	last = None
	for layer in g.layers:
		if not layer.has_moves:
			continue
		layer.geometry = Geometry(segments=[], planes=[])
		for line in layer.lines:
			if line.is_xyextrude():
				try:
					layer.geometry.segments.append(Segment(
							Point(last.args['X'], last.args['Y'], layer.z),
							Point(line.args['X'], line.args['Y'], layer.z)))
				except (AttributeError, TypeError) as e:
					raise GCodeException((layer,last), f'Segment {line.lineno}: {line}') from e
			if line.is_xymove():
				last = line

		#Construct two planes at the top and bottom of the layer, based on the
		# layer height
		if not layer_height:
			layer_height = float(g.preamble.info['Layer height'])

		(min_x, min_y), (max_x, max_y) = layer.extents()
		mid_x = min_x + .5 * (max_x - min_x)
		z = layer.z

		plane_points = [(min_x, min_y), (mid_x, max_y), (max_x, max_y)]
		bot_z = z - layer_height/2
		top_z = z + layer_height/2
		bottom = Plane(*[Point(p[0], p[1], bot_z) for p in plane_points])
		top    = Plane(*[Point(p[0], p[1], top_z) for p in plane_points])
		bottom.z = bot_z
		top.z    = top_z
		layer.geometry.planes = Planes(bottom=bottom, top=top)


def intersection2d(seg1, seg2):
	"""Discard the z information and return the intersection of two line
	segments."""
	return intersection(
			Segment(
				Point(seg1.start_point.x, seg1.start_point.y, 0),
				Point(seg1.end_point.x,   seg1.end_point.y,   0)),
			Segment(
				Point(seg2.start_point.x, seg2.start_point.y, 0),
				Point(seg2.end_point.x,   seg2.end_point.y,   0))
	)


def intersect_thread(th: [Segment], layer):
	"""Given a list of thread geometry Segments th, return a list of thread
	segments that are in the layer:

		[thread Segment, entry_intersection, exit_intersection, layer_intersections]

	If entry_intersection (exit_) is None, the segment starts (ends) inside the
	layer.
	"""
	segs = []

	bottom = layer.geometry.planes.bottom
	top    = layer.geometry.planes.top
	for t in th:
		#Is the segment entirely below or above the layer? If so, skip it.
		if((t.start_point.z <  bottom.z and t.end_point.z <  bottom.z) or
			 (t.start_point.z >= top.z   and  t.end_point.z >= top.z)):
			segs.append([t, None, None, [], []])
			continue

		#See if the thread segment enters and/or exits the layer
		enter = t.intersection(bottom)
		exit  = t.intersection(top)

		#And find the gCode lines the segment intersects with
		gc_inter, inter_points = [], []
		gc_inter = [gcseg for gcseg in layer.geometry.segments if intersection2d(t, gcseg)]
		# for gcseg in layer.geometry.segments:
		# 	inter = intersection2d(t, gcseg)
		# 	if inter:
		# 		gc_inter.append(gcseg)
		# 		inter_points.append(inter)

		segs.append([t, enter, exit, gc_inter, inter_points])

	return segs


def plot_test():
	import matplotlib.pyplot as plt
	import numpy as np
	from danutil import unpickle

	g = gcode.GcodeFile('/Users/dan/r/thread_printer/stl/test1/main_body.gcode')
	layers_to_geom(g.layers)

	#units from fusion are always in cm, so we need to convert to mm
	tpath = np.array(unpickle('/Users/dan/r/thread_printer/stl/test1/thread_from_fusion.pickle')) * 10
	thread_transform = [131.164, 110.421, 0]
	tpath += [thread_transform, thread_transform]

	ax = plt.figure().add_subplot(projection='3d')

	z = g.layers[53].z
	for s in g.layers[53].geometry['segments']:
			ax.plot([s.start_point.x, s.end_point.x], [s.start_point.y, s.end_point.y], [s.start_point.z, s.end_point.z], 'g', lw=1)
	for s,e in tpath:
			ax.plot([s[0], e[0]], [s[1], e[1]], [s[2], e[2]], 'r', lw=1)

	plt.show()

if __name__ == "__main__":
	#import sys, gcode, Geometry3D
	#g = gcode.GcodeFile(sys.argv[1])
	#layers_to_geom(g.layers)
	#r = Geometry3D.Renderer()
	#for l in g.layers[int(sys.argv[2])].geometry:
	#	r.add((l, 'g', 1))
	#r.show()
	plot_test()
