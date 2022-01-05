	"""
	#Plot top/bottom planes for the layer
	xx = list(filter(None, x)); yy = list(filter(None, y))
	zz = g.layers[53].z - 0.2
	fig.add_trace(go.Mesh3d(
			x=[min(xx), min(xx), max(xx), max(xx)],
			y=[min(yy), max(yy), max(yy), min(yy)],
			z=[zz,		 zz,		 zz,		 zz],
			opacity=.5))
	zz = g.layers[53].z + 0.2
	fig.add_trace(go.Mesh3d(
			x=[min(xx), min(xx), max(xx), max(xx)],
			y=[min(yy), max(yy), max(yy), min(yy)],
			z=[zz,		 zz,		 zz,		 zz],
			opacity=.5))
"""
