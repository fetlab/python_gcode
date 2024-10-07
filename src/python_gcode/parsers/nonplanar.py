from ..gcline import GCLine, GCLines
from ..gcode_printer import GCodePrinter
from ..gclayer import Layer

def detect(lines):
	return 'nonplanar' in lines[0].lower()

EXT_ABS = 'absolute'
EXT_REL = 'relative'
class ParserPrinter(GCodePrinter):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.extrusion_mode = EXT_ABS
		self.add_codes('M82', 'M83', action=self.gcfunc_set_extrusion_mode)


	def gcfunc_set_extrusion_mode(self, gcline:GCLine, **kwargs):
		if   gcline.code == 'M82': self.extrusion_mode = EXT_ABS
		elif gcline.code == 'M83': self.extrusion_mode = EXT_REL


	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs):
		#Track head location
		if gcline.x: self.x = gcline.x
		if gcline.y: self.y = gcline.y
		if gcline.z: self.z = gcline.z

		#Ensure each move line has all 3 coords
		if any((gcline.x, gcline.y, gcline.z)):
			x = gcline.x or self.x
			y = gcline.y or self.y
			z = gcline.z or self.z
			gcline = gcline.copy(x=x, y=y, z=z)

		if 'E' in gcline.args:
			#G92: software set value
			if gcline.code == 'G92':
				self.e = gcline.args['E']

			if self.extrusion_mode == EXT_ABS:
				gcline.relative_extrude = gcline.args['E'] - self.e
				self.e = gcline.args['E']
			else:
				gcline.relative_extrude = gcline.args['E']
				self.e += gcline.args['E']

		else:
			gcline.relative_extrude = 0

		return [gcline]



def _parse(gcobj):
	"""Ultra-basic, no layers"""
	layer_class = gcobj.layer_class
	printer = ParserPrinter()

	file_preamble = []
	for i,l in enumerate(gcobj.filelines):
		line = GCLine(l, lineno=i+1)
		file_preamble.extend(printer.execute_gcode(line))
		if line.code == 'M82':
			break

	gclines = []
	for j,l in enumerate(gcobj.filelines[i:]):
		line = GCLine(l, lineno=j+i+1)
		if line.code == 'M107':
			j -= 1
			break
		gclines.extend(printer.execute_gcode(line))

	file_postamble = [GCLine(l, lineno=j+k+i+1) for k,l in enumerate(gcobj.filelines[i+j:])]

	gcobj.preamble_layer  =  layer_class(GCLines(file_preamble), layernum='preamble')
	gcobj.postamble_layer =  layer_class(GCLines(file_postamble), layernum='postamble')
	gcobj.layers          = [layer_class(GCLines(gclines), layernum=1)]


def parse(gcobj):
	gcprinter = GCodePrinter()
	gcobj.lines = gcprinter.execute_gcode([GCLine(l, lineno=i+1) for i,l in enumerate(gcobj.filelines)])
	gcobj.layers = [Layer(gcobj.lines, layernum=0)]
