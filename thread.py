from Geometry3D import Point, Segment
from itertools import groupby, tee

def pairwise(iterable):
	# pairwise('ABCDEFG') --> AB BC CD DE EF FG
	a, b = tee(iterable)
	next(b, None)
	return zip(a, b)


def layers_to_geom(layers):
	"""Add a .geometry member to layer with line segments. Assumes absolute
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

if __name__ == "__main__":
	import sys, gcode, Geometry3D
	g = gcode.GcodeFile(sys.argv[1])
	layers_to_geom(g.layers)
	r = Geometry3D.Renderer()
	for l in g.layers[int(sys.argv[2])].geometry:
		r.add((l, 'g', 1))
	r.show()
