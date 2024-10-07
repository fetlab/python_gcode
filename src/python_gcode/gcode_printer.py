from typing import Callable
from fastcore.basics import listify
from gcode_geom import GPoint, GSegment, GHalfLine
from .util import attrhelper
from .gcline import GCLine
from .gclayer import Layer

#Extruder mode constants
E_ABS = 'absolute'
E_REL = 'relative'

class GCodePrinter:
	"""Simulates a printer in order to generate gcode."""
	def __init__(self, *args, **kwargs):

		#State: absolute extrusion amount, print head location, anchor location
		# (initially the bed's anchor)
		self.e           = 0
		self.e_mode      = E_ABS
		self.last_e      = 0

		self.f           = 5000
		self.head_loc    = GPoint(0, 0, 0)
		self.head_set_by = None
		self.prev_loc    = GPoint(0,0,0)
		self.prev_set_by = None
		self.curr_gcline:GCLine = None
		self.curr_gcseg:GSegment  = None

		#Functions for different Gcode commands
		self._code_actions: dict[str|None,Callable] = {}
		self.add_codes(None,       action=lambda gcline, **kwargs: [gcline])
		self.add_codes('G28',      action=self.gcfunc_auto_home)
		self.add_codes('G0', 'G1', action=self.gcfunc_move_axis)
		self.add_codes('G92',      action=self.gcfunc_set_axis_value)
		self.add_codes('M82',      action=self.gcfunc_set_e_absolute)
		self.add_codes('M83',      action=self.gcfunc_set_e_relative)


	#Create attributes which call Printer.attr_changed on change
	x = property(**attrhelper('head_loc.x'))
	y = property(**attrhelper('head_loc.y'))
	z = property(**attrhelper('head_loc.z'))

	@property
	def xy(self): return self.x, self.y

	def __repr__(self):
		return f'{self.__class__.__name__}(x={self.x}, y={self.y}, z={self.z})'


	def add_codes(self, *codes, action:str|Callable):
		"""Add the given action for each code in `codes`. `action` can be a string,
		in which case the line of gcode will be saved as an attribute with that
		name on this object, or it can be a function, in which case that function
		will be called with the line of gcode as a parameter."""
		for code in codes:
			if isinstance(action, str):
				self._code_actions[code] = lambda v: setattr(self, action, v) #type: ignore #Checked for action type
			elif callable(action):
				self._code_actions[code] = action
			else: raise ValueError(f'Need function or string for `action`, not {type(action)}')


	#Functions to add extra lines of GCode. Each is passed the pre/postamble and
	# should return it, possibly modified.
	def file_preamble  (self, preamble:  list[GCLine]) -> list[GCLine]: return preamble
	def file_postamble (self, postamble: list[GCLine]) -> list[GCLine]: return postamble
	def layer_preamble (self, preamble:  list[GCLine], layer:Layer) -> list[GCLine]: return preamble
	def layer_postamble(self, postamble: list[GCLine], layer:Layer) -> list[GCLine]: return postamble


	def set_thread_path(self, thread_path:GHalfLine, target:GPoint) -> list[GCLine]:
		raise NotImplementedError("Subclass must implement gcode_set_thread_path")


	def _execute_gcline(self, gcline:GCLine, **kwargs) -> list[GCLine]:
		return self._code_actions.get(gcline.code, self._code_actions[None])(gcline, **kwargs) or [gcline]


	def execute_gcode(self, gcline:GCLine|list[GCLine|None]|None, **kwargs) -> list[GCLine]:
		return sum([self._execute_gcline(l, **kwargs) for l in listify(gcline) if l], [])


	#G28
	def gcfunc_auto_home(self, gcline: GCLine, **kwargs):
		self.x, self.y, self.z = 0, 0, 0


	#G0, G1
	def gcfunc_move_axis(self, gcline:GCLine, **kwargs) -> list[GCLine]:
		return self.gcfunc_set_axis_value(gcline, **kwargs)


	#G0, G1, G92
	def gcfunc_set_axis_value(self, gcline: GCLine, **kwargs) -> list[GCLine]:
		#Track head location
		if gcline.x: self.x = gcline.x
		if gcline.y: self.y = gcline.y
		if gcline.z: self.z = gcline.z

		if any((gcline.x, gcline.y, gcline.z)):
			self.head_set_by = gcline

		new_args = {}

		#Try to keep feedrate for a line, even when moving lines around
		feedrate = gcline.args.get('F', gcline.meta.get('feedrate', self.f))
		if feedrate != self.f:
			self.f = feedrate
			if 'F' not in gcline.args:
				new_args['F'] = feedrate

		if 'E' in gcline.args:
			#G92: software set value
			if gcline.code == 'G92':
				self.e = gcline.args['E']

			#A normal extruding line; we need to use the relative extrude value
			# since our lines get emitted out-of-order
			else:
				self.e += gcline.relative_extrude or 0
				if self.e_mode == E_ABS:
					new_args['E'] = self.e
				elif self.e_mode == E_REL:
					new_args['E'] = gcline.relative_extrude

		if new_args:
			return [gcline.copy(args=new_args)]

		return [gcline]


	def gcfunc_set_e_absolute(self, gcline:GCLine, **kwargs):
		self.e_mode = E_ABS


	def gcfunc_set_e_relative(self, gcline:GCLine, **kwargs):
		self.e_mode = E_REL
