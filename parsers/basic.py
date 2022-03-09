from gcline import GCLine
from util import listsplit

def detect(lines):
	return True


def parse(gcobj):
	"""Basic gcode parser. No preamble/postamble detection. Splits on Z."""
	layer_class = gcobj.layer_class
	gcobj.lines = [GCLine(l, lineno=n+1) for n,l in enumerate(gcobj.filelines)]
	layers      = [layer_class(g, layernum=i) for i,g in enumerate(
		listsplit(gcobj.lines, lambda l: 'Z' in l.line, keepsep='>', minsize=1))]
	gcobj.layers = layers
