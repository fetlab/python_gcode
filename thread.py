import gcode
from Geometry3D import Point, Segment

def layers_to_geom(layers):
	"""Add a .geometry member to each layer with line segments. Assumes absolute
	positioning (G90)."""
	last = None
	for layer in layers:
		layer.geometry = []
		for line in layer.lines:
			if line.is_xyextrude():
				try:
					layer.geometry.append(Segment(
							Point(last.args['X'], last.args['Y'], layer.z),
							Point(line.args['X'], line.args['Y'], layer.z)))
				except AttributeError:
					print(f'Segment {line.lineno}: {line}')
					raise
			if line.is_xymove():
				last = line


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
	for s in g.layers[53].geometry:
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
