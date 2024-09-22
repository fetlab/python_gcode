from gcline import GCLine
from util import listsplit

__name__ = "prusa"

def detect(lines):
	return 'PrusaSlicer' in lines[0]


def parse(gcobj):
	layer_class = gcobj.layer_class

	#Read the file and create GCLines out of it
	gclines = []
	last_extrude = 0
	ext_mode = 'relative'
	feedrate = None
	for i,l in enumerate(gcobj.filelines):
		line = GCLine(l, lineno=i+1)
		if line.code == 'M82': ext_mode = 'absolute'
		if line.code == 'M83': ext_mode = 'relative'
		if 'F' in line.args: feedrate = line.args['F']
		if 'E' in line.args:
			if ext_mode == 'absolute':
				if line.code == 'G92':
					last_extrude = line.args['E']
				elif line.code in ['G0', 'G1']:
					line.relative_extrude = line.args['E'] - last_extrude
					last_extrude = line.args['E']
			else:
				line.relative_extrude = line.args['E']
		line.meta['feedrate'] = feedrate
		gclines.append(line)

	gcobj.lines = gclines.copy()

	#Extract the file preamble and postamble
	file_preamble, gclines = listsplit(gclines, lambda l: l.line.lstrip('; ').startswith('LAYER_CHANGE'),
			maxsplit=1, keepsep='>')
	file_postamble, gclines = listsplit(reversed(gclines), lambda l: l.line.lstrip('; ').startswith('TYPE:Custom'),
			maxsplit=1, keepsep='>')
	file_postamble.reverse()
	gclines.reverse()

	#Split layers
	splits = listsplit(gclines, lambda l: l.line.lstrip('; ').startswith('LAYER_CHANGE'),  keepsep='>')

	#Create layer objects
	layers = []
	for i, layer_lines in enumerate(splits):
		z = float(layer_lines[1].line.split(':')[1])
		h = float(layer_lines[2].line.split(':')[1])
		layers.append(layer_class(layer_lines, layernum=i, layer_height=h, z=z))

	gcobj.preamble_layer  = layer_class(file_preamble, layernum='preamble')
	gcobj.layers          = layers
	gcobj.postamble_layer = layer_class(file_postamble, layernum='postamble')
