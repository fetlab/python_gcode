from gcline import Line
from gclayer import Layer
from util import listsplit

"""Each parser should have a detect() and a parse(). parse() returns (preamble layer, layer list)"""

#PrusaSlicer: has header comment "generated by PrusaSlicer", has
# "BEFORE_LAYER_CHANGE" and "AFTER_LAYER_CHANGE" comments,
# although these are configured per-printer in .ini files. Looks
# like new layers start at "BEFORE_LAYER_CHANGE".
#Simplify3D: has header comment "generated by Simplify3D", has
# comments "layer N" where N is a number.
#Slic3r 1.3: has header comment "generated by Slic3r", no comments
# to denote layer changes
#Cura 15: has footer comment "CURA_PROFILE_STRING", has comments
# "LAYER:N" where N is a number.
#Cura 4.6: has header comment "Generated with Cura_SteamEngine",
# has comment "LAYER:N" where N is a number.
#
#Cura 4.12: has header comment "Generated with Cura_SteamEngine",
# has comment "LAYER:N" where N is a number; in each layer, has comments
# for different types of feature:
#   ;MESH:10x10x10 cube.stl
#   ;TYPE:WALL-INNER
#   ;TYPE:WALL-OUTER
#   ;TYPE:SKIN
#   ;MESH:NONMESH
#   ;TYPE:SKIRT

__name__ = "Cura4"

class Cura4Layer(Layer):
	"""A Layer, but using the comments in the Cura gcode to add additional useful
	members:
		Layer.meshes -> a list of sub-meshes to be found in this layer
			each containing
				.features -> a dict of lines by feature type
	"""
	pass

def detect(lines):
	return any('Cura_SteamEngine' in l for l in lines[:20])


#Convention is that preamble "layer" is -1, first print layer is 0
def parse(lines):
	"""Parse Cura4 Gcode into layers using the ;LAYER:N comment line."""
	glines = [Line(l, lineno=n) for n,l in enumerate(lines)]
	preamble, glines = listsplit(glines, lambda l: l.line.startswith(';LAYER:'),
			maxsplit=1, keepsep='>')
	layergroups = [Layer(layer) for layer in
			listsplit(glines, lambda i: i.line.startswith(''), keepsep='>')]

	preamble = Layer(preamble, layernum='preamble')
	preamble.info = {}
	for line in preamble.lines:
		if line.line[0] == ';' and ':' in line.line[0]:
			key, val = line.line[1:].split(':', maxsplit=1)
			preamble.info[key] = val

	#The first line in each layer will be ";LAYER:N" because that's what we split on
	for layer in layergroups[1:]:
		try:
			layer.layernum = int(layer.lines[0].line[1:].split(':')[1])
		except IndexError:
			print(layer.lines[0])
			raise

	return preamble, [
			Layer(layergroup, layernum=i) for i,layergroup in enumerate(layergroups[1:])]
