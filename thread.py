import gcode
from Geometry3D import Point, Segment, Plane, Vector

class GCodeException(Exception):
	def __init__(self, obj, message):
		self.obj = obj
		self.message = message


def layers_to_geom(g, layer_height=None):
	"""Add a .geometry member to each layer of GcodeFile g. Assumes absolute
	positioning (G90). If g.preamble doesn't have a 'Layer height' entry, provide
	layer_height."""
	last = None
	for layer in g.layers:
		if not layer.has_moves:
			continue
		layer.geometry = {'segments': [], 'plane': None}
		for line in layer.lines:
			if line.is_xyextrude():
				try:
					layer.geometry['segments'].append(Segment(
							Point(last.args['X'], last.args['Y'], layer.z),
							Point(line.args['X'], line.args['Y'], layer.z)))
				except (AttributeError, TypeError) as e:
					raise GCodeException((layer,last), f'Segment {line.lineno}: {line}') from e
			if line.is_xymove():
				last = line

		#Construct two planes at the top and bottom of the layer, based on the
		# layer height -> unncessary, just need one at the layer height
		if not layer_height:
			layer_height = float(g.preamble.info['Layer height'])

		(min_x, min_y), (max_x, max_y) = layer.extents()
		mid_x = min_x + .5 * (max_x - min_x)
		z = layer.z

		plane_points = [(min_x, min_y), (mid_x, max_y), (max_x, max_y)]
		layer.geometry['planes'] = [
				#Plane(*[Point(p[0], p[1], z - layer_height/2) for p in plane_points]),
				#Plane(*[Point(p[0], p[1], z + layer_height/2) for p in plane_points])]
				Plane(*[Point(p[0], p[1], z) for p in plane_points])]


def intersect_layers(start, end, layers, extrusion_width=0.4):
	#Return layers where the line segment starts or ends inside the layer, or
	# where the line segment starts before the layer and ends after the layer.
	ll = []
	layers = iter(layers)

	for layer in layers:
		if start.z >= layer.z:
			ll.append(layer)
		else:
			break

	for layer in layers:
		if end.z <= layer.z:
			ll.append(layer)
		else:
			break

	return ll


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
