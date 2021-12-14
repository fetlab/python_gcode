import Geometry3D
from itertools import groupby

def layer_to_geom(layer):
	"""Add a .geometry member to layer with line segments."""
	groups = [list(g) for k,g in groupby(layer.lines, lambda l: l.is_xyextrude())]
	extgroups = [g for g in groups if 'E' in g[0].args]

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
