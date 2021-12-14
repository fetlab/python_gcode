import Geometry3D

def layer_to_geom(layer):
	"""Add a .geometry member to layer with line segments."""

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
