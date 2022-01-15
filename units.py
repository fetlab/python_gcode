from pint import UnitRegistry
from functools import partial

ureg = UnitRegistry(auto_reduce_dimensions=True)

#So we can do U.mm(7) instead of (7*ureg.mm)
class UnitHelper:
	def __getattr__(self, attr):
		return partial(self.unitmap, units=attr)
	def unitmap(self, *args, units='mm'):
		return(ureg.Quantity(args[0], units=units) if len(args) == 1
			else [ureg.Quantity(a, units=units) for a in args])


U = UnitHelper()

#some convenience units
mm  = ureg.mm
cm  = ureg.cm
#Don't use `radians` or `degrees` as shortcuts to avoid overriding `math` functions
rad = ureg.radians
deg = ureg.degrees
