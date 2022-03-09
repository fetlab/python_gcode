import sys, warnings
import parsers
from gclayer import Layer
from gcline import GCLine


class GcodeFile:
	def __init__(self, filename=None, filestring='', layer_class=Layer,
			line_class=GCLine, parser=None):
		"""Parse a file's worth of gcode."""
		self.preamble = None
		self.layers   = []
		self.filestring = filestring
		if filename:
			if filestring:
				warnings.warn("Ignoring passed filestring in favor of loading file.")
			self.filestring = open(filename).read()
		self.filelines = self.filestring.split('\n')
		self.layer_class = layer_class
		self.line_class  = line_class
		self.parse(parser)


	def __repr__(self):
		return '<GcodeFile with %d layers>' % len(self.layers)


	def construct(self, outfile=None):
		"""Construct all of and return the gcode. If outfile is given,
		write the gcode to the file instead of returning it."""
		s = (self.preamble.construct() + '\n') if self.preamble else ''
		for i,layer in enumerate(self.layers):
			s += ';LAYER:%d\n' % i
			s += layer.construct()
			s += '\n'
		if outfile:
			with open(outfile, 'w') as f:
				f.write(s)
		else:
			return s


	def shift(self, layernum=0, **kwargs):
		"""Shift given layer and all following. Provide arguments and
		amount as kwargs. Example: shift(17, X=-5) shifts layer 17 and all
		following by -5 in the X direction."""
		for layer in self.layers[layernum:]:
			layer.shift(**kwargs)


	def multiply(self, layernum=0, **kwargs):
		"""The same as shift() but multiply the given argument by a
		factor."""
		for layer in self.layers[layernum:]:
			layer.multiply(**kwargs)


	def parse(self, parser):
		"""Parse the gcode. Split it into chunks of lines at Z changes,
		assuming that denotes layers. The Layer object does the actual
		parsing of the code."""
		if not self.filelines:
			return

		parser = parser or parsers.find_parser(self.filelines)
		parser.parse(self)


def test():
	try:
		g = GcodeFile('example_gcode/cubex2-cura_4.12.1.gcode')
	except Exception as e:
		return e.args[0]
	return g


if __name__ == "__main__":
	if sys.argv[1:]:
		g = GcodeFile(sys.argv[1])
		print(g)
		print((g.layers))
